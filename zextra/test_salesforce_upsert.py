import os
import requests
from dotenv import load_dotenv

load_dotenv()

# =========================
# CONFIG
# =========================

LOGIN_URL = os.getenv("SF_LOGIN_URL")
CLIENT_ID = os.getenv("SF_CLIENT_ID")
CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")

API_VERSION = "v62.0"

# =========================
# AUTH
# =========================

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    response = requests.post(LOGIN_URL, data=payload)
    response.raise_for_status()

    data = response.json()
    return data["access_token"], data["instance_url"]

# =========================
# ACCOUNT UPSERT
# =========================

def upsert_account(token, instance_url, ocr, external_id="CUST-001"):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Account/Customer_External_Id__c/{external_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Name": f"{ocr['FirstName']} {ocr['LastName']}",
        "BillingStreet": ocr["Address"],
        "BillingCountry": "Australia"
    }

    response = requests.patch(url, json=payload, headers=headers)
    response.raise_for_status()

    return response.json()

# =========================
# GENERIC KYC UPSERT ENGINE (FIXED PATTERN)
# =========================
def upsert_kyc(token, instance_url, account_id, doc_type, ocr, external_id):

    url = f"{instance_url}/services/data/v62.0/sobjects/KYC_Document__c/KYC_External_Doc_Id__c/{external_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Account_KYC__c": account_id,
        "Document_Number__c": ocr.get("DocumentNumber") or ocr.get("account_number"),
        "Document_Type__c": doc_type,
        "Issue_By__c": ocr.get("issuedBy"),
        "Issue_Date__c": ocr.get("DateOfBirth") or ocr.get("issue_date"),
        "Validation_Status__c": "VALID",
        "Workflow_Id__c": "wf-001",
        "reference_id__c": f"REF-{doc_type}"
    }

    response = requests.patch(url, json=payload, headers=headers)

    if response.status_code >= 400:
        print("ERROR:", response.text)

    response.raise_for_status()
    return response.json()

# =========================
# DOCUMENT HANDLERS (FIXED IDS)
# =========================

def create_driver_license(token, instance_url, account_id, ocr):

    return upsert_kyc(
        token,
        instance_url,
        account_id,
        "DRIVER_LICENSE",
        ocr,
        "001_DRIVER"
    )

def create_passport(token, instance_url, account_id, passport):

    return upsert_kyc(
        token,
        instance_url,
        account_id,
        "PASSPORT",
        passport,
        "001_PASSPORT"
    )

def create_utility_bill(token, instance_url, account_id, bill):

    return upsert_kyc(
        token,
        instance_url,
        account_id,
        "UTILITY_BILL",
        bill,
        "001_UTILITY"
    )

# =========================
# MAIN WORKFLOW
# =========================

if __name__ == "__main__":

    token, instance = get_access_token()

    # =========================
    # DRIVER LICENSE OCR
    # =========================

    driver_license = {
        "Address": "FLAT 10 77 SAMPLE PARADE KEW EAST VIC 3102",
        "LastName": "CITIZEN",
        "issuedBy": "VICTORIA AUSTRALIA",
        "FirstName": "JANE",
        "DateOfBirth": "09-07-1983",
        "DocumentNumber": "987654321"
    }

    # =========================
    # PASSPORT OCR
    # =========================

    passport = {
        "Sex": "F",
        "Country": "AUSTRALIA",
        "LastName": "CITIZEN",
        "FirstName": "JANE",
        "DateOfBirth": "09 JUL 1983",
        "DateOfIssue": "01 MAR 2014",
        "Nationality": "AUSTRALIAN",
        "DocumentNumber": "PA0916042"
    }

    # =========================
    # UTILITY BILL OCR
    # =========================

    utility_bill = {
        "address": "JANE CITIZEN FLAT 10 77 SAMPLE PARADE KEW EAST VIC 3102",
        "retailer": "agl",
        "issue_date": "5 Apr 2023",
        "account_number": "123456789X"
    }

    # =========================
    # STEP 1 - UPSERT ACCOUNT
    # =========================

    account = upsert_account(token, instance, driver_license, "CUST-001")
    account_id = account["id"]

    print("\n=== ACCOUNT UPSERTED ===")
    print(account_id)

    # =========================
    # STEP 2 - DRIVER LICENSE
    # =========================

    dl = create_driver_license(token, instance, account_id, driver_license)
    print("\n=== DRIVER LICENSE UPSERTED ===")
    print(dl)

    # =========================
    # STEP 3 - PASSPORT
    # =========================

    pp = create_passport(token, instance, account_id, passport)
    print("\n=== PASSPORT UPSERTED ===")
    print(pp)

    # =========================
    # STEP 4 - UTILITY BILL
    # =========================

    ub = create_utility_bill(token, instance, account_id, utility_bill)
    print("\n=== UTILITY BILL UPSERTED ===")
    print(ub)