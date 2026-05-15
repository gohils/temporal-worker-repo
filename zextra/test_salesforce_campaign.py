import os
import requests
from dotenv import load_dotenv
from datetime import date

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
# ACCOUNT
# =========================

def upsert_account(token, instance_url, first_name, last_name, external_id):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Account/Customer_External_Id__c/{external_id}"

    payload = {
        "Name": f"{first_name} {last_name}",
        "BillingCountry": "Australia"
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.patch(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# CONTACT
# =========================

def create_contact(token, instance_url, account_id, first_name, last_name, email):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Contact"

    payload = {
        "FirstName": first_name,
        "LastName": last_name,
        "Email": email,
        "AccountId": account_id
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

def get_primary_contact(token, instance_url, account_id):

    url = f"{instance_url}/services/data/v62.0/query"

    soql = f"""
    SELECT Id, Name
    FROM Contact
    WHERE AccountId = '{account_id}'
    LIMIT 1
    """

    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": soql}
    )

    r.raise_for_status()
    records = r.json()["records"]

    return records[0] if records else None

# =========================
# CAMPAIGN (RETENTION)
# =========================

def create_campaign(token, instance_url):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Campaign"

    payload = {
        "Name": "AI Churn Prevention Campaign",
        "Status": "In Progress",
        "Type": "Retention",
        "IsActive": True
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# CAMPAIGN MEMBER (ENROLLMENT)
# =========================

def enroll_campaign(token, instance_url, campaign_id, contact_id):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/CampaignMember"

    payload = {
        "CampaignId": campaign_id,
        "ContactId": contact_id,
        "Status": "Added"
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# CASE (SERVICE ISSUE)
# =========================

def create_case(token, instance_url, account_id, subject):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Case"

    payload = {
        "AccountId": account_id,
        "Subject": subject,
        "Status": "New",
        "Origin": "Call Center",
        "Priority": "High"
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# OPPORTUNITY (UPSSELL / CROSS-SELL / SAVE OFFER)
# =========================

def create_opportunity(token, instance_url, account_id, opp_type, amount):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Opportunity"

    payload = {
        "Name": f"{opp_type} Opportunity",
        "AccountId": account_id,
        "StageName": "Prospecting",
        "CloseDate": str(date(2026, 12, 31)),
        "Amount": amount,
        "Type": opp_type
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# MOCK DATA
# =========================

customers = [
    ("Oliver", "Smith"),
    ("Amelia", "Johnson")
]

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    token, instance = get_access_token()

    # STEP 1 - CREATE CAMPAIGN ONCE
    # campaign = create_campaign(token, instance)
    # campaign_id = campaign["id"]
    campaign_id = "701g500000MP3ndAAD"

    print("\n=== CAMPAIGN CREATED ===")
    print(campaign_id)

    # =========================
    # LOOP CUSTOMERS
    # =========================

    for i, (first, last) in enumerate(customers, start=101):

        external_id = f"CUST-{i}"

        print("\n===========================")
        print("PROCESSING:", external_id, first, last)

        # STEP 2 - ACCOUNT
        account = upsert_account(token, instance, first, last, external_id)
        account_id = account["id"]

        # STEP 3 - CONTACT
        email = f"{first.lower()}.{last.lower()}@demo.com"

        contact = get_primary_contact(token, instance, account_id)

        if contact is None:
            contact = create_contact(token, instance, account_id, first, last, email)
            contact_id = contact["id"]
        else:
            contact_id = contact["Id"]

        print("Account:", account_id)
        print("Contact:", contact_id)

        # =========================
        # SIMULATED BUSINESS LOGIC
        # =========================

        if i % 3 == 0:
            # 🔴 CHURN CASE
            case = create_case(
                token,
                instance,
                account_id,
                "Customer experiencing service issues"
            )
            print("CASE CREATED:", case["id"])

            # ENROLL IN RETENTION CAMPAIGN
            cm = enroll_campaign(
                token,
                instance,
                campaign_id,
                contact_id
            )
            print("ENROLLED IN CAMPAIGN:", cm["id"])

        elif i % 3 == 1:
            # 🟢 UPSSELL
            opp = create_opportunity(
                token,
                instance,
                account_id,
                "Upsell",
                500
            )
            print("UPSELL OPPORTUNITY:", opp["id"])

        else:
            # 🔵 CROSS-SELL
            opp = create_opportunity(
                token,
                instance,
                account_id,
                "Cross-sell",
                300
            )
            print("CROSS-SELL OPPORTUNITY:", opp["id"])