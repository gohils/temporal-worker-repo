import httpx
import asyncio
from typing import List, Dict

URL = "http://localhost:8000/ai_doc_llm/intent-ai"

SYSTEM_PROMPT = "retention_nba_refiner_system"
USER_PROMPT = "retention_nba_refiner_user"

# ---------------------------------------------------------
# Test transcripts mapped to expected NBA intent
# ---------------------------------------------------------
TEST_CASES: List[Dict] = [
    {
        "name": "Price objection (cost complaint)",
        "transcript": "Your monthly bill is too expensive. I cannot continue unless you give me a cheaper plan.",
    },
    {
        "name": "Service failure complaint",
        "transcript": "Your internet has been down multiple times this week and support has not fixed it.",
    },
    {
        "name": "VIP high value churn risk",
        "transcript": "I have been a premium customer for years but I am seriously considering leaving if this continues.",
    },
    {
        "name": "Device issue",
        "transcript": "My device is faulty and keeps restarting. I need a replacement or upgrade.",
    },
    {
        "name": "Bundle upgrade interest",
        "transcript": "Do you have any better bundle options with more value for money?",
    },
    {
        "name": "Premium feature interest",
        "transcript": "I am interested in advanced analytics and premium features if available.",
    },
    {
        "name": "Competitive threat",
        "transcript": "Another provider is offering me a much cheaper plan with better benefits.",
    },
]

# ---------------------------------------------------------
# Call API
# ---------------------------------------------------------
async def call_nba_api(client: httpx.AsyncClient, transcript: str):
    payload = {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": USER_PROMPT,
        "context": {
            "transcript": transcript
        }
    }

    response = await client.post(URL, json=payload)

    if response.status_code != 200:
        return {"error": response.text}

    return response.json()


# ---------------------------------------------------------
# Runner
# ---------------------------------------------------------
async def run_tests():
    async with httpx.AsyncClient(timeout=60) as client:

        print("\n================ NBA ACTION TEST RESULTS ================\n")

        for test in TEST_CASES:
            result = await call_nba_api(client, test["transcript"])

            nba_action = (
                result.get("result", {})
                .get("NBA_Action", "NULL")
            )

            confidence = (
                result.get("result", {})
                .get("confidence", 0)
            )

            print(f"TEST: {test['name']}")
            print(f"TRANSCRIPT: {test['transcript']}")
            print(f"➡️ NBA_ACTION: {nba_action}")
            print(f"➡️ CONFIDENCE: {confidence}")
            print("-" * 60)

        print("\n================ TEST COMPLETE ================\n")


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(run_tests())