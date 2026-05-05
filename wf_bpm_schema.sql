CREATE TABLE process_registry (
    process_name TEXT PRIMARY KEY, --e.g., KYC, Billing, Payroll

    -- =========================
    -- HUMAN BUSINESS CONTEXT
    -- =========================
    process_context JSONB NOT NULL,

    -- =========================
    -- WORKFLOW ENGINE VIEW
    -- =========================
    workflow_type TEXT,          -- e.g., Customer Onboarding, Invoice Processing, Payroll
    workflow_definition JSONB NOT NULL,

    -- =========================
    -- LLM LIFECYCLE SUMMARY
    -- =========================
    lifecycle_summary JSONB NOT NULL,

    -- =========================
    -- LLM BEHAVIOR TUNING
    -- =========================
    critical_steps JSONB,
    risk_stages JSONB,

    -- metadata
    version TEXT DEFAULT 'v1',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 🧾 5. SQL INSERTS for YOUR TWO WORKFLOWS
-- 🧾 Invoice Processing
INSERT INTO process_registry (
    process_name,
    process_context,
    workflow_type,
    workflow_definition,
    lifecycle_summary,
    critical_steps,
    risk_stages
)
VALUES (
'Invoice Processing',

'{
  "process_name": "Invoice Processing",
  "business_goal": "Process supplier invoices and post to ERP after validation",
  "actors": ["Finance User", "System", "Approver"],
  "entry_trigger": "Invoice document uploaded",
  "exit_condition": "ERP posting completed or rejection logged"
}',
'InvoiceProcessingWorkflow',
'{
  "expected_flow": [
    "01_PREPROCESS_INVOICE",
    "02_OCR",
    "03_NORMALIZE",
    "04_VALIDATE",
    "05_DECISION",
    "06_ERP",
    "07_AUDIT"
  ],
  "step_meaning": {
    "01_PREPROCESS_INVOICE": "Document ingestion and normalization",
    "02_OCR": "AI extraction of invoice data",
    "03_NORMALIZE": "Standardization of extracted fields",
    "04_VALIDATE": "Business rule validation",
    "05_DECISION": "Approval or rejection decision",
    "06_ERP": "Posting to ERP system",
    "07_AUDIT": "Audit logging"
  }
}',

'{
  "flow": [
    "Document received",
    "OCR extraction",
    "Data normalization",
    "Validation",
    "Approval decision",
    "ERP posting",
    "Audit logging"
  ],
  "narrative": "Invoice is ingested → OCR extracts data → validated → approved → posted to ERP → audited"
}',

'["04_VALIDATE","05_DECISION","06_ERP"]',

'{
  "HIGH_RISK": ["05_DECISION", "06_ERP"],
  "MEDIUM_RISK": ["04_VALIDATE"],
  "LOW_RISK": ["01_PREPROCESS_INVOICE", "02_OCR", "07_AUDIT"]
}'
);

-- 🧾 KYC / Customer Onboarding
INSERT INTO process_registry (
    process_name,
    process_context,
    workflow_type,
    workflow_definition,
    lifecycle_summary,
    critical_steps,
    risk_stages
)
VALUES (
'Customer Onboarding',

'{
  "process_name": "Customer Onboarding / KYC",
  "business_goal": "Verify customer identity and compliance before onboarding",
  "actors": ["Compliance Officer", "System", "Risk Engine"],
  "entry_trigger": "Customer document submission",
  "exit_condition": "KYC approved or rejected"
}',

'CustomerOnboardingWorkflow',
'{
  "expected_flow": [
    "01_PREPROCESS",
    "02_CLASSIFY",
    "03_OCR",
    "04_VALIDATE",
    "05_CROSS_VERIFY",
    "06_APPROVAL",
    "07_ERP",
    "08_AUDIT"
  ],
  "step_meaning": {
    "01_PREPROCESS": "Document ingestion",
    "02_CLASSIFY": "Identify document type",
    "03_OCR": "Extract identity data",
    "04_VALIDATE": "Validate extracted information",
    "05_CROSS_VERIFY": "Cross-check with external systems",
    "06_APPROVAL": "Risk-based approval decision",
    "07_ERP": "Store verified customer record",
    "08_AUDIT": "Audit logging"
  }
}',

'{
  "flow": [
    "Document received",
    "Classification",
    "OCR extraction",
    "Validation",
    "Cross verification",
    "Approval decision",
    "Customer onboarding completion",
    "Audit logging"
  ],
  "narrative": "Customer documents flow through classification → OCR → validation → risk check → approval → onboarding"
}',

'["04_VALIDATE","05_CROSS_VERIFY","06_APPROVAL"]',

'{
  "HIGH_RISK": ["05_CROSS_VERIFY", "06_APPROVAL"],
  "MEDIUM_RISK": ["04_VALIDATE"],
  "LOW_RISK": ["01_PREPROCESS", "02_OCR", "08_AUDIT"]
}'
);

SELECT * FROM process_registry;