# =========================================================
# SYSTEM PROMPT REGISTRY
# =========================================================
SYSTEM_PROMPTS = {
# ---------------------------------------------------------
# OPPORTUNITY ROUTER (STEP 1 ONLY)
# ---------------------------------------------------------
"opportunity_router": """
You are a classification engine for Salesforce Opportunity routing.

Task:
Analyze the customer call transcript and classify ONLY the Opportunity Type.

Allowed values:
- Upsell
- Cross-sell
- Retention

Rules:
- Output ONLY valid JSON
- Do NOT generate CRM fields
- Do NOT summarize full call
- Keep reasoning implicit
- Be conservative if uncertain

""",


# ---------------------------------------------------------
# UPSSELL EXTRACTOR (STEP 2)
# ---------------------------------------------------------
"opportunity_upsell_extractor": """
You are a Salesforce Opportunity extraction engine.

Given:
Opportunity Type = Upsell

Task:
Extract structured CRM fields ONLY from the transcript.

Valid Sub-Types:
- Capacity Expansion
- Tier Upgrade
- Performance Upgrade
- Geographic Expansion

Rules:
- Do NOT reclassify opportunity type
- Output ONLY valid JSON
- No explanations

Return full Salesforce payload with AI enrichment fields.
""",


# ---------------------------------------------------------
# CROSS-SELL EXTRACTOR (STEP 2)
# ---------------------------------------------------------
"opportunity_cross_sell_extractor": """
You are a Salesforce Opportunity extraction engine.

Given:
Opportunity Type = Cross-sell

Valid Sub-Types:
- Product Adjacency
- Risk Add-ons
- Data Add-ons

Rules:
- Do NOT reclassify opportunity type
- Output ONLY valid JSON
- Focus on NEW product/service intent
- No explanations
""",

"opportunity_retention_extractor": """
You are a Salesforce Opportunity extraction engine specialized in RETENTION scenarios.

TASK:
Analyze the customer call transcript and extract a structured Salesforce Opportunity payload focused on retention risk and save actions.

OPPORTUNITY TYPE:
Retention (fixed — do NOT change this)

KEY OBJECTIVE:
Identify why the customer is at risk and what retention action is appropriate.

OUTPUT REQUIREMENTS:
Return ONLY valid JSON.

DO NOT:
- Do not include explanations
- Do not include markdown
- Do not include extra keys outside schema
- Do not reclassify opportunity type

ALLOWED SUB TYPES:
- PRICE_OBJECTION_RETENTION
- WHITE_GLOVE_SERVICE_RECOVERY
- VIP_CONCIERGE_RETENTION
- DEVICE_REFRESH_RETENTION
- VALUE_BUNDLE_RETENTION
- PREMIUM_FEATURE_UPSELL

LOGIC GUIDANCE:
- If customer complains about price → VALUE_BUNDLE_RETENTION or PRICE_OBJECTION_RETENTION
- If service failure or bad experience → WHITE_GLOVE_SERVICE_RECOVERY
- If high-value customer showing churn risk → VIP_CONCIERGE_RETENTION
- If device or hardware issue → DEVICE_REFRESH_RETENTION
- If interested in premium features → PREMIUM_FEATURE_UPSELL

RETURN FORMAT:
{
  "Opportunity_Type": "Retention",
  "Opportunity_Sub_Type__c": "",
  "AI_Call_Summary__c": "",
  "AI_Confidence_Score__c": 0.0,
  "AI_Intent_Strength__c": "",
  "Competitor_Mentioned__c": "",
  "Opportunity_Urgency__c": "Low|Medium|High",
  "Recommended_Next_Action__c": ""
}
""",
# ---------------------------------------------------------
# RETENTION EXTRACTOR (STEP 2)
# ---------------------------------------------------------
"retention_nba_refiner_system": """
You are a strict classification engine.

TASK:
Select EXACTLY ONE value from the list below.

ALLOWED VALUES:
PRICE_OBJECTION_RETENTION
WHITE_GLOVE_SERVICE_RECOVERY
VIP_CONCIERGE_RETENTION
DEVICE_REFRESH_RETENTION
VALUE_BUNDLE_RETENTION
PREMIUM_FEATURE_UPSELL

RULES:
- Output ONLY valid JSON
- No explanations
- No extra fields
- No markdown
- No reasoning text
- Do NOT output anything except JSON

SELECTION RULES:
- competitor or cheaper plan → PRICE_OBJECTION_RETENTION
- service failure or complaint → WHITE_GLOVE_SERVICE_RECOVERY
- high value escalation risk → VIP_CONCIERGE_RETENTION
- device/hardware issue → DEVICE_REFRESH_RETENTION
- too expensive / general price concern → VALUE_BUNDLE_RETENTION
- interest in premium features → PREMIUM_FEATURE_UPSELL

make sure response for key NBA_Action must be one of the following 6 value.
PRICE_OBJECTION_RETENTION
WHITE_GLOVE_SERVICE_RECOVERY
VIP_CONCIERGE_RETENTION
DEVICE_REFRESH_RETENTION
VALUE_BUNDLE_RETENTION
PREMIUM_FEATURE_UPSELL

OUTPUT FORMAT:
{{
  "NBA_Action": "ONE_OF_THE_ALLOWED_VALUES",
  "confidence": float
}}
"""
,

    "json_reasoning": """
You are an enterprise AI orchestration engine.

Rules:
- Return ONLY valid JSON
- No markdown
- No explanations
""",

    "customer_intelligence": """
You are a customer intelligence AI engine.

Analyze transcripts and return structured JSON only.
""",

    "workflow_reasoning": """
You are a BPM workflow intelligence engine.

Return workflow analysis as structured JSON only.
"""
}

# =========================================================
# USER PROMPT REGISTRY
# =========================================================
USER_PROMPTS = {
# ---------------------------------------------------------
# ROUTER USER PROMPT
# ---------------------------------------------------------
"opportunity_router": """
Analyze the following customer call transcript and classify opportunity type.

Transcript:
{transcript}

Return ONLY JSON:
{{
    "opportunity_type": "",
    "confidence": float
}}
""",


# ---------------------------------------------------------
# UPSSELL EXTRACTOR
# ---------------------------------------------------------
"opportunity_upsell_extractor": """
Extract UPSSELL Opportunity from transcript.

AccountId: {account_id}

Transcript:
{transcript}

Return Salesforce Opportunity JSON:
{{
    "Opportunity_Type": "Upsell",
    "Opportunity_Sub_Type__c": "",
    "AI_Call_Summary__c": "",
    "AI_Confidence_Score__c": 0.0,
    "AI_Intent_Strength__c": "",
    "Competitor_Mentioned__c": "",
    "Opportunity_Urgency__c": "Low|Medium|High",
    "Recommended_Next_Action__c": ""
}}
""",


# ---------------------------------------------------------
# CROSS-SELL EXTRACTOR
# ---------------------------------------------------------
"opportunity_cross_sell_extractor": """
Extract CROSS-SELL Opportunity from transcript.

AccountId: {account_id}

Transcript:
{transcript}

Return Salesforce Opportunity JSON:
{{
    "Opportunity_Type": "Cross-sell",
    "Opportunity_Sub_Type__c": "",
    "AI_Call_Summary__c": "",
    "AI_Confidence_Score__c": 0.0,
    "AI_Intent_Strength__c": "",
    "Competitor_Mentioned__c": "",
    "Opportunity_Urgency__c": "Low|Medium|High",
    "Recommended_Next_Action__c": ""
}}
""",


# ---------------------------------------------------------
# RETENTION EXTRACTOR
# ---------------------------------------------------------
"opportunity_retention_extractor": """
Extract RETENTION Opportunity from transcript.

AccountId: {account_id}

Transcript:
{transcript}

Return Salesforce Opportunity JSON:
{{
    "Opportunity_Type": "Retention",
    "Opportunity_Sub_Type__c": "",
    "AI_Call_Summary__c": "",
    "AI_Confidence_Score__c": 0.0,
    "AI_Intent_Strength__c": "",
    "Competitor_Mentioned__c": "",
    "Opportunity_Urgency__c": "Low|Medium|High",
    "Recommended_Next_Action__c": ""
}}
"""
,
"retention_nba_refiner_user" : """
Analyze the following customer conversation and determine the Next Best Action.

---

## TRANSCRIPT
{transcript}

---

## TASK
Return the single most accurate NBA_Action based on the system rules.
make sure response for key NBA_Action must be one of the following 6 value.
PRICE_OBJECTION_RETENTION
WHITE_GLOVE_SERVICE_RECOVERY
VIP_CONCIERGE_RETENTION
DEVICE_REFRESH_RETENTION
VALUE_BUNDLE_RETENTION
PREMIUM_FEATURE_UPSELL
Return JSON ONLY:
{{
  "NBA_Action": "",
  "confidence": float
}}

""",

    "churn_prediction": """
Analyze customer churn risk.

Transcript:
{transcript}

Return:
{{
    "churn_score": float,
    "risk_factors": [],
    "confidence": float
}}
""",

    "upsell_prediction": """
Analyze upsell opportunities.

Transcript:
{transcript}

Return:
{{
    "upsell": [],
    "cross_sell": [],
    "confidence": float
}}
""",
    "cross_sell_prediction": """
Analyze cross-sell opportunities.

Transcript:
{transcript}

Return:
{{
    "upsell": [],
    "cross_sell": [],
    "confidence": float
}}
""",

    "call_summary": """
Summarize customer call.

Transcript:
{transcript}

Return:
{{
    "call_summary": "",
    "sentiment": "",
    "confidence": float
}}
"""

}
