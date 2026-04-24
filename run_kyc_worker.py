import os
import asyncio
import uuid
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker


TEMPORAL_HOST = os.getenv(
    "TEMPORAL_HOST",
    "temporal-server-demo.australiaeast.cloudapp.azure.com:7233"
)
TASK_QUEUE = os.getenv("TASK_QUEUE", "kyc-task-queue")


# =====================================================
# WORKFLOW
# =====================================================
@workflow.defn
class KYCWorkflow:

    @workflow.run
    async def run(self, payload: dict):

        print("\n================ KYC WORKFLOW START ================\n")
        print(f"[WORKFLOW] Input Payload:\n{payload}\n")

        customer_id = payload.get("customer_id", "unknown")
        document_type = payload.get("document_type", "passport")
        country = payload.get("country", "AU")

        print(f"[WORKFLOW] Normalized Input:")
        print(f"  customer_id = {customer_id}")
        print(f"  document_type = {document_type}")
        print(f"  country = {country}\n")

        # =================================================
        # STEP 1 - DOCUMENT VALIDATION
        # =================================================
        print("▶ STEP 1: DOCUMENT VALIDATION")

        validation = await workflow.execute_activity(
            validate_documents,
            {
                "customer_id": customer_id,
                "document_type": document_type,
                "country": country,
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print(f"[WORKFLOW] Validation Result: {validation}\n")

        if not validation.get("approved"):
            print("❌ KYC FAILED\n")
            return {
                "status": "REJECTED",
                "reason": validation.get("reason", "invalid documents"),
            }

        # =================================================
        # STEP 2 - AI DOCUMENT PROCESSING
        # =================================================
        print("▶ STEP 2: AI DOCUMENT PROCESSING")

        ai_result = await workflow.execute_activity(
            process_documents,
            {
                "customer_id": customer_id,
                "document_type": document_type,
            },
            start_to_close_timeout=timedelta(seconds=20),
        )

        print(f"[WORKFLOW] AI Result: {ai_result}\n")

        # =================================================
        # STEP 3 - FINAL APPROVAL
        # =================================================
        print("▶ STEP 3: FINAL APPROVAL")

        await workflow.execute_activity(
            finalize_kyc,
            {
                "customer_id": customer_id,
                "status": "approved",
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print("✅ KYC WORKFLOW COMPLETE\n")

        return {
            "status": "APPROVED",
            "customer_id": customer_id,
            "reference_id": str(uuid.uuid4()),
        }


# =====================================================
# ACTIVITIES
# =====================================================
@activity.defn
async def validate_documents(payload: dict) -> dict:
    print("\n[ACTIVITY] VALIDATE DOCUMENTS")
    print(f"[INPUT] {payload}")

    if payload["document_type"] not in ["passport", "license", "id_card"]:
        return {"approved": False, "reason": "unsupported document type"}

    return {"approved": True}


@activity.defn
async def process_documents(payload: dict) -> dict:
    print("\n[ACTIVITY] PROCESS DOCUMENTS")
    print(f"[INPUT] {payload}")

    return {
        "extracted_name": "John Doe",
        "risk_score": 0.12,
        "verification": "passed"
    }


@activity.defn
async def finalize_kyc(payload: dict):
    print("\n[ACTIVITY] FINALIZE KYC")
    print(f"[INPUT] {payload}")
    print("[ACTIVITY] KYC marked as APPROVED\n")


# =====================================================
# WORKER BOOTSTRAP
# =====================================================
async def main():

    print("\n🚀 STARTING KYC TEMPORAL WORKER")
    print(f"Connecting to: {TEMPORAL_HOST}\n")

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[KYCWorkflow],
        activities=[validate_documents, process_documents, finalize_kyc],
    )

    print("🟢 KYC Worker running...\n")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())