# -----------------------------------------
# loan_underwriting_aggregator_worker.py
# -----------------------------------------

import asyncio
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import timedelta

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

# -----------------------------
# SAFE IMPORTS
# -----------------------------
with workflow.unsafe.imports_passed_through():
    from ai_worker_db_log import (
        log_activity,
        upsert_workflow_instance
    )

# -----------------------------
# CONFIG
# -----------------------------
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "loan-underwriting-queue"

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
# CONTEXT HELPERS
# =========================================================
def build_context(payload, wf_id):
    return {
        "workflow_id": wf_id,
        "workflow_type": "LOAN_UNDERWRITING",
        "application_id": payload.get("application_id")
    }


# =========================================================
# 1. LOAD LOAN APPLICATION PROFILE
# =========================================================
@activity.defn
@log_activity(display_name="01_LOAD_LOAN_PROFILE")
async def load_loan_profile(input: ActivityInput) -> ActivityOutput:

    application_id = input.context["application_id"]

    # ---- DB READ (core aggregation source) ----
    # This should be your "automation_process_header + item + document outputs"
    loan_profile = {
        "application_id": application_id,
        "customer": {
            "income": 120000,
            "employment_status": "FULL_TIME"
        },
        "documents": {
            "kyc": "VERIFIED",
            "payslip": "VERIFIED",
            "bank_statement": "VERIFIED"
        },
        "existing_loans": 2,
        "credit_score": 710
    }

    return ActivityOutput(
        {"loan_profile": loan_profile},
        {"profile_loaded": True}
    )


# =========================================================
# 2. UNDERWRITE RISK ENGINE (deterministic rules)
# =========================================================
@activity.defn
@log_activity(display_name="02_UNDERWRITE_RISK")
async def underwrite(input: ActivityInput) -> ActivityOutput:

    profile = input.payload["loan_profile"]

    risk_score = 0.0
    reasons = []

    # Income check
    if profile["customer"]["income"] < 50000:
        risk_score += 0.4
        reasons.append("LOW_INCOME")

    # Credit score check
    if profile["credit_score"] < 650:
        risk_score += 0.4
        reasons.append("LOW_CREDIT_SCORE")

    # Document completeness
    for doc, status in profile["documents"].items():
        if status != "VERIFIED":
            risk_score += 0.2
            reasons.append(f"{doc}_NOT_VERIFIED")

    decision = "APPROVE" if risk_score < 0.5 else "REVIEW" if risk_score < 0.8 else "REJECT"

    return ActivityOutput(
        {
            "risk_score": risk_score,
            "decision": decision,
            "reasons": reasons
        },
        {"risk_evaluated": True}
    )


# =========================================================
# 3. POLICY CHECK (bank rules layer)
# =========================================================
@activity.defn
@log_activity(display_name="03_POLICY_CHECK")
async def policy_check(input: ActivityInput) -> ActivityOutput:

    profile = input.payload["loan_profile"]
    risk = input.payload["risk_score"]

    conditions = []

    if profile["existing_loans"] > 3:
        conditions.append("LIMIT_EXPOSURE")

    if risk > 0.6:
        conditions.append("MANUAL_REVIEW_REQUIRED")

    return ActivityOutput(
        {"conditions": conditions},
        {"policy_checked": True}
    )


# =========================================================
# 4. FINAL UNDERWRITING DECISION
# =========================================================
@activity.defn
@log_activity(display_name="04_FINAL_DECISION")
async def final_decision(input: ActivityInput) -> ActivityOutput:

    risk = input.payload["risk_score"]
    policy_conditions = input.payload.get("conditions", [])

    if "MANUAL_REVIEW_REQUIRED" in policy_conditions:
        decision = "HUMAN_APPROVAL_REQUIRED"
    elif risk < 0.5:
        decision = "AUTO_APPROVE"
    else:
        decision = "REJECT"

    return ActivityOutput(
        {"final_decision": decision},
        {"decision_made": True}
    )


# =========================================================
# 5. WRITE BACK TO LOAN PROFILE (aggregation layer)
# =========================================================
@activity.defn
@log_activity(display_name="05_UPDATE_LOAN_PROFILE")
async def update_profile(input: ActivityInput) -> ActivityOutput:

    # This is where you update:
    # automation_process_header.verification_status
    # or a loan_application_profile table

    return ActivityOutput(
        {"status": "PROFILE_UPDATED"},
        {"db_updated": True}
    )


# =========================================================
# 6. TRIGGER HUMAN UNDERWRITING (if required)
# =========================================================
@activity.defn
@log_activity(display_name="06_TRIGGER_HUMAN_REVIEW")
async def trigger_human_review(input: ActivityInput) -> ActivityOutput:

    return ActivityOutput(
        {"status": "HUMAN_REVIEW_TASK_CREATED"},
        {"human_task": "CREATED"}
    )


# =========================================================
# WORKFLOW
# =========================================================
@workflow.defn
class LoanUnderwritingAggregatorWorkflow:

    @workflow.run
    async def run(self, payload: Dict):

        wf_id = workflow.info().workflow_id
        context = build_context(payload, wf_id)

        # 1. Load aggregated loan profile
        payload, _ = await workflow.execute_activity(
            load_loan_profile,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # 2. Risk engine
        payload, _ = await workflow.execute_activity(
            underwrite,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=30),
        )

        # 3. Policy engine
        payload, _ = await workflow.execute_activity(
            policy_check,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=30),
        )

        # 4. Final decision
        payload, _ = await workflow.execute_activity(
            final_decision,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=30),
        )

        decision = payload["final_decision"]

        # 5. Branching logic
        if decision == "HUMAN_APPROVAL_REQUIRED":
            await workflow.execute_activity(
                trigger_human_review,
                ActivityInput(payload, context),
                start_to_close_timeout=timedelta(seconds=30),
            )

        # 6. Persist results
        await workflow.execute_activity(
            update_profile,
            ActivityInput(payload, context),
            start_to_close_timeout=timedelta(seconds=30),
        )

        # 7. Final DB update
        upsert_workflow_instance(
            workflow_id=wf_id,
            workflow_type="LOAN_UNDERWRITING",
            status="COMPLETED",
            input_data=payload
        )

        return {
            "workflow_id": wf_id,
            "decision": decision,
            "status": "COMPLETED"
        }


# =========================================================
# WORKER
# =========================================================
async def main():

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[LoanUnderwritingAggregatorWorkflow],
        activities=[
            load_loan_profile,
            underwrite,
            policy_check,
            final_decision,
            update_profile,
            trigger_human_review
        ],
    )

    async with worker:
        print("🚀 Loan Underwriting Aggregator Worker running")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())