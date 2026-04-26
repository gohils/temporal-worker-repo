import os
import uuid
import json
from fastapi import UploadFile, HTTPException
from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import OpenAI


# =========================================================
# CONFIG
# =========================================================
CONNECT_STR = os.getenv("blob_storage_connect_str")
CONTAINER = os.getenv("container_name", "documents")

AZURE_ENDPOINT = os.getenv("AZURE_DOC_INT_API_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_DOC_INT_API_KEY")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# =========================================================
# SINGLETON CLIENTS
# =========================================================
class AIClients:
    _doc_client = None
    _llm_client = None
    _blob_client = None

    @classmethod
    def doc_ai(cls):
        if cls._doc_client is None:
            cls._doc_client = DocumentAnalysisClient(
                endpoint=AZURE_ENDPOINT,
                credential=AzureKeyCredential(AZURE_API_KEY)
            )
        return cls._doc_client

    @classmethod
    def llm(cls):
        if cls._llm_client is None:
            cls._llm_client = OpenAI(api_key=OPENAI_API_KEY)
        return cls._llm_client

    @classmethod
    def blob(cls):
        if cls._blob_client is None:
            cls._blob_client = BlobServiceClient.from_connection_string(CONNECT_STR)
        return cls._blob_client


# =========================================================
# SAFE HELPERS
# =========================================================
class Safe:

    @staticmethod
    def value(field, attr="content"):
        if not field:
            return None
        return getattr(field, attr, None)


# =========================================================
# BLOB STORAGE SERVICE
# =========================================================
class BlobService:

    @staticmethod
    def upload(file: UploadFile) -> str:
        if not file:
            raise HTTPException(400, "No file provided")

        file_name = f"{uuid.uuid4()}-{file.filename}"

        blob = AIClients.blob().get_blob_client(
            container=CONTAINER,
            blob=file_name
        )

        try:
            blob.upload_blob(file.file.read(), overwrite=True)
        except Exception as e:
            raise HTTPException(500, f"Upload failed: {str(e)}")
        finally:
            file.file.close()

        return f"https://zblobarchive.blob.core.windows.net/documents/{file_name}"


# =========================================================
# DOCUMENT AI SERVICE (OCR + EXTRACTION)
# =========================================================
class DocumentService:

    # -------- ANALYZE --------
    @staticmethod
    def analyze(url: str, model: str):
        return AIClients.doc_ai() \
            .begin_analyze_document_from_url(model, url) \
            .result()

    # -------- FIELD EXTRACTION --------
    @staticmethod
    def extract(doc, fields):
        data = {}
        for f in fields:
            val = doc.fields.get(f)
            if val:
                data[f] = Safe.value(val)
        return data

    @staticmethod
    def extract_all(result, fields):
        output = {}
        for d in result.documents:
            output.update(DocumentService.extract(d, fields))
        return output

    # -------- TEXT EXTRACTION --------
    @staticmethod
    def extract_plain_text(result):
        return "\n\n".join(
            "\n".join(line.content for line in page.lines)
            for page in result.pages
        )

    # -------- FLAT EXTRACTION --------
    @staticmethod
    def extract_flat(result):
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

    # -------- STRUCTURED EXTRACTION --------
    @staticmethod
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
                    items.append({
                        k: getattr(v, "content", None)
                        for k, v in item.value.items()
                    })

            docs.append({
                "header": header,
                "items": items
            })

        return docs


# =========================================================
# LLM SERVICE
# =========================================================
class LLMService:

    @staticmethod
    def reason(prompt: str, model: str, temperature: float, max_tokens: int):

        response = AIClients.llm().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI decision engine replacing a human decision-maker in a business workflow."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        raw = response.choices[0].message.content

        try:
            return json.loads(raw), raw
        except json.JSONDecodeError:
            return {"decision": None, "raw": raw}, raw