from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
API_VERSION = "v62.0"  # Salesforce API version

router = APIRouter(
    prefix="/salesforce",
    tags=["salesforce"])


# # =========================================================
# # SIMPLE SALESFORCE CLIENT (NO CLASSES, MINIMAL)
# # =========================================================
# 🟦 1. Account = “Who”
# Represents:
   # customer / company / household (B2B or B2C via Person Account)
   # root entity for all activity

# 🟨 2. Opportunity = “Money / Revenue”
# Represents:
   # upsell
   # cross-sell
   # renewal
   # retention revenue
   # pipeline forecasting

# 🟥 3. Case = “Problem / Support”
# Represents:
   # complaints
   # incidents
   # service requests
   # billing issues
   # support lifecycle
# 🟩 4. Task = “Work to do”
# Represents:
   # follow-up call
   # email
   # internal action

class SF:

   access_token = None
   instance_url = None

   @staticmethod
   def get_access_token():
      payload = {
         "grant_type": "client_credentials",
         "client_id": CLIENT_ID,
         "client_secret": CLIENT_SECRET
      }

      response = requests.post(LOGIN_URL, data=payload)

      print("\n=== AUTH RESPONSE ===")
      print("Status:", response.status_code)
      # print("Body:", response.text)

      data = response.json()

      if "access_token" not in data:
            raise Exception(f"Auth failed: {data}")

      SF.access_token = data["access_token"]
      SF.instance_url = data["instance_url"]

   @staticmethod
   def create(object_name, payload):

      SF.get_access_token()

      url = f"{SF.instance_url}/services/data/{API_VERSION}/sobjects/{object_name}"

      headers = {
         "Authorization": f"Bearer {SF.access_token}",
         "Content-Type": "application/json"
      }

      res = requests.post(url, json=payload, headers=headers)
      data = res.json()

      if not data.get("success"):
         raise Exception(data)

      return data["id"]

   @staticmethod
   def get_record(object_name, record_id):

      SF.get_access_token()

      url = (
         f"{SF.instance_url}"
         f"/services/data/{API_VERSION}"
         f"/sobjects/{object_name}/{record_id}"
      )

      headers = {
         "Authorization": f"Bearer {SF.access_token}"
      }

      res = requests.get(url, headers=headers)

      if res.status_code != 200:
         raise Exception(res.text)

      return res.json()

   @staticmethod
   def query(soql):

      SF.get_access_token()

      url = f"{SF.instance_url}/services/data/{API_VERSION}/query"

      headers = {
         "Authorization": f"Bearer {SF.access_token}"
      }

      res = requests.get(url, headers=headers, params={"q": soql})

      data = res.json()

      if res.status_code != 200:
         raise Exception(f"Salesforce Query Error: {data}")

      return data
   

# =========================================================
# 1. CREATE ACCOUNT (Customer onboarding)
# =========================================================
@router.post("/account")
def create_account(payload: dict):
    """
    Create Salesforce Account (Customer / Company)

    Example payload:
    {
        "Name": "Acme Corporation",
        "Phone": "+61 400 000 111",
        "Website": "https://acme.com",
        "BillingCity": "Melbourne",
        "BillingCountry": "Australia",
        "Industry": "Technology",
        "Description": "AI suggested upsell based on usage patterns"
    }
    """

    account_id = SF.create("Account", payload)
    return {"account_id": account_id}


# =========================================================
# 2. CREATE TASK (Churn prevention / follow-up)
# =========================================================
@router.post("/task")
def create_task(payload: dict):
    """
    Create Salesforce Task (Follow-up / Action Item)

    Example payload:
    {
        "Subject": "Call high churn-risk customer",
        "Status": "Not Started",
        "Priority": "High",
        "Description": "AI detected churn risk from call transcript",
        "WhatId": "001XXXXXXXXXXXX",   # Account ID (optional)
        "WhoId": "003XXXXXXXXXXXX",    # Contact ID (optional)
        "ActivityDate": "2026-05-10"
    }
    """

    task_id = SF.create("Task", payload)
    return {"task_id": task_id}


# =========================================================
# 3. CREATE OPPORTUNITY (Upsell / cross-sell / retention)
# =========================================================
@router.post("/opportunity")
def create_opportunity(payload: dict):
    """
    Create Salesforce Opportunity (Revenue event)

    Example payload:
    {
        "Name": "Upsell Premium Package - Acme",
        "StageName": "Prospecting",
        "CloseDate": "2026-07-30",
        "Amount": 75000,
        "Type": "Upsell",
        "AccountId": "001XXXXXXXXXXXX",
        "Description": "AI suggested upsell based on usage patterns"
    }
    """

    opp_id = SF.create("Opportunity", payload)
    return {"opportunity_id": opp_id}


# =========================================================
# 4. CREATE CASE (Customer complaint / support)
# =========================================================
@router.post("/case")
def create_case(payload: dict):
    """
    Create Salesforce Case (Complaint / Support Ticket)

    Example payload:
    {
        "Subject": "Billing issue - incorrect invoice",
        "Status": "New",
        "Priority": "High",
        "Origin": "Phone",
        "Description": "Customer reported incorrect billing amount",
        "AccountId": "001XXXXXXXXXXXX",
        "ContactId": "003XXXXXXXXXXXX"
    }
    """

    case_id = SF.create("Case", payload)
    return {"case_id": case_id}

# =========================================================
# GET ACCOUNT (Customer information)
# =========================================================
@router.get("/account/{account_id}")
def get_account(account_id: str):
    """
    Get Salesforce Account by ID

    Example:
    GET /salesforce/account/001XXXXXXXXXXXX
    """

    return SF.get_record("Account", account_id)

# =========================================================
# GET TASK (Task information)
# =========================================================
@router.get("/task/{task_id}")
def get_task(task_id: str):
    """
    Get Salesforce Task by ID
    """

    return SF.get_record("Task", task_id)

# =========================================================
# GET OPPORTUNITY (Opportunity information)
# =========================================================
@router.get("/opportunity/{opp_id}")
def get_opportunity(opp_id: str):
    """
    Get Salesforce Opportunity by ID
    """

    return SF.get_record("Opportunity", opp_id)
# =========================================================
# GET CASE (Case information)
# =========================================================
@router.get("/case/{case_id}")
def get_case(case_id: str):
    """
    Get Salesforce Case by ID
    """

    return SF.get_record("Case", case_id)

# =========================================================
# Query Accounts (filters, search, analytics)
# =========================================================
@router.get("/accounts/search")
def search_accounts(soql: str):
    """
    Search Salesforce Accounts using SOQL

   Account
   SELECT Id, Name, CreatedDate FROM Account ORDER BY CreatedDate DESC LIMIT 5
   SELECT Id, Name FROM Account WHERE Name LIKE 'Acme%'
   SELECT Id, Name FROM Account WHERE Id = '001g500000LisVgAAJ'

   Contact
   SELECT Id, FirstName, LastName, Email, AccountId FROM Contact LIMIT 10

   Opportunity
   SELECT Id, Name, StageName, Amount, CloseDate, AccountId FROM Opportunity LIMIT 10

   Case
   SELECT Id, CaseNumber, Subject, Status, Priority, AccountId FROM Case LIMIT 10

   Task
   SELECT Id, Subject, Status, Priority, WhatId, WhoId FROM Task LIMIT 10

    """
   
    return SF.query(soql)