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
TASK_QUEUE = os.getenv("TASK_QUEUE", "invoice-task-queue")


# =====================================================
# WORKFLOW
# =====================================================
@workflow.defn
class InvoiceWorkflow:

    @workflow.run
    async def run(self, payload: dict):

        print("\n================ INVOICE WORKFLOW START ================\n")
        print(f"[WORKFLOW] Input Payload:\n{payload}\n")

        invoice_id = payload.get("invoice_id", str(uuid.uuid4()))
        customer_id = payload.get("customer_id", "unknown")
        amount = payload.get("amount", 0)
        currency = payload.get("currency", "AUD")

        print(f"[WORKFLOW] Normalized Input:")
        print(f"  invoice_id = {invoice_id}")
        print(f"  customer_id = {customer_id}")
        print(f"  amount = {amount}")
        print(f"  currency = {currency}\n")

        # =================================================
        # STEP 1 - INVOICE VALIDATION
        # =================================================
        print("▶ STEP 1: VALIDATE INVOICE")

        validation = await workflow.execute_activity(
            validate_invoice,
            {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "amount": amount,
                "currency": currency,
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print(f"[WORKFLOW] Validation Result: {validation}\n")

        if not validation.get("approved"):
            print("❌ INVOICE REJECTED\n")
            return {
                "status": "REJECTED",
                "reason": validation.get("reason", "validation failed"),
            }

        # =================================================
        # STEP 2 - TAX CALCULATION
        # =================================================
        print("▶ STEP 2: TAX CALCULATION")

        tax_result = await workflow.execute_activity(
            calculate_tax,
            {
                "invoice_id": invoice_id,
                "amount": amount,
                "currency": currency,
            },
            start_to_close_timeout=timedelta(seconds=15),
        )

        print(f"[WORKFLOW] Tax Result: {tax_result}\n")

        # =================================================
        # STEP 3 - GENERATE PDF INVOICE
        # =================================================
        print("▶ STEP 3: GENERATE PDF")

        pdf_result = await workflow.execute_activity(
            generate_pdf_invoice,
            {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "amount": amount,
                "tax": tax_result["tax_amount"],
                "currency": currency,
            },
            start_to_close_timeout=timedelta(seconds=20),
        )

        print(f"[WORKFLOW] PDF Result: {pdf_result}\n")

        # =================================================
        # STEP 4 - SEND INVOICE
        # =================================================
        print("▶ STEP 4: SEND INVOICE")

        await workflow.execute_activity(
            send_invoice,
            {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "pdf_url": pdf_result["pdf_url"],
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        print("✅ INVOICE WORKFLOW COMPLETE\n")

        return {
            "status": "SUCCESS",
            "invoice_id": invoice_id,
            "pdf_url": pdf_result["pdf_url"],
        }


# =====================================================
# ACTIVITIES
# =====================================================
@activity.defn
async def validate_invoice(payload: dict) -> dict:
    print("\n[ACTIVITY] VALIDATE INVOICE")
    print(f"[INPUT] {payload}")

    if payload["amount"] <= 0:
        return {"approved": False, "reason": "invalid invoice amount"}

    return {"approved": True}


@activity.defn
async def calculate_tax(payload: dict) -> dict:
    print("\n[ACTIVITY] CALCULATE TAX")
    print(f"[INPUT] {payload}")

    tax_rate = 0.10
    tax_amount = payload["amount"] * tax_rate

    result = {
        "tax_amount": tax_amount
    }

    print(f"[OUTPUT] {result}\n")
    return result


@activity.defn
async def generate_pdf_invoice(payload: dict) -> dict:
    print("\n[ACTIVITY] GENERATE PDF INVOICE")
    print(f"[INPUT] {payload}")

    pdf_url = f"https://invoices.example.com/{payload['invoice_id']}.pdf"

    result = {
        "pdf_url": pdf_url
    }

    print(f"[OUTPUT] {result}\n")
    return result


@activity.defn
async def send_invoice(payload: dict):
    print("\n[ACTIVITY] SEND INVOICE")
    print(f"[INPUT] {payload}")
    print("[ACTIVITY] Invoice sent successfully\n")


# =====================================================
# WORKER BOOTSTRAP
# =====================================================
async def main():

    print("\n🚀 STARTING INVOICE TEMPORAL WORKER")
    print(f"Connecting to: {TEMPORAL_HOST}\n")

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[InvoiceWorkflow],
        activities=[
            validate_invoice,
            calculate_tax,
            generate_pdf_invoice,
            send_invoice,
        ],
    )

    print("🟢 Invoice Worker running...\n")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())