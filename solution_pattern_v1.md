# 🧠 Intelligent Document & Loan Automation Pattern (Temporal + OCR + LLM + Rules)

## 1. Core Idea

This architecture separates:

* **Deterministic orchestration (Temporal + rules + DB state)**
* **Probabilistic intelligence (LLM + OCR + extraction models)**
* **Human decision points (loan officer / reviewer)**
* **Batch + event-driven execution models**

Instead of “AI-driven workflow”, this is:

> **A deterministic workflow engine augmented with probabilistic intelligence at bounded steps**

---

# 2. High-Level Architecture

```
                ┌────────────────────────────┐
                │ Loan Application Workflow  │
                │ (Header-level orchestration)│
                └─────────────┬──────────────┘
                              │
              fetch items (DB / batch / event)
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
┌───────▼────────┐                        ┌────────▼────────┐
│ automation      │                        │ human triggers   │
│_process_item    │                        │ (loan officer)   │
└───────┬─────────┘                        └────────┬────────┘
        │                                            │
        ▼                                            ▼
┌────────────────────────────────────────────────────────────┐
│ Document Processing Pipeline (per item, Temporal Worker)   │
├────────────────────────────────────────────────────────────┤
│ 1. OCR (Azure / AWS / custom model)                        │
│ 2. LLM Extraction (generic endpoint)                       │
│ 3. Rules Engine (deterministic validation)                │
│ 4. Profile Update (DB / CRM / ERP)                        │
│ 5. Audit + Traceability                                   │
└────────────────────────────────────────────────────────────┘
```

---

# 3. Two-Level Workflow Design (IMPORTANT)

## A. LoanApplicationWorkflow (HEADER LEVEL)

**Purpose:**

* Controls the whole loan application
* Manages lifecycle state
* Does NOT process documents directly

### Responsibilities:

* Load header (`automation_process_header`)
* Load items (`automation_process_item`)
* Decide when processing starts
* Trigger batch processing (or wait for manual trigger)
* Aggregate final decision

### Key principle:

> This workflow is **NOT doing AI work**

It is orchestration + business state only.

---

## B. LoanDocumentWorkflow (ITEM LEVEL)

**Purpose:**

* Processes ONE document per execution
* Fully independent, stateless execution unit

### Input:

```json
{
  "header_id": 35,
  "item_id": 57
}
```

### Responsibilities:

* Fetch document URL from DB
* Run OCR
* Run LLM extraction
* Run validation rules
* Store outputs
* Update item state

---

# 4. Data Flow (Correct Pattern)

## Step 1 — Loan Officer or Batch Trigger

```
LoanApplicationWorkflow
        │
        ▼
SELECT * FROM automation_process_item
WHERE header_id = 35 AND status = 'PROCESSING'
```

## Step 2 — Each item triggers workflow

```
for item in items:
    start LoanDocumentWorkflow(header_id, item_id)
```

---

# 5. Why THIS is the correct separation

## ❌ Wrong pattern (what you initially had)

* One workflow loops over multiple documents
* Mixes DB, OCR, LLM, orchestration
* Hard to retry per document
* Hard to scale
* Hard to parallelize

---

## ✅ Correct pattern (this design)

| Layer           | Responsibility      |
| --------------- | ------------------- |
| Header workflow | orchestration       |
| Item workflow   | document processing |
| OCR service     | extraction          |
| LLM service     | intelligence        |
| DB              | state               |

---

# 6. LLM Integration Pattern (Generic Endpoint)

You correctly standardized this:

```python
resp = await client.post(
    f"{AI_API_URL}/ai_doc_llm/execute_llm",
    json={
        "prompt": prompt,
        "context": {
            "document_text": raw_text
        }
    }
)
```

### Why this is good:

* No workflow coupling to model type
* Can swap GPT / Claude / local LLM
* Same contract across all workflows
* Enables reuse across banking, insurance, claims

---

# 7. Deterministic + Probabilistic Split

## Deterministic layer (NO AI)

* workflow routing
* item selection
* retries
* approvals
* SLA tracking
* status transitions

## Probabilistic layer (AI)

* OCR
* document understanding
* field extraction
* classification
* summarization

---

# 8. Human-in-the-loop pattern (important for loans)

```
OCR → LLM → Rules Engine → Decision
                           ↓
                     If uncertain
                           ↓
                 workflow_approval_task
                           ↓
                    Loan officer review
```

---

# 9. Database mapping (correct usage)

## automation_process_header

* Loan application level
* One row per customer/application

## automation_process_item

* One row per document
* THIS is what workflows process

## workflow_ocr_data

* raw + extracted OCR output

## erp_crm_documents

* final structured output

---

# 10. Execution modes (VERY IMPORTANT)

## Mode A — Batch mode (overnight)

```
LoanApplicationWorkflow
   → fetch all items
   → start document workflows in parallel
```

## Mode B — Manual trigger (loan officer)

```
UI → triggers LoanDocumentWorkflow per item
```

## Mode C — Event-driven (future)

```
document uploaded → trigger item workflow automatically
```

---

# 11. Why this pattern is industry-grade

This is exactly aligned with:

### Banking

* Loan origination systems
* KYC processing
* Mortgage document pipelines

### Insurance

* Claims ingestion
* Fraud detection pipelines

### Enterprise BPM

* SAP workflow extensions
* Pega-like orchestration model

---

# 12. Key design principle (most important takeaway)

> “Workflows should orchestrate decisions, not execute intelligence.”

Temporal = deterministic brain
LLM = probabilistic assistant
DB = system of record

---

# 13. What you have now (correct direction)

You are now building:

### ✔ Event-driven document intelligence pipeline

### ✔ Header → Item → Document decomposition

### ✔ AI augmentation layer (not AI control layer)

### ✔ Human approval integration ready

### ✔ Scalable per-document execution model
