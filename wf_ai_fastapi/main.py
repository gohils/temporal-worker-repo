# main.py
from fastapi.responses import JSONResponse
from fastapi import FastAPI, File, Query, Request, UploadFile, Form, HTTPException
import requests
import os
import json
from pydantic import BaseModel
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta


from temporalio.client import Client, WorkflowHandle
import asyncio

# Import DB abstraction layer
from wf_ai_fastapi.routers.temporal_router import router as temporal_router
from wf_ai_fastapi.routers.crud_router import router as crud_router
from wf_ai_fastapi.routers.ai_doc_router import router as ai_doc_router
from wf_ai_fastapi.routers.ai_doc_llm_router import router as ai_doc_llm_router
from wf_ai_fastapi.routers.erp_router import router as erp_router

from fastapi.middleware.cors import CORSMiddleware




logger = logging.getLogger(__name__)

# ------------------------------------------------
# FastAPI App
# ------------------------------------------------
app = FastAPI(title="IBPA API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] ,  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Include ERP router

app.include_router(temporal_router)
app.include_router(ai_doc_llm_router)
app.include_router(ai_doc_router)
app.include_router(crud_router)
app.include_router(erp_router)

# ------------------------------------------------
# Run FastAPI
# ------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)