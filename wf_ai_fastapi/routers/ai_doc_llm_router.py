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
from datetime import datetime

# Import DB abstraction layer
from wf_ai_fastapi.routers import bpm_prompts
import wf_ai_fastapi.routers.process_db as db
from wf_ai_fastapi.routers import ai_cc_salesforce_prompt

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
class AIReasoningRequest(BaseModel):
    action: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AIReasoningResponse(BaseModel):
    action: str
    final_prompt: str
    result: Dict[str, Any]
    raw_response: Optional[str] = None
    confidence: Optional[float] = None


class TranscribeRequest(BaseModel):
    audio_url: str
    workflow_id: Optional[str] = None
    call_id: Optional[str] = None

class IntentAIRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AIIntentResponse(BaseModel):
    result: Dict[str, Any]
    model: str
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
@router.post("/ai-reasoning", response_model=AIReasoningResponse)
async def ai_reasoning(req: AIReasoningRequest):
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

        return AIReasoningResponse(
            action=req.action,
            final_prompt=final_prompt,
            result=parsed,
            raw_response=raw,
            confidence=parsed.get("confidence")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

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
    

# =========================================================
# PROMPT BUILDER
# =========================================================

def render_prompt(template: str, data: Dict[str, Any]):

    try:
        return template.format(**data)

    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing template variable: {e}"
        )


# =========================================================
# GENERIC AI ENDPOINT
# =========================================================

@router.post("/intent-ai", response_model=AIIntentResponse)
async def intent_ai(req: IntentAIRequest):
    """
    {
        "system_prompt": "customer_intelligence",
        "user_prompt": "call_summary",
            "context": {
                "transcript": "Customer said they are unhappy with pricing and considering competitor offers."
            }
    }

    {
    "system_prompt": "opportunity_upsell_extractor",
    "user_prompt": "opportunity_upsell_extractor",
        "context": {
            "transcript": "Customer wants to upgrade from basic plan to enterprise plan due to scaling needs",
            "account_id": "001ABC123"
        }
    }    
    """
    started = datetime.utcnow()

    system_template = ai_cc_salesforce_prompt.SYSTEM_PROMPTS.get(req.system_prompt)
    user_template = ai_cc_salesforce_prompt.USER_PROMPTS.get(req.user_prompt)

    merged = req.context or {}

    system_prompt = system_template
    user_prompt = render_prompt(user_template, merged)
    model= (req.options or {}).get("model", "gpt-4o-mini")
    response = AIClients.llm().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0
        )

    raw = response.choices[0].message.content

    try:
        parsed = json.loads(raw)

    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON returned: {raw}"
        )

    return AIIntentResponse(
        result=parsed,
        model=model,
        confidence=parsed.get("AI_Confidence_Score__c")
    )