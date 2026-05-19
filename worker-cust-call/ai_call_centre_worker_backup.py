# -----------------------------
# ai_call_centre_worker.py (FINAL PRODUCTION VERSION)
# Router + Extractor + Deterministic CRM Layer
# -----------------------------

import asyncio, json, os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import httpx

    from ai_worker_db_log import (
        log_activity,
        upsert_workflow_instance,
        store_call_transcript,
        get_call_transcript,
        store_erp_document        
    )

    from salesforce_cc_utils import (
        upsert_opportunity_by_external_id,
        enroll_contact_into_campaign_by_external_id
    )


# =========================================================
# CONFIG
# =========================================================
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "temporal-server-demo.australiaeast.cloudapp.azure.com:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "call-centre-ai-queue")
AI_API_URL = os.getenv("AI_API_URL", "https://temporal-fastapi.livelysand-fad44e9f.australiaeast.azurecontainerapps.io")

# =========================================================
@dataclass
class ActivityInput:
    payload: Dict[str, Any]
    context: Dict[str, Any]


@dataclass
class ActivityOutput:
    response: Dict[str, Any]
    context: Dict[str, Any]


# =========================================================
# HELPERS
# =========================================================
async def call_intent_ai(system_prompt, user_prompt, context, options=None):
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/intent-ai",
            json={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "context": context or {},
                "options": options or {},
            }
        )

    if resp.status_code != 200:
        raise Exception(f"Intent AI failed: {resp.text}")

    return resp.json()


def build_base_context(payload, wf_id):
    declared = payload.get("declared_data", {})

    return {
        "workflow_id": wf_id,
        "workflow_type": payload.get("workflow_type"),
        "customer_id": payload.get("customer_id") or declared.get("customer_number"),
        "email": declared.get("email"),
        "phone": declared.get("phone"),
        "call_id": declared.get("customer_call_record_id") or payload.get("call_id"),
    }


def merge_context(parent, child):
    return {
        **parent,
        **child,
        "workflow_id": parent["workflow_id"],
        "customer_id": parent.get("customer_id"),
        "call_id": parent.get("call_id"),
    }


async def execute_step(activity_fn, payload, context, step, timeout=30):

    prev_node = context.get("current_node_id")

    context = {
        **context,
        "prev_node_id": prev_node,
        "current_node_id": step,
        "branch_id": context.get("branch_id", "MAIN"),
    }

    result: ActivityOutput = await workflow.execute_activity(
        activity_fn,
        ActivityInput(payload, context),
        start_to_close_timeout=timedelta(seconds=timeout),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )

    payload = {**payload, **result.response}

    business_context = merge_context(context, result.context)

    # 🔒 Preserve graph state
    business_context["prev_node_id"] = context["prev_node_id"]
    business_context["current_node_id"] = context["current_node_id"]
    business_context["branch_id"] = context["branch_id"]

    return payload, business_context

# =========================================================
# DETERMINISTIC CRM FIELD ENGINE (CRITICAL)
# =========================================================
def generate_deterministic_fields(opportunity_type: str):
    """
    Business-controlled CRM fields (NO LLM dependency)
    """

    now = datetime.utcnow()

    if opportunity_type == "Retention":
        close_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        stage = "At Risk"

    elif opportunity_type == "Upsell":
        close_date = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        stage = "Qualification"

    else:  # Cross-sell
        close_date = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        stage = "Qualification"

    return {
        "CloseDate": close_date,
        "StageName": stage,
        "Amount": 1200
    }


# =========================================================
# 1 INGEST
# =========================================================
@activity.defn
@log_activity(display_name="01_INGEST_AUDIO_CALL")
async def ingest_call(input: ActivityInput) -> ActivityOutput:

    item = input.payload.get("items", [{}])[0]
    document_url = item.get("input_parameters", {}).get("document_url")

    upsert_workflow_instance(
        workflow_id=input.context["workflow_id"],
        workflow_type=input.context["workflow_type"],
        status="STARTED",
        input_data=input.payload,
        header_id=input.context.get("header_id"),
        reference_id=input.context.get("reference_id"),
    )

    if not document_url:
        raise ValueError("Missing document_url")

    return ActivityOutput(
        {"audio_url": document_url},
        {}
    )


# =========================================================
# 2 TRANSCRIBE
# =========================================================
@activity.defn
@log_activity(display_name="02_TRANSCRIBE_CALL")
async def transcribe_call(input: ActivityInput) -> ActivityOutput:

    audio_url = input.payload["audio_url"]

    cached = get_call_transcript(audio_url)
    if cached:
        return ActivityOutput({"transcript": cached}, {"source": "cache"})

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{AI_API_URL}/ai_doc_llm/transcribe-audio",
            json={"audio_url": audio_url}
        )
        r.raise_for_status()
        transcript = r.json()["transcript"]

    store_call_transcript(
        workflow_id=input.context["workflow_id"],
        call_id=input.context["call_id"],
        audio_url=audio_url,
        transcript=transcript
    )

    return ActivityOutput({"transcript": transcript}, {"source": "whisper"})


# =========================================================
# 3 ROUTER (LLM ONLY CLASSIFICATION)
# =========================================================
@activity.defn
@log_activity(display_name="03_AI_INTENT_DETECTION")
async def ai_intent_detection(input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt="opportunity_router",
        user_prompt="opportunity_router",
        context={"transcript": input.payload["transcript"]}
    )

    return ActivityOutput(
        {
            "opportunity_type": result["result"]["opportunity_type"],
            "confidence": result["result"]["confidence"]
        },
        {}
    )


# =========================================================
# 4 EXTRACTOR (LLM + BUSINESS ENRICHMENT)
# =========================================================
async def run_opportunity_extractor_core(prompt_name: str, opp_type: str, input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt=prompt_name,
        user_prompt=prompt_name,
        context={
            "transcript": input.payload["transcript"],
            "account_id": input.context["customer_id"]
        }
    )

    llm = result["result"]

    deterministic = generate_deterministic_fields(opp_type)

    return ActivityOutput(
        {
            "opportunity_payload": {
                "Type": opp_type,
                "Name": f"{opp_type} Opportunity - AI",
                "AccountId": input.context["customer_id"],

                **deterministic,

                "Opportunity_Sub_Type__c": llm.get("Opportunity_Sub_Type__c"),
                "AI_Call_Summary__c": llm.get("AI_Call_Summary__c"),
                "AI_Confidence_Score__c": llm.get("AI_Confidence_Score__c", 0),
                "AI_Intent_Strength__c": llm.get("AI_Intent_Strength__c"),
                "Competitor_Mentioned__c": llm.get("Competitor_Mentioned__c"),
                "Opportunity_Urgency__c": llm.get("Opportunity_Urgency__c"),
                "Recommended_Next_Action__c": llm.get("Recommended_Next_Action__c"),
            }
        },
        {}
    )

@activity.defn
@log_activity(display_name="04_AI_OPPORTUNITY_RETENTION")
async def ai_opportunity_retention(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_retention_extractor",
        "Retention",
        input
    )

@activity.defn
@log_activity(display_name="04_AI_OPPORTUNITY_UPSELL")
async def ai_opportunity_upsell(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_upsell_extractor",
        "Upsell",
        input
    )

@activity.defn
@log_activity(display_name="04_AI_OPPORTUNITY_CROSS_SELL")
async def ai_opportunity_cross_sell(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_cross_sell_extractor",
        "Cross-sell",
        input
    )


# =========================================================
# 05B CRM STAGING (REUSING ERP TABLE)
# =========================================================
@activity.defn
@log_activity(display_name="05_REGISTER_SALES_OPPORTUNITY")
async def register_sales_opportunity(input: ActivityInput) -> ActivityOutput:

    opp = input.payload.get("opportunity_payload")

    if not opp:
        return ActivityOutput({"status": "SKIPPED"}, {})

    import uuid

    doc_id = f"CRM-{uuid.uuid4().hex[:10]}"

    store_erp_document(
        doc_id=doc_id,
        doc_type="crm_opportunity",   # 👈 key change (separates ERP vs CRM)
        workflow_id=input.context.get("workflow_id"),
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        header_data={
            "staging_type": "SALESFORCE_OPPORTUNITY",
            "payload": opp
        },
        approval_status="STAGED",
        approved_by="SYSTEM",
        reference_id=input.context.get("reference_id"),
    )

    return ActivityOutput(
        {
            **input.payload,
            "REGISTER_SALES_OPPORTUNITY_doc_id": doc_id
        },
        {
            "crm_stage": {
                "doc_id": doc_id,
                "status": "STAGED"
            }
        }
    )

# =========================================================
# 5 CRM WRITE (SAFE + ID EMPOTENT)
# =========================================================
@activity.defn
@log_activity(display_name="06_SALESFORCE_OPPORTUNITY_CREATION")
async def salesforce_opportunity_creation(input: ActivityInput)->ActivityOutput:

    opp=input.payload.get("opportunity_payload")

    if not opp:
        return ActivityOutput({"status":"SKIPPED"},{})

    try:

        customer_id = input.context.get("customer_id")
        norm_opp_type = opp.get("Type").lower().replace("_", "-").replace(" ", "-")
        print("norm_opp_type======",norm_opp_type)
        amount = 1200
        if norm_opp_type == "retention":
            amount = 2400
        elif norm_opp_type == "upsell":
            amount = 1200
        elif norm_opp_type in ("cross-sell", "crosssell"):
            amount = 600

        result=upsert_opportunity_by_external_id(
            customer_external_id=customer_id,
            opportunity_external_id=f"{customer_id}_{opp['Type']}",

            opp_name=opp.get(
                "Name",
                f"{opp['Type']} Opportunity - AI"
            ),

            opp_type=opp["Type"],

            stage_name=opp.get(
                "StageName",
                "Qualification"
            ),

            close_date=opp.get("CloseDate"),
            amount=opp.get("Amount",500),
            opp_sub_type=opp.get("Opportunity_Sub_Type__c"),
            ai_call_summary=opp.get("AI_Call_Summary__c"),
            ai_confidence_score=opp.get("AI_Confidence_Score__c"),
            ai_intent_strength=opp.get("AI_Intent_Strength__c"),
            competitor_mentioned=opp.get("Competitor_Mentioned__c"),
            opportunity_urgency=opp.get("Opportunity_Urgency__c"),
            recommended_next_action=opp.get("Recommended_Next_Action__c")
        )

        return ActivityOutput(
            {
                "status":"SUCCESS",
                "salesforce_result":result
            },
            {}
        )

    except Exception as e:

        return ActivityOutput(
            {
                "status":"FAILED",
                "reason":str(e)
            },
            {}
        )

campaign_map = {
    "retention": "CUSTOMER_RETENTION_PROGRAM",
    "upsell": "CUSTOMER_GROWTH_PROGRAM",
    "crosssell": "REVENUE_EXPANSION_PROGRAM",
    "cross-sell": "REVENUE_EXPANSION_PROGRAM"
}

@activity.defn
@log_activity(display_name="07_CAMPAIGN_ENROLLMENT")
async def salesforce_campaign_enrollment(input: ActivityInput) -> ActivityOutput:

    opp = input.payload.get("opportunity_payload")

    if not opp:
        return ActivityOutput(
            {"status": "SKIPPED_NO_OPPORTUNITY"},
            {}
        )

    opp_type = opp.get("Type")
    opportunity_type = opp_type.lower().replace("_", "-").replace(" ", "-")
    print("opportunity_type======",opportunity_type)
    campaign_name = campaign_map.get(opportunity_type)
    customer_id = input.context.get("customer_id")

    try:

        result = enroll_contact_into_campaign_by_external_id(customer_external_id=customer_id, campaign_name=campaign_name)

        return ActivityOutput(
            {
                "status": "SUCCESS",
                "campaign_name": campaign_name,
                "campaign_result": result
            },
            {}
        )

    except Exception as e:
        return ActivityOutput(
            {
                "status": "FAILED",
                "reason": str(e)
            },
            {}
        )
    
# =========================================================
# 6 AUDIT
# =========================================================
@activity.defn
@log_activity(display_name="08_AUDIT")
async def audit(input: ActivityInput) -> ActivityOutput:
    print(json.dumps(input.payload, indent=2))
    return ActivityOutput({"status": "AUDITED"}, {})


# =========================================================
# WORKFLOW
# =========================================================
@workflow.defn
class CustomerCallWorkflow:

    @workflow.run
    async def run(self, initial_payload: Dict):

        wf_id = workflow.info().workflow_id
        context = build_base_context(initial_payload, wf_id)
        payload = initial_payload.copy()

        # 1 INGEST
        payload, context = await execute_step(ingest_call, payload, context, "INGEST_AUDIO_CALL")

        # 2 TRANSCRIBE
        payload, context = await execute_step(transcribe_call, payload, context, "TRANSCRIBE_AUDIO_CALL")

        # 3 ROUTER
        payload, context = await execute_step(ai_intent_detection, payload, context, "AI_INTENT_DETECTION")

        # 4 EXTRACTOR
        opp_type = payload.get("opportunity_type")

        if not opp_type:
            return {
                "status": "COMPLETED_NO_ACTION",
                "reason": "No intent detected",
                "opportunity": None
            }

        norm_opp_type = opp_type.lower().replace("_", "-").replace(" ", "-")
        print("norm_opp_type======",norm_opp_type)
        if norm_opp_type == "retention":
            payload, context = await execute_step(
                ai_opportunity_retention,
                payload,
                context,
                "RETENTION_EXTRACTOR"
            )

        elif norm_opp_type == "upsell":
            payload, context = await execute_step(
                ai_opportunity_upsell,
                payload,
                context,
                "UPSELL_EXTRACTOR"
            )

        elif norm_opp_type in ("cross-sell", "crosssell"):
            payload, context = await execute_step(
                ai_opportunity_cross_sell,
                payload,
                context,
                "CROSSSELL_EXTRACTOR"
            )
        else:
            raise ValueError(f"Unknown opportunity type: {opp_type}")
        
        # 5 CRM register_sales_opportunity
        payload, context = await execute_step(register_sales_opportunity, payload, context, "REGISTER_SALES_OPPORTUNITY")
        payload, context = await execute_step(salesforce_opportunity_creation, payload, context, "OPPORTUNITY_CREATION")
        payload, context = await execute_step(salesforce_campaign_enrollment, payload, context, "CAMPAIGN_ENROLLMENT")

        # 6 AUDIT
        await execute_step(audit, payload, context, "AUDIT")

        upsert_workflow_instance(
            workflow_id=wf_id,
            workflow_type=payload.get("workflow_type"),
            status="COMPLETED",
            input_data=payload,
            header_id=payload.get("header_id"),
            reference_id=payload.get("reference_id"),
            end_time=workflow.now()
        )

        return {
            "status": "COMPLETED",
            "opportunity": payload.get("opportunity_payload", {})
        }


# =========================================================
# WORKER ENTRYPOINT
# =========================================================
async def main():
    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CustomerCallWorkflow],
        activities=[
            ingest_call,
            transcribe_call,
            ai_intent_detection,
            ai_opportunity_retention,
            ai_opportunity_upsell,
            ai_opportunity_cross_sell,
            register_sales_opportunity,
            salesforce_opportunity_creation,
            salesforce_campaign_enrollment,
            audit
        ],
    )

    async with worker:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())