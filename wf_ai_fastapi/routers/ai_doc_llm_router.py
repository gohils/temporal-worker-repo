from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import json
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import OpenAI
import requests
import io

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

class TranscribeRequest(BaseModel):
    audio_url: str
    workflow_id: Optional[str] = None
    call_id: Optional[str] = None

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
    

# =========================================================
# 1. TRANSCRIPT ANALYSIS
# =========================================================
@router.post("/analyze-transcript")
async def analyze_transcript(req: AIRequest):

    prompt = f"""
    Analyze this call transcript:

    {req.context.get("transcript")}

    Return structured JSON with:
    - summary
    - intent
    - entities
    - key_moments
    """

    response = AIClients.llm().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)


# =========================================================
# 2. CHURN PREDICTION
# =========================================================
@router.post("/churn-prediction")
async def churn_prediction(req: AIRequest):

    prompt = f"""
    Predict churn risk (0 to 1) and reasons:

    {req.context.get("transcript")}

    Return JSON:
    {{
      "churn_score": float,
      "risk_factors": [],
      "confidence": float
    }}
    """

    response = AIClients.llm().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)


# =========================================================
# 3. REVENUE OPPORTUNITY ENGINE
# =========================================================
@router.post("/revenue-opportunity")
async def revenue_opportunity(req: AIRequest):

    prompt = f"""
    Extract upsell and cross-sell opportunities:

    {req.context.get("transcript")}

    Return JSON:
    {{
      "upsell": [],
      "cross_sell": [],
      "intent_strength": float
    }}
    """

    response = AIClients.llm().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)


# =========================================================
# 4. CALL INTELLIGENCE SUMMARY (MASTER)
# =========================================================
@router.post("/call-intelligence-summary")
async def call_intelligence_summary(req: AIRequest):

    prompt = f"""
    Create unified call intelligence:

    {req.context.get("transcript")}

    Return JSON:
    {{
      "call_summary": "",
      "customer_sentiment": "",
      "churn_risk": float,
      "revenue_opportunity": "",
      "recommended_action": ""
    }}
    """

    response = AIClients.llm().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)


# =========================================================
# 5. SALESFORCE PAYLOAD GENERATOR
# =========================================================
@router.post("/generate-salesforce-payload")
async def generate_salesforce_payload(req: AIRequest):

    prompt = f"""
    Convert this call intelligence into CRM payload for Salesforce:

    {req.context.get("structured_data")}

    Return JSON formatted for CRM ingestion.
    """

    response = AIClients.llm().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)

@router.post("/transcribe-audio")
async def transcribe_audio(req: TranscribeRequest):
    """
    Stateless transcription endpoint.
    Input:
    {  "audio_url": "https://zblobarchive.blob.core.windows.net/samples/call_cancellation_chat_sample1.wav"     }
    """

    audio_url = req.audio_url

    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url is required")

    try:
        # -------------------------------------------------
        # 1. Download audio into memory (NO DISK)
        # -------------------------------------------------
        response = requests.get(audio_url, timeout=30)
        response.raise_for_status()

        audio_bytes = io.BytesIO(response.content)
        audio_bytes.name = "audio.wav"  # required by OpenAI SDK

        # -------------------------------------------------
        # 2. Whisper transcription
        # -------------------------------------------------
        client = AIClients.llm()

        transcript_response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_bytes
        )

        transcript = transcript_response.text

        print("Transcription result:", transcript)

        if not transcript:
            raise HTTPException(
                status_code=500,
                detail="Transcription failed"
            )

        # -------------------------------------------------
        # 3. Return result (stateless)
        # -------------------------------------------------
        return {
            "audio_url": audio_url,
            "transcript": transcript,
            "workflow_id": req.workflow_id,
            "call_id": req.call_id
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Audio download failed: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Transcription error: {str(e)}"
        )