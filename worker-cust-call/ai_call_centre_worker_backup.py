# -----------------------------
# ai_call_centre_worker.py (PRODUCTION FIXED)
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
        upsert_opportunity_by_account
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
async def call_intent_ai(
    system_prompt: str,
    user_prompt: str,
    context: dict,
    parameters: dict = None,
    expected_output: dict = None
):
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/intent-ai",
            json={
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "context": context,
                "parameters": parameters or {},
                "expected_output": expected_output
            }
        )

    resp.raise_for_status()
    return resp.json()
    
def build_base_context(payload, wf_id):
    return {
        "workflow_id": wf_id,
        "workflow_type": payload.get("workflow_type"),
        "customer_id": payload.get("customer_id"),
        "call_id": payload.get("call_id"),
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

def safe_list(v):
    if not v:
        return []
    if isinstance(v, list):
        return [x for x in v if x]  # remove empty dicts/nulls
    return [v]

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
        {
            "call_record": {
                "audio_url": document_url
            }
        },
        {}
    )


# =========================================================
# 2 TRANSCRIBE
# =========================================================
@activity.defn
@log_activity(display_name="02_TRANSCRIBE")
async def transcribe_call(input: ActivityInput) -> ActivityOutput:

    audio_url = input.payload["call_record"]["audio_url"]

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
# 3 PARALLEL AI LAYER
# =========================================================
@activity.defn
@log_activity(display_name="03_CHURN")
async def churn_prediction(input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt="customer_intelligence",
        user_prompt="churn_prediction",
        context={"transcript": input.payload["transcript"]},
        expected_output={
            "churn_score": "float",
            "confidence": "float"
        }
    )
    return ActivityOutput(
        {
            "churn_score": float(result["result"].get("churn_score") or 0),
            "confidence": float(result["result"].get("confidence") or 0)
        },
        {}
    )


@activity.defn
@log_activity(display_name="03_CROSS_SELLING")
async def cross_sell_prediction(input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt="customer_intelligence",
        user_prompt="cross_sell_prediction",
        context={"transcript": input.payload["transcript"]},
    )

    return ActivityOutput(
        {
            "cross_sell": safe_list(result["result"].get("cross_sell")),
            "confidence": result["result"].get("confidence", 0)
        },
        {}
    )

@activity.defn
@log_activity(display_name="03_UP_SELLING")
async def upsell_prediction(input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt="customer_intelligence",
        user_prompt="upsell_prediction",
        context={"transcript": input.payload["transcript"]},
    )

    return ActivityOutput(
        {
            "upsell": safe_list(result["result"].get("upsell")),
            "confidence": result["result"].get("confidence", 0)
        },
        {}
    )


@activity.defn
@log_activity(display_name="03_CALL_SUMMARY")
async def call_summary(input: ActivityInput) -> ActivityOutput:

    result = await call_intent_ai(
        system_prompt="customer_intelligence",
        user_prompt="call_summary",
        context={"transcript": input.payload["transcript"]},
    )

    result_output =     {
        "summary": result["result"].get("call_summary", "")
    }
    return ActivityOutput(result_output, {})

# =========================================================
# 5 DECISION ENGINE
# =========================================================
@activity.defn
@log_activity(display_name="05_CRM_DECISION_ENGINE")
async def crm_decision_engine(input: ActivityInput) -> ActivityOutput:

    churn = float(input.payload.get("churn_score") or 0)

    upsell = safe_list(input.payload.get("upsell"))
    cross_sell = safe_list(input.payload.get("cross_sell"))

    create_opportunity = False
    reasons = []
    if churn >= 0.6:
        reasons.append("high_churn_risk")

    if upsell or cross_sell:
        reasons.append("revenue_signal")

    create_opportunity = len(reasons) > 0

    return ActivityOutput(
        {
            "crm": {
                "create_opportunity": create_opportunity,
                "reasons": reasons
            }
        },
        {}
    )


# =========================================================
# 6 CRM ROUTER (ONLY OPPORTUNITY)
# =========================================================
@activity.defn
@log_activity(display_name="06_CRM_ROUTER")
async def create_opportunity_if_needed(input: ActivityInput) -> ActivityOutput:
    print("CRM DECISION: input", input)
    crm = input.payload.get("crm", {})

    if str(crm.get("create_opportunity")).lower() != "true":
        return ActivityOutput({"opportunity": "SKIPPED"}, {})

    try:
        result = upsert_opportunity_by_account(
            CUSTOMER_EXTERNAL_ID=input.context["customer_id"],
            opp_type="CALL_AI_OPPORTUNITY",
            amount=0
        )

        return ActivityOutput(
            {"status": "SUCCESS", "salesforce_result": result},
            {"salesforce": {"status": "SUCCESS"}}
        )

    except Exception as e:
        print("========salesfoce API error=====\n",str(e))
        return ActivityOutput(
            {"status": "SKIPPED", "reason": str(e)},
            {"salesforce": {"status": "SKIPPED"}}
        )
    


# =========================================================
# 7 AUDIT
# =========================================================
@activity.defn
@log_activity(display_name="07_AUDIT")
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

        # 3 PARALLEL (Temporal-safe)
        churn_future = workflow.execute_activity(
            churn_prediction,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=60),
        )

        cross_future = workflow.execute_activity(
            cross_sell_prediction,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=60),
        )

        upsell_future = workflow.execute_activity(
            upsell_prediction,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=60),
        )

        summary_future = workflow.execute_activity(
            call_summary,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=60),
        )

        churn, cross_sell, upsell, summary = await asyncio.gather(
            churn_future,
            cross_future,
            upsell_future,
            summary_future
        )

        payload.update({
            "churn_score": getattr(churn, "response", {}).get("churn_score", 0),
            "cross_sell": getattr(cross_sell, "response", {}).get("cross_sell", []),
            "upsell": getattr(upsell, "response", {}).get("upsell", []),
            "summary": getattr(summary, "response", {}).get("summary", "")
        })

        # 5 DECISION
        payload, context = await execute_step(crm_decision_engine, payload, context, "DECISION")

        # 6 CRM
        payload, context = await execute_step(create_opportunity_if_needed, payload, context, "CRM")

        # 7 AUDIT
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
            "churn_score": payload.get("churn_score"),
            "opportunity": payload.get("crm", {})
        }


# =========================================================
# WORKER
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
            churn_prediction,
            upsell_prediction,
            cross_sell_prediction,
            call_summary,
            crm_decision_engine,
            create_opportunity_if_needed,
            audit
        ],
    )

    async with worker:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())