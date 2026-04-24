import asyncio
from temporalio.client import Client


TEMPORAL_HOST = "temporal-server-demo.australiaeast.cloudapp.azure.com:7233"


# =====================================================
# 1. INVOICE WORKFLOW TRIGGER
# =====================================================
async def trigger_invoice(client: Client):

    print("\n🚀 Triggering Invoice Workflow...\n")

    result = await client.execute_workflow(
        "InvoiceWorkflow",
        {
            "invoice_id": "inv-1001",
            "customer_id": "cust-789",
            "amount": 1500,
            "currency": "AUD",
        },
        id="invoice-test-001",
        task_queue="invoice-task-queue",
    )

    print("✅ Invoice Result:", result)


# =====================================================
# 2. PAYMENT WORKFLOW TRIGGER
# =====================================================
async def trigger_payment(client: Client):

    print("\n🚀 Triggering Payment Workflow...\n")

    result = await client.execute_workflow(
        "PaymentWorkflow",
        {
            "payment_id": "pay-2001",
            "customer_id": "cust-111",
            "amount": 250.75,
            "currency": "AUD",
        },
        id="payment-test-001",
        task_queue="payments-task-queue",
    )

    print("✅ Payment Result:", result)


# =====================================================
# 3. KYC WORKFLOW TRIGGER
# =====================================================
async def trigger_kyc(client: Client):

    print("\n🚀 Triggering KYC Workflow...\n")

    result = await client.execute_workflow(
        "KYCWorkflow",
        {
            "customer_id": "cust-222",
            "document_type": "passport",
            "country": "AU",
        },
        id="kyc-test-001",
        task_queue="kyc-task-queue",
    )

    print("✅ KYC Result:", result)


# =====================================================
# 4. FRAUD WORKFLOW TRIGGER
# =====================================================
async def trigger_fraud(client: Client):

    print("\n🚀 Triggering Fraud Workflow...\n")

    result = await client.execute_workflow(
        "FraudWorkflow",
        {
            "transaction_id": "txn-4002",
            "user_id": "user-999",
            "amount": 15000,
            "country": "NG",
        },
        id="fraud-test-001",
        task_queue="fraud-task-queue",
    )

    print("✅ Fraud Result:", result)


# =====================================================
# MAIN RUNNER (ALL TOGETHER)
# =====================================================
async def main():

    print("\n================ CONNECTING TO TEMPORAL ================\n")

    client = await Client.connect(TEMPORAL_HOST)

    print("✅ Connected to Temporal\n")

    # Run all workflows sequentially
    await trigger_invoice(client)
    await trigger_payment(client)
    await trigger_kyc(client)
    await trigger_fraud(client)

    print("\n🎉 ALL WORKFLOWS COMPLETED\n")


if __name__ == "__main__":
    asyncio.run(main())