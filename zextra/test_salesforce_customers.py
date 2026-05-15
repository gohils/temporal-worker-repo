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
# UPSERT ACCOUNT
# =========================

def upsert_account(token, instance_url, first_name, last_name, external_id):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Account/Customer_External_Id__c/{external_id}"

    payload = {
        "Name": f"{first_name} {last_name}",
        "BillingCountry": "Australia"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    r = requests.patch(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# CREATE CONTACT
# =========================

def create_contact(token, instance_url, account_id, first_name, last_name, email):

    url = f"{instance_url}/services/data/{API_VERSION}/sobjects/Contact"

    payload = {
        "FirstName": first_name,
        "LastName": last_name,
        "Email": email,
        "AccountId": account_id
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# =========================
# MOCK CUSTOMER DATA (REALISTIC)
# =========================

customers = [
    ("Sophia", "Johnson"),
    ("Emily", "Williams"),
    ("Jenny", "Walker"),
    ("Bella", "Robinson"),
    ("Grace", "Martin"),
    ("Oliver", "Smith"),
    ("Liam", "Jones"),
    ("Lucas", "Miller"),
    ("Henry", "Davis"),
    ("David", "Wilson")
]

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    token, instance = get_access_token()

    created_records = []

    for i, (first, last) in enumerate(customers, start=101):

        external_id = f"CUST-{i}"

        print("\n===========================")
        print("CREATING:", external_id, first, last)

        # STEP 1 - ACCOUNT
        account = upsert_account(token, instance, first, last, external_id)
        account_id = account["id"]

        print("Account ID:", account_id)

        # STEP 2 - CONTACT
        email = f"{first.lower()}.{last.lower()}@demo.com"

        contact = create_contact(
            token,
            instance,
            account_id,
            first,
            last,
            email
        )

        contact_id = contact["id"]

        print("Contact ID:", contact_id)

        created_records.append({
            "external_id": external_id,
            "account_id": account_id,
            "contact_id": contact_id,
            "name": f"{first} {last}"
        })

    print("\n\n===== SUMMARY =====")
    for r in created_records:
        print(r)