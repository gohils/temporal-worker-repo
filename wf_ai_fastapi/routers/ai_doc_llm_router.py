from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import json
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import OpenAI

# Import DB abstraction layer
from wf_ai_fastapi.routers import bpm_prompts
import wf_ai_fastapi.routers.process_db as db

# ---------------------------
# Environment Validation
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_DOC_INT_API_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_DOC_INT_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

if not AZURE_ENDPOINT or not AZURE_API_KEY:
    raise RuntimeError("Azure Document Intelligence credentials not set")

router = APIRouter(
    prefix="/ai_doc_llm",
    tags=["AI Document & LLM"]
)

# ---------------------------
# Clients
# ---------------------------
class AIClients:
    _llm_client = None
    _doc_client = None

    @classmethod
    def llm(cls):
        if cls._llm_client is None:
            cls._llm_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
        return cls._llm_client

    @classmethod
    def doc_ai(cls):
        if cls._doc_client is None:
            cls._doc_client = DocumentAnalysisClient(
                endpoint=os.getenv("AZURE_DOC_INT_API_ENDPOINT"),
                credential=AzureKeyCredential(
                    os.getenv("AZURE_DOC_INT_API_KEY")
                )
            )
        return cls._doc_client

# =========================================================
# REQUEST / RESPONSE
# =========================================================
class AIRequest(BaseModel):
    action: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AIResponse(BaseModel):
    action: str
    final_prompt: str
    result: Dict[str, Any]
    raw_response: Optional[str] = None
    confidence: Optional[float] = None

BUSINESS_SUMMARY_PROMPT = """
You are a business operations assistant.

Convert structured workflow analysis into a SHORT business explanation.

Rules:
- max 3–5 sentences
- no JSON
- simple business language
- no technical terms like "OCR", "workflow_id"
- focus on what happened + current status + next implication

INPUT:
{data}

OUTPUT:
A short business-friendly summary.
"""

# ---------------------------
# LLM AI reasoning Endpoint
# ---------------------------
@router.post("/ai-reasoning", response_model=AIResponse)
async def ai_reasoning(req: AIRequest):
    """Endpoint for AI reasoning on documents with action-aware context building and unified prompt transformation.
            where_in_lifecycle, is_everything_correct, needs_attention, root_cause, what_next
    ```json
    {
        "action": "where_in_lifecycle",
        "context": {
            "workflowId": "INV-20260414-B125B3-202604141803",
            "headerId": 34,
            "referenceId": "INV-20260414-B125B3"
            }
    }
    ```
    """
    try:
        # 1. build transaction context
        header_id = req.context.get("headerId")
        transaction_state_context = bpm_prompts.get_transaction_state(header_id)

        # 2. single unified transformation
        final_prompt = bpm_prompts.build_prompt(req.action, transaction_state_context)

        # 3. LLM call
        response = AIClients.llm().chat.completions.create(
            model=req.options.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Return ONLY JSON."},
                {"role": "user", "content": final_prompt},
            ],
            temperature=0
        )

        raw = response.choices[0].message.content

        try:
            parsed = json.loads(raw)
        except:
            parsed = {"error": "invalid_json", "raw_response": raw}

        return AIResponse(
            action=req.action,
            final_prompt=final_prompt,
            result=parsed,
            raw_response=raw,
            confidence=parsed.get("confidence")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ---------------------------
# OCR Request Model
# ---------------------------
class AnalyzeRequest(BaseModel):
    ai_model_name: str = "prebuilt-read"
    document_url: str = "https://zblobarchive.blob.core.windows.net/samples/aus-passport-sample1.png"
    response_format: str = "plain_text"

# ---------------------------
# Extraction Helpers
# ---------------------------
def extract_plain_text(result):
    return "\n\n".join(
        "\n".join(line.content for line in page.lines) for page in result.pages
    )

def extract_flat_fields(result):
    docs = []
    for doc in result.documents:
        data = {}
        for k, f in (doc.fields or {}).items():
            data[k] = (
                getattr(f, "value_string", None)
                or str(getattr(f, "value_date", None))
                or getattr(f, "value_number", None)
                or getattr(getattr(f, "value_currency", None), "amount", None)
                or getattr(f, "content", None)
            )
        docs.append(data)
    return docs

def extract_structured(result):
    docs = []
    for doc in result.documents:
        header, items = {}, []
        for k, f in doc.fields.items():
            if k.lower() != "items" and hasattr(f, "content"):
                header[k] = f.content
        items_field = doc.fields.get("Items")
        if items_field and hasattr(items_field, "value"):
            for item in items_field.value:
                items.append({k: getattr(v, "content", None) for k, v in item.value.items()})
        docs.append({"header": header, "items": items})
    return docs

# ---------------------------
# OCR Endpoint
# ---------------------------
@router.post("/analyze-document-prebuilt-model")
async def analyze_document(request: AnalyzeRequest):
    """Endpoint to analyze document using specified prebuilt model
       \nai_model_name : prebuilt-read, prebuilt-layout, prebuilt-idDocument, prebuilt-invoice, prebuilt-receipt
      \n return format : plain_text, flat, structured (in header-item format).
    """
    try:
        poller = AIClients.doc_ai().begin_analyze_document_from_url(
            model_id=request.ai_model_name,
            document_url=request.document_url
        )
        result = poller.result()

        if request.response_format == "plain_text":
            extracted = extract_plain_text(result)
        elif request.response_format == "flat":
            extracted = extract_flat_fields(result)
        elif request.response_format == "structured":
            extracted = extract_structured(result)
        else:
            raise HTTPException(400, "Invalid response_format")

        return {
            "model_used": request.ai_model_name,
            "response_format": request.response_format,
            "documents": extracted
        }

    except Exception as e:
        raise HTTPException(500, str(e))
