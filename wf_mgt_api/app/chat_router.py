# uvicorn main:app
# uvicorn main:app --reload

# Main imports
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import os
from pydantic import BaseModel
from typing import List

# Custom function imports
from app.functions.text_to_speech import gcp_convert_text_to_speech, azure_convert_text_to_speech
from app.functions.openai_requests import convert_audio_to_text, get_chat_response
from app.functions.database import store_messages, reset_messages

from fastapi import APIRouter

router = APIRouter()



# Store chat messages in memory (not suitable for production)
chat_history = []


class Message(BaseModel):
    text: str
    user: str


class BotResponse(BaseModel):
    text: str
    user: str = "ChatGPT"

@router.get("/chatbot_messages", response_model=List[Message])
async def get_messages():
    return chat_history


@router.post("/chatbot_messages", response_model=BotResponse)
async def send_message(message: Message):
    # print("=====user input",message)
    chat_history.append(message)

    # Get chat response
    chat_response = get_chat_response(message.text)

    # Store messages
    store_messages(message.text, chat_response)

    # Guard: Ensure output
    if not chat_response:
        raise HTTPException(status_code=400, detail="Failed chat response")
    
    # print("======== chat_response ========",chat_response)

    response = BotResponse(text=chat_response)

    # print("=========",response)
    return response

