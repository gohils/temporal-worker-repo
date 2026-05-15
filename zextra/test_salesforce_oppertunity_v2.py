import os
import requests
from dotenv import load_dotenv

load_dotenv()

LOGIN_URL = os.getenv("SF_LOGIN_URL")
CLIENT_ID = os.getenv("SF_CLIENT_ID")
CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")

API_VERSION = "v62.0"

def get_access_token():
    r = requests.post(LOGIN_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    })
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["instance_url"]


def get_account_by_external_id(token, instance_url, customer_external_id):
    url = f"{instance_url}/services/data/{API_VERSION}/query"

    soql = f"""
    SELECT Id, Name
    FROM Account
    WHERE Customer_External_Id__c = '{customer_external_id}'
    LIMIT 1
    """

    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params={"q": soql})
    r.raise_for_status()

    records = r.json()["records"]
    if not records:
        raise Exception(f"Account not found: {customer_external_id}")

    return records[0]


def clean_payload(payload):
    """Remove None values so Salesforce only receives valid fields"""
    return {k: v for k, v in payload.items() if v is not None}


def upsert_opportunity_by_external_id(
    customer_external_id,
    opportunity_external_id,
    opp_name,
    opp_type,
    stage_name="Qualification",
    close_date="2026-12-31",
    amount=0,

    # OPTIONAL AI FIELDS
    opp_sub_type=None,
    ai_call_summary=None,
    ai_confidence_score=None,
    ai_intent_strength=None,
    ai_revenue_at_risk=None,
    competitor_mentioned=None,
    opportunity_urgency=None,
    recommended_next_action=None
):

    token, instance_url = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    account = get_account_by_external_id(token, instance_url, customer_external_id)
    account_id = account["Id"]

    upsert_url = (
        f"{instance_url}/services/data/{API_VERSION}"
        f"/sobjects/Opportunity/Opportunity_External_Id__c/"
        f"{opportunity_external_id}"
    )

    payload = clean_payload({
        "Name": opp_name,
        "AccountId": account_id,
        "Type": opp_type,
        "StageName": stage_name,
        "CloseDate": close_date,
        "Amount": amount,

        # AI fields (optional)
        "Opportunity_Sub_Type__c": opp_sub_type,
        "AI_Call_Summary__c": ai_call_summary,
        "AI_Confidence_Score__c": ai_confidence_score,
        "AI_Intent_Strength__c": ai_intent_strength,
        "Competitor_Mentioned__c": competitor_mentioned,
        "Opportunity_Urgency__c": opportunity_urgency,
        "Recommended_Next_Action__c": recommended_next_action
    })

    r = requests.patch(upsert_url, json=payload, headers=headers)

    # IMPORTANT: debug on failure
    if r.status_code >= 300:
        print("ERROR:", r.status_code, r.text)
    r.raise_for_status()

    print("✅ Opportunity Upsert Successful")
    print("External ID:", opportunity_external_id)

    return {"success": True, "external_id": opportunity_external_id}


if __name__ == "__main__":

    CUSTOMER_EXTERNAL_ID = "CUST-103"

    result = upsert_opportunity_by_external_id(
        customer_external_id=CUSTOMER_EXTERNAL_ID,
        opportunity_external_id=f"{CUSTOMER_EXTERNAL_ID}_Retention",

        opp_name="AI Retention - Competitive Threat",
        opp_type="Retention",

        ai_call_summary="Customer is evaluating competitor pricing",
        ai_confidence_score=92,
        ai_intent_strength="High",
        competitor_mentioned="Optus",
        opportunity_urgency="Immediate",
        recommended_next_action="Offer retention bundle",

        amount=15000
    )

    print(result)