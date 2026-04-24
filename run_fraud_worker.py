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
TASK_QUEUE = os.getenv("TASK_QUEUE", "fraud-task-queue")


# =====================================================
# WORKFLOW
# =====================================================
@workflow.defn
class FraudWorkflow:

    @workflow.run
    async def run(self, payload: dict):

        print("\n================ FRAUD WORKFLOW START ================\n")
        print(f"[WORKFLOW] Input Payload:\n{payload}\n")

        transaction_id = payload.get("transaction_id", str(uuid.uuid4()))
        amount = payload.get("amount", 0)
        country = payload.get("country", "AU")
        user_id = payload.get("user_id", "unknown")

        print(f"[WORKFLOW] Normalized Input:")
        print(f"  transaction_id = {transaction_id}")
        print(f"  user_id = {user_id}")
        print(f"  amount = {amount}")
        print(f"  country = {country}\n")

        # =================================================
        # STEP 1 - RISK ANALYSIS
        # =================================================
        print("▶ STEP 1: RISK ANALYSIS")

        risk = await workflow.execute_activity(
            analyze_risk,
            {
                "transaction_id": transaction_id,
                "user_id": user_id,
                "amount": amount,
                "country": country,
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print(f"[WORKFLOW] Risk Result: {risk}\n")

        if risk["risk_score"] > 0.7:
            print("❌ FRAUD DETECTED\n")
            return {
                "status": "BLOCKED",
                "reason": "high risk score",
                "risk_score": risk["risk_score"],
            }

        # =================================================
        # STEP 2 - APPROVE TRANSACTION
        # =================================================
        print("▶ STEP 2: APPROVE TRANSACTION")

        await workflow.execute_activity(
            approve_transaction,
            {
                "transaction_id": transaction_id,
                "status": "approved",
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print("✅ FRAUD WORKFLOW COMPLETE\n")

        return {
            "status": "APPROVED",
            "transaction_id": transaction_id,
            "risk_score": risk["risk_score"],
        }


# =====================================================
# ACTIVITIES
# =====================================================
@activity.defn
async def analyze_risk(payload: dict) -> dict:
    print("\n[ACTIVITY] ANALYZE RISK")
    print(f"[INPUT] {payload}")

    # simple mock logic
    risk_score = 0.2

    if payload["amount"] > 10000:
        risk_score += 0.5

    if payload["country"] not in ["AU", "NZ"]:
        risk_score += 0.3

    return {"risk_score": min(risk_score, 1.0)}


@activity.defn
async def approve_transaction(payload: dict):
    print("\n[ACTIVITY] APPROVE TRANSACTION")
    print(f"[INPUT] {payload}")
    print("[ACTIVITY] Transaction APPROVED\n")


# =====================================================
# WORKER BOOTSTRAP
# =====================================================
async def main():

    print("\n🚀 STARTING FRAUD TEMPORAL WORKER")
    print(f"Connecting to: {TEMPORAL_HOST}\n")

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[FraudWorkflow],
        activities=[analyze_risk, approve_transaction],
    )

    print("🟢 Fraud Worker running...\n")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())