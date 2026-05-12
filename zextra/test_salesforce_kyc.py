import os
import requests
from dotenv import load_dotenv
import psycopg

load_dotenv()

# =========================
# CONFIG
# =========================

LOGIN_URL = os.getenv("SF_LOGIN_URL")
CLIENT_ID = os.getenv("SF_CLIENT_ID")
CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")
API_VERSION = "v62.0"

POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")
if not POSTGRES_CONNECTION_STRING:
    raise ValueError("POSTGRES_CONNECTION_STRING is not set")

# =========================
# DB CONNECTION
# =========================

def get_conn():
    return psycopg.connect(
        POSTGRES_CONNECTION_STRING,
        prepare_threshold=None
    )

# =========================
# AUTH
# =========================

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    r = requests.post(LOGIN_URL, data=payload)
    r.raise_for_status()

    data = r.json()
    return data["access_token"], data["instance_url"]

# =========================
# SQL (DEDUPED + LATEST ONLY)
# =========================

def fetch_documents(header_id):
    query = """
        SELECT DISTINCT ON (d.doc_type)
            d.doc_type,
            d.doc_id,
            d.header_data,
            d.reference_id,
            d.workflow_id,
            d.reference_id,
            d.header_id,
            d.created_at
        FROM erp_crm_documents d
        WHERE d.header_id = %s
        ORDER BY d.doc_type, d.created_at DESC, d.workflow_id DESC;
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, (header_id,))
        rows = cur.fetchall()

    docs = []
    for r in rows:
        docs.append({
            "doc_type": r[0],
            "doc_id": r[1],
            "header_data": r[2],
            "reference_id": r[3],
            "workflow_id": r[4],
        })
    return docs

# =========================
# UTILITIES
# =========================

def normalize_doc_type(doc_type: str) -> str:
    mapping = {
        "driving_licence": "DRIVER_LICENSE",
        "driver_license": "DRIVER_LICENSE",
        "passport": "PASSPORT",
        "utility_bill": "UTILITY_BILL"
    }
    return mapping.get(doc_type, doc_type.upper())


def extract_ocr(doc):
    data = doc.get("header_data", {})
    return data.get("ocr_data", data)


def mask_value(value: str) -> str:
    if not value:
        return None
    value = str(value)
    if len(value) <= 4:
        return value
    return "*" * (len(value) - 4) + value[-4:]

# =========================
# SALESFORCE - ACCOUNT
# =========================

def upsert_account(token, instance_url, ocr, header_id):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Account/Customer_External_Id__c/CUST-{header_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Name": f"{ocr.get('FirstName','')} {ocr.get('LastName','')} -({header_id})",
        "BillingStreet": ocr.get("Address"),
        "BillingCountry": "Australia"
    }

    r = requests.patch(url, json=payload, headers=headers)
    r.raise_for_status()

    return r.json()

# =========================
# SALESFORCE - KYC UPSERT
# =========================

def upsert_kyc(token, instance_url, account_id, doc_type, ocr, external_id, masked_doc_no, reference_id,workflow_id):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/KYC_Document__c/KYC_External_Doc_Id__c/{external_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Account_KYC__c": account_id,
        "Document_Type__c": doc_type,
        "Document_Number__c": masked_doc_no,
        "Issue_By__c": ocr.get("issuedBy")  or ocr.get("Country") or ocr.get("retailer"),
        "Issue_Date__c": ocr.get("DateOfExpiration") or ocr.get("issue_date"),
        "Validation_Status__c": "VALID",
        "Workflow_Id__c": workflow_id,
        "reference_id__c": reference_id
    }

    r = requests.patch(url, json=payload, headers=headers)

    if r.status_code >= 400:
        print("ERROR:", r.text)

    r.raise_for_status()
    return r.json()

# =========================
# ACCOUNT SOURCE SELECTION (CRITICAL FIX)
# =========================

def pick_account_source(docs):
    # 1. Driver license first (MOST TRUSTED)
    for d in docs:
        if normalize_doc_type(d["doc_type"]) == "DRIVER_LICENSE":
            return extract_ocr(d)

    # 2. Passport fallback
    for d in docs:
        if normalize_doc_type(d["doc_type"]) == "PASSPORT":
            return extract_ocr(d)

    # 3. fallback any
    return extract_ocr(docs[0])

# =========================
# PROCESS DOCUMENT
# =========================

def process_document(token, instance_url, account_id, header_id, doc):

    doc_type = normalize_doc_type(doc["doc_type"])
    ocr = extract_ocr(doc)

    raw_number = (
        ocr.get("DocumentNumber")
        or ocr.get("account_number")
        or "UNKNOWN"
    )

    masked_number = mask_value(raw_number)

    external_id = f"{header_id}_{doc_type}_{doc['doc_id']}"

    return upsert_kyc(
        token,
        instance_url,
        account_id,
        doc_type,
        ocr,
        external_id,
        masked_number,
        reference_id=doc.get("reference_id"),
        workflow_id=doc.get("workflow_id")
    )

# =========================
# WORKFLOW
# =========================

def run_workflow(header_id):

    token, instance = get_access_token()

    # STEP 1: FETCH CLEAN DOC SET
    docs = fetch_documents(header_id)

    if not docs:
        raise Exception("No documents found")

    # STEP 2: ACCOUNT FROM DRIVER LICENSE FIRST
    account_source = pick_account_source(docs)

    account = upsert_account(token, instance, account_source, header_id)
    account_id = account["id"]

    print("\n=== ACCOUNT UPSERTED ===", account_id)

    # STEP 3: UPSERT ALL DOCUMENTS
    for doc in docs:
        result = process_document(
            token,
            instance,
            account_id,
            header_id,
            doc
        )

        print(f"\n=== UPSERTED {doc['doc_type']} ===")
        print(result)

# =========================
# ENTRY
# =========================

if __name__ == "__main__":
    run_workflow(header_id=32)