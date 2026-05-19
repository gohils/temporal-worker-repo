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
# AI_API_URL = os.getenv("AI_API_URL", "http://localhost:8000")

campaign_map = {
    "retention": "CUSTOMER_RETENTION_PROGRAM",
    "upsell": "CUSTOMER_GROWTH_PROGRAM",
    "crosssell": "REVENUE_EXPANSION_PROGRAM",
    "cross-sell": "REVENUE_EXPANSION_PROGRAM"
}

retention_campaign_map = {
    "VALUE_BUNDLE_RETENTION": "BUNDLE_SAVERS_CAMPAIGN",
    "WHITE_GLOVE_SERVICE_RECOVERY": "SERVICE_UPGRADE_CAMPAIGN",
    "DEVICE_REFRESH_RETENTION": "DEVICE_UPGRADE_CAMPAIGN",
    "PREMIUM_FEATURE_UPSELL": "FEATURE_UNLOCK_RETENTION_CAMPAIGN",
    "VIP_CONCIERGE_RETENTION": "VIP_TREATMENT_CAMPAIGN",
    "PRICE_OBJECTION_RETENTION": "PRICE_OBJECTION_CAMPAIGN"
}

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
async def call_intent_ai(prompt_name, context, options=None):

    async with httpx.AsyncClient(timeout=60) as client:
        payload = {
            "prompt_name": prompt_name,
            "context": context or {},
            "options": options or {}
        }

        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/intent-ai",
            json=payload
        )

    if resp.status_code != 200:
        print("\n==== INTENT AI FAILURE ====")
        print(resp.text)
        print(payload)
        raise Exception(resp.text)

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

def normalize_type(t: str):
    return (t or "").strip().lower().replace("_", "-").replace(" ", "-")

# =========================================================
# DETERMINISTIC CRM FIELD ENGINE (CRITICAL)
# =========================================================
def generate_deterministic_fields(opportunity_type: str):
    """
    Business-controlled CRM fields (NO LLM dependency)
    """

    now = datetime.utcnow()
    opportunity_type_lc = normalize_type(opportunity_type) 
    if opportunity_type_lc == "retention":
        close_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        stage = "At Risk"

    elif opportunity_type_lc == "upsell":
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

    llm_response = await call_intent_ai(
        prompt_name="opportunity_router",
        context={"transcript": input.payload["transcript"]}
    )
    result = llm_response.get("result", llm_response)

    return ActivityOutput(
        {
            "opportunity_type": result.get("opportunity_type"),
            "confidence": result.get("confidence")
        },   {}
    )

# =========================================================
# 4 EXTRACTOR (LLM + BUSINESS ENRICHMENT)
# =========================================================
async def ai_retention_campaign_router(transcript: str):

    try:
        result = await call_intent_ai(
            prompt_name="ai_retention_campaign_router",
            context={
                "transcript": transcript
            }
        )

        print("\n================ NBA refinement raw =================\n",result)

        # 🔒 SAFE ACCESS
        llm_result = result.get("result") or result

        # 🔒 Defensive extraction
        next_best_campaign = llm_result.get("next_best_campaign")

        if not next_best_campaign:
            print("[WARN] next_best_campaign missing from LLM output")
            return None

        return next_best_campaign

    except Exception as e:
        print(f"[ERROR] NBA refinement failed: {e}")
        return None

async def run_opportunity_extractor_core(prompt_name: str, opp_type: str, input: ActivityInput) -> ActivityOutput:

    llm_response = await call_intent_ai(
        prompt_name=prompt_name,
        context={
            "transcript": input.payload["transcript"],
            "account_id": input.context["customer_id"]
        }
    )

    # IMPORTANT FIX
    llm_result = llm_response.get("result", llm_response)

    print("=======run_opportunity_extractor_core======llm result =========",llm_result)
    deterministic = generate_deterministic_fields(opp_type)

    llm_opportunity_type = normalize_type( llm_result.get("opportunity_type") or llm_result.get("Opportunity_Type")  or opp_type )
    next_best_campaign = None
    if llm_opportunity_type == "retention":
        next_best_campaign = await ai_retention_campaign_router(
            transcript=input.payload["transcript"]
        )

        # fallback chain (very important)
        if not next_best_campaign:
            next_best_campaign = "CUSTOMER_RETENTION_PROGRAM"

    return ActivityOutput(
        {
            "opportunity_payload": {
                "Type": opp_type,
                "Name": f"{opp_type} Opportunity - AI",
                "AccountId": input.context["customer_id"],

                **deterministic,

                "Primary_Churn_Driver__c": llm_result.get("Primary_Churn_Driver__c"),
                "Next_Best_Campaign__c": next_best_campaign,
                "Opportunity_Sub_Type__c": llm_result.get("Opportunity_Sub_Type__c"),
                "AI_Call_Summary__c": llm_result.get("AI_Call_Summary__c"),
                "AI_Confidence_Score__c": llm_result.get("AI_Confidence_Score__c", 0),
                "AI_Intent_Strength__c": llm_result.get("AI_Intent_Strength__c"),
                "Competitor_Mentioned__c": llm_result.get("Competitor_Mentioned__c"),
                "Opportunity_Urgency__c": llm_result.get("Opportunity_Urgency__c"),
                "Recommended_Next_Action__c": llm_result.get("Recommended_Next_Action__c"),
            }
        },
        {}
    )


@activity.defn
@log_activity(display_name="04_AI_OPPORTUNITY_RETENTION")
async def ai_opportunity_retention(input: ActivityInput) -> ActivityOutput:
    try:
        return await run_opportunity_extractor_core(
            "opportunity_retention_extractor",
            "Retention",
            input
        )
    except Exception as e:
        return ActivityOutput(
            {
                "opportunity_payload": {
                    "Type": "Retention",
                    "Opportunity_Sub_Type__c": "VALUE_BUNDLE_RETENTION",
                    "AI_Call_Summary__c": "Fallback due to AI failure",
                    "AI_Confidence_Score__c": 0.0
                }
            },
            {}
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
            recommended_next_action=opp.get("Recommended_Next_Action__c"),
            next_best_campaign=opp.get("Next_Best_Campaign__c"),
            primary_churn_driver=opp.get("Primary_Churn_Driver__c"),

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

@activity.defn
@log_activity(display_name="07_CAMPAIGN_ENROLLMENT")
async def salesforce_campaign_enrollment(input: ActivityInput) -> ActivityOutput:

    opp = input.payload.get("opportunity_payload")

    if not opp:
        return ActivityOutput( {"status": "SKIPPED_NO_OPPORTUNITY"}, {}  )

    opp_type = opp.get("Type")
    opportunity_type = opp_type.lower().replace("_", "-").replace(" ", "-")
    print("opportunity_type======",opportunity_type)

    campaign_name = None

    if opportunity_type == "retention":
        nba = opp.get("Next_Best_Campaign__c")

        campaign_name = retention_campaign_map.get(nba)

        if not campaign_name:
            campaign_name = campaign_map.get("retention")
    else:        
        campaign_name = campaign_map.get(opportunity_type)
    customer_id = input.context.get("customer_id")

    print("campaign_name======",campaign_name)

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
    # print(json.dumps(input.payload, indent=2))
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