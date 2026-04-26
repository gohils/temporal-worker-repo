from fastapi import FastAPI, Request, Response 
from fastapi.middleware.cors import CORSMiddleware

import os
from dotenv import load_dotenv


from app import ai_router
from app import chat_router
from app.routers import ai_document
from app.routers import ai_doc_llm

load_dotenv()


# Create FastAPI app
app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(ai_router.router)
app.include_router(chat_router.router)
app.include_router(ai_document.router)
app.include_router(ai_doc_llm.router)


@app.get("/")
async def root():
    return {"message": "OpenAI Fastapi Applications!"}

    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000
    ) 
