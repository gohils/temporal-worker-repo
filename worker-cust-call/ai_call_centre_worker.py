# -----------------------------
# ai_call_centre_worker.py (REFRACTORED)
# -----------------------------

import asyncio, json, os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

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


# -----------------------------
# ENV
# -----------------------------
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "call-centre-ai-queue")
AI_API_URL = os.getenv("AI_API_URL", "http://localhost:8000")
SALESFORCE_API = os.getenv("SALESFORCE_API", "https://salesforce.com/api")


# -----------------------------
# CONTRACTS
# -----------------------------
@dataclass
class ActivityInput:
    payload: Dict[str, Any]
    context: Dict[str, Any]


@dataclass
class ActivityOutput:
    response: Dict[str, Any]
    context: Dict[str, Any]


# -----------------------------
# CONTEXT
# -----------------------------
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


# -----------------------------
# EXECUTION WRAPPER
# -----------------------------
async def execute_step(activity_fn, payload, context, step, timeout=60):

    context = {**context, "current_node_id": step}

    result: ActivityOutput = await workflow.execute_activity(
        activity_fn,
        ActivityInput(payload, context),
        start_to_close_timeout=timedelta(seconds=timeout),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )

    payload = {**payload, **result.response}
    context = merge_context(context, result.context)

    return payload, context


# =========================================================
# ACTIVITIES
# =========================================================

# -----------------------------
# 1. CALL INGESTION
# -----------------------------
@activity.defn
@log_activity(display_name="01_CALL_INGEST")
async def ingest_call(input: ActivityInput) -> ActivityOutput:

    return ActivityOutput(
        {
            "call_record": {
                "call_id": input.context["call_id"],
                "audio_url": input.payload["audio_url"],
                "customer_id": input.context["customer_id"],
                "agent_id": input.payload.get("agent_id")
            }
        },
        {}
    )


# -----------------------------
# 2. TRANSCRIPTION (IDEMPOTENT + DB CACHE)
# -----------------------------
@activity.defn
@log_activity(display_name="02_TRANSCRIBE")
async def transcribe_call(input: ActivityInput) -> ActivityOutput:

    audio_url = input.payload["call_record"]["audio_url"]
    call_id = input.context["call_id"]

    # 1. CHECK DB CACHE FIRST (IMPORTANT)
    cached = get_call_transcript(audio_url)
    if cached:
        return ActivityOutput(
            {"transcript": cached},
            {"source": "cache"}
        )

    # 2. CALL TRANSCRIPTION SERVICE
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/transcribe-audio",
            json={"audio_url": audio_url}
        )
        resp.raise_for_status()

        print(f"Transcription response: {resp.json()}")
        transcript = resp.json()["transcript"]

    # 3. STORE IN POSTGRES (CRITICAL)
    store_call_transcript(
        workflow_id=input.context["workflow_id"],
        call_id=call_id,
        audio_url=audio_url,
        transcript=transcript
    )

    return ActivityOutput(
        {"transcript": transcript},
        {"source": "whisper"}
    )


# -----------------------------
# 3. CHURN PREDICTION
# -----------------------------
@activity.defn
@log_activity(display_name="03_CHURN_PREDICTION")
async def churn_prediction(input: ActivityInput) -> ActivityOutput:

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/llm/churn-predict",
            json={"text": input.payload["transcript"]}
        )
        resp.raise_for_status()
        churn = resp.json()

    return ActivityOutput(
        {
            "churn_score": churn["score"],
            "churn_reason": churn.get("reason")
        },
        {}
    )


# -----------------------------
# 4. UPSELL / CROSS-SELL
# -----------------------------
@activity.defn
@log_activity(display_name="04_REVENUE_OPPORTUNITY")
async def detect_opportunities(input: ActivityInput) -> ActivityOutput:

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/llm/revenue-opportunity",
            json={"text": input.payload["transcript"]}
        )
        resp.raise_for_status()
        opp = resp.json()

    return ActivityOutput(
        {
            "cross_sell": opp.get("cross_sell", []),
            "upsell": opp.get("upsell", [])
        },
        {}
    )


# -----------------------------
# 5. SALESFORCE SYNC (ISOLATED SIDE EFFECT)
# -----------------------------
@activity.defn
@log_activity(display_name="05_SALESFORCE_SYNC")
async def sync_salesforce(input: ActivityInput) -> ActivityOutput:

    payload = {
        "customer_id": input.context["customer_id"],
        "call_id": input.context["call_id"],
        "churn_score": input.payload.get("churn_score"),
        "cross_sell": input.payload.get("cross_sell"),
        "upsell": input.payload.get("upsell"),
        "timestamp": datetime.utcnow().isoformat()
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{SALESFORCE_API}/customer-insights",
            json=payload
        )
        resp.raise_for_status()

    return ActivityOutput({"salesforce_sync": "SUCCESS"}, {})


# -----------------------------
# 6. AUDIT
# -----------------------------
@activity.defn
@log_activity(display_name="06_AUDIT")
async def audit(input: ActivityInput) -> ActivityOutput:
    print(json.dumps(input.payload, indent=2))
    return ActivityOutput({"status": "AUDITED"}, {})


# =========================================================
# WORKFLOW
# =========================================================

@workflow.defn
class CallCentreAIWorkflow:

    @workflow.run
    async def run(self, initial_payload: Dict):

        wf_id = workflow.info().workflow_id
        context = build_base_context(initial_payload, wf_id)
        payload = initial_payload.copy()

        # 1. ingest
        payload, context = await execute_step(ingest_call, payload, context, "01_INGEST")

        # 2. transcribe (cached + stored)
        payload, context = await execute_step(transcribe_call, payload, context, "02_TRANSCRIBE")

        # 3. churn
        payload, context = await execute_step(churn_prediction, payload, context, "03_CHURN")

        # 4. revenue opportunities
        payload, context = await execute_step(detect_opportunities, payload, context, "04_OPPORTUNITY")

        # 5. Salesforce sync
        payload, context = await execute_step(sync_salesforce, payload, context, "05_SALESFORCE")

        # 6. audit
        await execute_step(audit, payload, context, "06_AUDIT")

        # workflow persistence
        upsert_workflow_instance(
            workflow_id=wf_id,
            workflow_type=payload.get("workflow_type"),
            status="COMPLETED",
            input_data=payload,
            header_id=payload.get("call_id"),
            reference_id=payload.get("customer_id"),
            end_time=workflow.now()
        )

        return {
            "status": "COMPLETED",
            "churn_score": payload.get("churn_score"),
            "cross_sell": payload.get("cross_sell"),
            "upsell": payload.get("upsell")
        }


# =========================================================
# WORKER
# =========================================================

async def main():
    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CallCentreAIWorkflow],
        activities=[
            ingest_call,
            transcribe_call,
            churn_prediction,
            detect_opportunities,
            sync_salesforce,
            audit
        ],
    )

    async with worker:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())