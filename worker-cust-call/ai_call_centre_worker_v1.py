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
        get_call_transcript
    )

    from salesforce_cc_utils import (
        upsert_opportunity_by_external_id
    )


# =========================================================
# CONFIG
# =========================================================
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "call-centre-ai-queue")
AI_API_URL = os.getenv("AI_API_URL", "http://localhost:8000")


# =========================================================
# CONTRACTS
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


async def execute_step(fn, payload, context, step, timeout=60):
    context = {**context, "current_node_id": step}

    result = await workflow.execute_activity(
        fn,
        ActivityInput(payload, context),
        start_to_close_timeout=timedelta(seconds=timeout),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )

    payload = {**payload, **result.response}
    context = merge_context(context, result.context)

    return payload, context


# =========================================================
# DETERMINISTIC CRM FIELD ENGINE (CRITICAL)
# =========================================================
def generate_deterministic_fields(opportunity_type: str):
    """
    Business-controlled CRM fields (NO LLM dependency)
    """

    now = datetime.utcnow()

    if opportunity_type == "Retention":
        close_date = (now + timedelta(days=3)).strftime("%Y-%m-%d")
        stage = "At Risk"

    elif opportunity_type == "Upsell":
        close_date = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        stage = "Qualification"

    else:  # Cross-sell
        close_date = (now + timedelta(days=10)).strftime("%Y-%m-%d")
        stage = "Qualification"

    return {
        "CloseDate": close_date,
        "StageName": stage,
        "Amount": 0
    }


# =========================================================
# 1 INGEST
# =========================================================
@activity.defn
@log_activity(display_name="01_INGEST")
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
@log_activity(display_name="02_TRANSCRIBE")
async def transcribe_call(input: ActivityInput) -> ActivityOutput:

    audio_url = input.payload["audio_url"]

    cached = get_call_transcript(audio_url)
    if cached:
        return ActivityOutput({"transcript": cached}, {"source": "cache"})

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{AI_API_URL}/transcribe-audio",
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
@log_activity(display_name="03_OPPORTUNITY_ROUTER")
async def opportunity_router(input: ActivityInput) -> ActivityOutput:

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
@log_activity(display_name="04_RETENTION_EXTRACTOR")
async def opportunity_retention_extractor(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_retention_extractor",
        "Retention",
        input
    )

@activity.defn
@log_activity(display_name="04_UPSELL_EXTRACTOR")
async def opportunity_upsell_extractor(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_upsell_extractor",
        "Upsell",
        input
    )

@activity.defn
@log_activity(display_name="04_CROSSSELL_EXTRACTOR")
async def opportunity_cross_sell_extractor(input: ActivityInput) -> ActivityOutput:
    return await run_opportunity_extractor_core(
        "opportunity_cross_sell_extractor",
        "Cross-sell",
        input
    )


# =========================================================
# 5 CRM WRITE (SAFE + ID EMPOTENT)
# =========================================================
# =========================================================
# 5 CRM WRITE
# =========================================================
@activity.defn
@log_activity(display_name="05_CRM_WRITE")
async def create_salesforce_opportunity_if_needed(input: ActivityInput)->ActivityOutput:

    opp=input.payload.get("opportunity_payload")

    if not opp:
        return ActivityOutput({"status":"SKIPPED"},{})

    try:

        customer_id=input.context["customer_id"]

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
            amount=opp.get("Amount",0),

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

# =========================================================
# 6 AUDIT
# =========================================================
@activity.defn
@log_activity(display_name="06_AUDIT")
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
        payload, context = await execute_step(ingest_call, payload, context, "INGEST")

        # 2 TRANSCRIBE
        payload, context = await execute_step(transcribe_call, payload, context, "TRANSCRIBE")

        # 3 ROUTER
        payload, context = await execute_step(opportunity_router, payload, context, "ROUTER")

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
                opportunity_retention_extractor,
                payload,
                context,
                "RETENTION_EXTRACTOR"
            )

        elif norm_opp_type == "upsell":
            payload, context = await execute_step(
                opportunity_upsell_extractor,
                payload,
                context,
                "UPSELL_EXTRACTOR"
            )

        elif norm_opp_type == "cross-sell":
            payload, context = await execute_step(
                opportunity_cross_sell_extractor,
                payload,
                context,
                "CROSSSELL_EXTRACTOR"
            )
        else:
            raise ValueError(f"Unknown opportunity type: {opp_type}")
        
        # 5 CRM
        payload, context = await execute_step(create_salesforce_opportunity_if_needed, payload, context, "CRM")

        # 6 AUDIT
        await execute_step(audit, payload, context, "AUDIT")

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
            opportunity_router,
            opportunity_retention_extractor,
            opportunity_upsell_extractor,
            opportunity_cross_sell_extractor,
            create_salesforce_opportunity_if_needed,
            audit
        ],
    )

    async with worker:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())