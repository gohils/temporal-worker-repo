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
import wf_ai_fastapi.routers.prompts.ai_cc_salesforce_prompt as ai_cc_salesforce_prompt
import wf_ai_fastapi.routers.prompts.registry as prompts_registry
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
# =========================================================
# REQUEST (MINIMAL)
# =========================================================
class LLMRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    model: str = "gpt-4o-mini"
    temperature: float = 0.0


# =========================================================
# RESPONSE (MINIMAL)
# =========================================================
class LLMResponse(BaseModel):
    result: Any
    raw_response: Optional[str]
    prompt_used: str

class TranscribeRequest(BaseModel):
    audio_url: str
    workflow_id: Optional[str] = None
    call_id: Optional[str] = None

class IntentAIRequest(BaseModel):
    prompt_name: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AIIntentResponse(BaseModel):
    result: Dict[str, Any]
    model: str
    confidence: Optional[float] = None

# ---------------------------
# LLM AI generic Endpoint
# ---------------------------
@router.post("/execute_llm", response_model=LLMResponse)
async def execute_llm(req: LLMRequest):
    """Endpoint for AI reasoning on documents 
    ```json
    {
    "prompt": "Extract key fields from this document and return them in plain text: Be concise.",
    "context": {
            "document_text": "PASSPORT AUSTRALIA NO885237 Name: Marcus Anthony Seth ..."
        }
    }
    ```
    """
    try:
        # simple context injection (no framework logic here)
        context_str = json.dumps(req.context, indent=2)

        final_prompt = f"""
{req.prompt}

CONTEXT:
{context_str}
"""

        response = AIClients.llm().chat.completions.create(
            model=req.model,
            messages=[
                {"role": "user", "content": final_prompt},
            ],
            temperature=req.temperature,
        )

        raw = response.choices[0].message.content

        return LLMResponse(
            result={"response": raw},
            raw_response=raw,
            prompt_used=final_prompt
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# LLM AI transcribe Endpoint
# ---------------------------
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
    Generic prompt execution endpoint using registry-based prompt contracts.
    \n{ "prompt_name": "opportunity_router", "context": { "transcript": "Customer is considering cancelling due to pricing and comparing with competitors." } }
    \n{ "prompt_name": "opportunity_upsell_extractor", "context": { "transcript": "Customer wants to upgrade from basic plan to enterprise plan due to scaling needs" } }
    \n{ "prompt_name": "opportunity_cross_sell_extractor", "context": { "transcript": "Customer is interested in adding analytics and reporting module to existing CRM subscription" } }
    \n{ "prompt_name": "opportunity_retention_extractor", "context": { "transcript": "Customer is unhappy with service outages and considering switching to a cheaper competitor plan" } }
    \n{ "prompt_name": "retention_nba_refiner", "context": { "transcript": "Customer complains about pricing and wants to downgrade to a cheaper plan" } }  
    """
 

    try:
        started = datetime.utcnow()

        # -------------------------------------------------
        # 1. Fetch prompt config from registry
        # -------------------------------------------------
        prompt_config = prompts_registry.PROMPTS.get(req.prompt_name)

        if not prompt_config:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown prompt_name: {req.prompt_name}"
            )

        system_template = prompt_config["system"]
        user_template = prompt_config["user"]

        # -------------------------------------------------
        # 2. Render user prompt with context
        # -------------------------------------------------
        user_prompt = render_prompt(
            user_template,
            req.context or {}
        )

        system_prompt = system_template

        # -------------------------------------------------
        # 3. Model config (optional override)
        # -------------------------------------------------
        model = (req.options or {}).get(
            "model",
            prompt_config.get("model", "gpt-4o-mini")
        )

        temperature = (req.options or {}).get(
            "temperature",
            prompt_config.get("temperature", 0.0)
        )

        # -------------------------------------------------
        # 4. Call LLM
        # -------------------------------------------------
        response = AIClients.llm().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature
        )

        raw = response.choices[0].message.content

        # -------------------------------------------------
        # 5. Parse JSON safely
        # -------------------------------------------------
        try:
            parsed = json.loads(raw)
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON returned: {raw}"
            )

        # -------------------------------------------------
        # 6. Return response
        # -------------------------------------------------
        return AIIntentResponse(
            result=parsed,
            model=model,
            confidence=parsed.get("AI_Confidence_Score__c")
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"intent-ai execution failed: {str(e)}"
        )