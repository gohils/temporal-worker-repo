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
# SQL FETCH (Direct Debit Form)
# =========================

def fetch_direct_debit(header_id):
    query = """
        SELECT
            d.header_data,
            d.reference_id,
            d.workflow_id,
            d.created_at
        FROM erp_crm_documents d
        WHERE d.header_id = %s
        ORDER BY d.created_at DESC
        LIMIT 1;
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, (header_id,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        "header_data": row[0],
        "reference_id": row[1],
        "workflow_id": row[2],
    }


# =========================
# UTILITIES
# =========================

def mask_value(value: str, keep=4):
    if not value:
        return None
    value = str(value)
    if len(value) <= keep:
        return value
    return "*" * (len(value) - keep) + value[-keep:]


def mask_email(email: str):
    if not email or "@" not in email:
        return None
    name, domain = email.split("@", 1)
    return mask_value(name, 2) + "@" + domain


# =========================
# SALESFORCE UPSERT (Direct Debit)
# =========================
def upsert_direct_debit(token, instance_url, header_id, data):

    ocr = data.get("header_data", {}).get("ocr_data", {})

    print("\n=== OCR DATA ===", ocr)
    # -------------------------
    # CUSTOMER LINK (REQUIRED)
    # -------------------------
    # customer_external_id = f"CUST-{header_id}"
    declared = data.get("header_data", {}).get("declared_data", {})

    customer_external_id = declared.get("customer_number")

    if not customer_external_id:
        raise ValueError("Missing customer_number in declared_data")

    direct_debit_external_id  = f"Direct-Debit-{header_id}"

    url = (
        f"{instance_url}/services/data/{API_VERSION}/sobjects/"
        f"Direct_Debit__c/External_Id__c/{direct_debit_external_id}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        # 🔗 link to existing Account using Customer external ID (Customer External Id = CUST-DD-47)
        "Account_DD__r": { "Customer_External_Id__c": customer_external_id  },
        # direct debit fields
        "Status__c": "ACTIVE",
        "Bank_Name__c": ocr.get("BankName"),
        "BSB_Number__c": ocr.get("BSBNumber"),
        "Bank_Account_Number__c": mask_value( ocr.get("AccountNumber")),
        "Bank_Account_Name__c": ocr.get("AccountName"),
        "Signed_Date__c": ocr.get("SignedDate"),
    }

    try:
        r = requests.patch(url, json=payload, headers=headers)

        if r.status_code >= 400:
            print("⚠️ Salesforce Direct Debit failed:", r.text)
            return {"status": "SKIPPED", "error": r.text}

        return {"status": "SUCCESS", "result": r.json()}

    except Exception as e:
        print("⚠️ Salesforce unreachable:", str(e))
        return {"status": "SKIPPED", "error": str(e)}
    
# =========================
# MAIN FLOW
# =========================

def upsert_account_with_direct_debit(header_id):

    token, instance = get_access_token()

    data = fetch_direct_debit(header_id)

    if not data:
        print("No direct debit data found")
        return {"status": "EMPTY"}

    result = upsert_direct_debit(token, instance, header_id, data)

    print("\n=== DIRECT DEBIT SYNC RESULT ===")
    print(result)

    return result


# =========================
# ENTRY
# =========================

if __name__ == "__main__":
    upsert_account_with_direct_debit(header_id=47)