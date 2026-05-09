import os
import requests
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# =========================
# CONFIG FROM ENV
# =========================

LOGIN_URL = os.getenv("SF_LOGIN_URL")

CLIENT_ID = os.getenv("SF_CLIENT_ID")
CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")

# =========================
# AUTH FUNCTION
# =========================

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    response = requests.post(LOGIN_URL, data=payload)

    print("\n=== AUTH RESPONSE ===")
    print("Status:", response.status_code)
    print("Body:", response.text)

    data = response.json()

    if "access_token" not in data:
        raise Exception(f"Authentication failed: {data}")

    return data["access_token"], data["instance_url"]

# =========================
# CREATE ACCOUNT
# =========================

def create_account(access_token, instance_url):
    url = f"{instance_url}/services/data/v62.0/sobjects/Account"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Name": "Acme Corporation",
        "BillingCity": "Melbourne",
        "BillingCountry": "Australia"
    }

    response = requests.post(url, json=payload, headers=headers)

    print("\n=== CREATE ACCOUNT RESPONSE ===")
    print("Status:", response.status_code)
    print("Body:", response.text)

    return response.json()

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    token, instance = get_access_token()
    result = create_account(token, instance)

    print("\n=== SUCCESS ===")
    print(result)