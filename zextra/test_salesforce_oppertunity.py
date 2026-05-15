import os
import requests
from dotenv import load_dotenv
from datetime import date

load_dotenv()

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
# GET ACCOUNT (by external id)
# =========================

def get_account_by_external_id(token, instance_url, external_id):

    url = f"{instance_url}/services/data/{API_VERSION}/query"

    soql = f"""
    SELECT Id, Name
    FROM Account
    WHERE Customer_External_Id__c = '{external_id}'
    LIMIT 1
    """

    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": soql}
    )
    r.raise_for_status()

    records = r.json()["records"]
    if not records:
        raise Exception(f"Account not found: {external_id}")

    return records[0]

# =========================
# SINGLE WRAPPER: OPPORTUNITY UPSERT
# =========================

def upsert_opportunity_by_account(
    CUSTOMER_EXTERNAL_ID,
    opp_type,
    amount
):
    """
    RULE:
    Only ONE OPEN Opportunity per Account + Type
    """

    token, instance_url = get_access_token()
    account = get_account_by_external_id(token, instance_url, CUSTOMER_EXTERNAL_ID)
    account_id = account["Id"]

    print("Account:", account_id, account["Name"])

    # STEP 1: check existing open opportunity
    query_url = f"{instance_url}/services/data/{API_VERSION}/query"

    soql = f"""
    SELECT Id, Amount, StageName
    FROM Opportunity
    WHERE AccountId = '{account_id}'
    AND Type = '{opp_type}'
    AND IsClosed = false
    ORDER BY LastModifiedDate DESC
    LIMIT 1
    """

    r = requests.get(
        query_url,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": soql}
    )
    r.raise_for_status()

    records = r.json()["records"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # =========================
    # UPDATE EXISTING
    # =========================
    if records:
        opp = records[0]

        update_url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Opportunity/{opp['Id']}"

        payload = {
            "Amount": amount
        }

        r = requests.patch(update_url, json=payload, headers=headers)
        r.raise_for_status()

        print("♻️ Updated existing Opportunity:", opp["Id"])
        return opp["Id"]

    # =========================
    # CREATE NEW
    # =========================
    create_url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Opportunity"

    payload = {
        "Name": f"AI {opp_type} Opportunity",
        "AccountId": account_id,
        "StageName": "Prospecting",
        "CloseDate": str(date(2026, 12, 31)),
        "Amount": amount,
        "Type": opp_type
    }

    r = requests.post(create_url, json=payload, headers=headers)
    r.raise_for_status()

    opp_id = r.json()["id"]

    print("🆕 Created Opportunity:", opp_id)
    return opp_id

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    CUSTOMER_EXTERNAL_ID = "CUST-103"
    # ONLY ONE FUNCTION CALL
    opp_id = upsert_opportunity_by_account(
        CUSTOMER_EXTERNAL_ID,
        opp_type="Retention",
        amount=500
    )

    print("Final Opportunity ID:", opp_id)