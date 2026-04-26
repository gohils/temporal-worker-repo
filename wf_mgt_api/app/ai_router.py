import os
import uuid
import tempfile
from io import BytesIO

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
import requests

from app.functions.text_to_speech import (
    gcp_convert_text_to_speech,
    azure_convert_text_to_speech,
)
from app.functions.openai_requests import (
    convert_audio_to_text,
    get_chat_response,
)
from app.functions.database import store_messages, reset_messages


# 🔴 CRITICAL for Azure Functions
tempfile.tempdir = "/tmp"

router = APIRouter()


def save_temp_file(contents: bytes, suffix: str = ".wav") -> str:
    """Save bytes to a unique temp file in /tmp and return path."""
    temp_path = f"/tmp/{uuid.uuid4()}{suffix}"
    with open(temp_path, "wb") as f:
        f.write(contents)
    return temp_path


def stream_bytes(data: bytes, media_type: str):
    return StreamingResponse(BytesIO(data), media_type=media_type)


@router.get("/reset")
async def reset_conversation():
    reset_messages()
    return {"response": "conversation reset"}


# ✅ MAIN BOT ENDPOINT (FIXED)
@router.post("/post-audio/")
async def post_audio(file: UploadFile = File(...)):
    contents = await file.read()

    temp_path = save_temp_file(contents)

    try:
        with open(temp_path, "rb") as audio_input:
            message_decoded = convert_audio_to_text(audio_input)

        if not message_decoded:
            raise HTTPException(400, "Failed to decode audio")

        chat_response = get_chat_response(message_decoded)

        if not chat_response:
            raise HTTPException(400, "Failed chat response")

        store_messages(message_decoded, chat_response)

        audio_output = gcp_convert_text_to_speech(chat_response)
        # audio_output = azure_convert_text_to_speech(chat_response)

        if not audio_output:
            raise HTTPException(400, "Failed audio output")

        return stream_bytes(audio_output, "application/octet-stream")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ✅ SPEECH TO TEXT (FIXED)
@router.post("/speech-to-text")
async def speech_to_text(file: UploadFile = File(...)):
    contents = await file.read()
    temp_path = save_temp_file(contents)

    try:
        with open(temp_path, "rb") as audio_input:
            recognized_text = convert_audio_to_text(audio_input)

        if not recognized_text:
            raise HTTPException(400, "Failed to decode audio")

        return {"recognized_text": recognized_text}

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ✅ SPEECH TO TEXT FROM URL (FIXED)
@router.post("/speech-to-text-url")
async def speech_to_text_url(file_url: str):
    response = requests.get(file_url)
    if response.status_code != 200:
        raise HTTPException(
            400,
            f"Failed to download audio file. Status: {response.status_code}",
        )

    temp_path = save_temp_file(response.content)

    try:
        with open(temp_path, "rb") as audio_input:
            recognized_text = convert_audio_to_text(audio_input)

        if not recognized_text:
            raise HTTPException(400, "Failed to decode audio")

        return {"recognized_text": recognized_text}

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ✅ TEST AUDIO (NO DISK WRITE)
@router.get("/get-audio-test/")
async def get_audio_test():
    with open("/tmp/test.mp3", "rb") as f:
        audio_input = f.read()

    message_decoded = convert_audio_to_text(BytesIO(audio_input))

    if not message_decoded:
        raise HTTPException(400, "Failed to decode audio")

    chat_response = get_chat_response(message_decoded)
    store_messages(message_decoded, chat_response)

    audio_output = gcp_convert_text_to_speech(chat_response)

    if not audio_output:
        raise HTTPException(400, "Failed audio output")

    return stream_bytes(audio_output, "audio/mpeg")
