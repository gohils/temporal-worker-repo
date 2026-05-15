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


# ---------------------------------------------------------
# RETENTION EXTRACTOR (STEP 2)
# ---------------------------------------------------------
"opportunity_retention_extractor": """
You are a Salesforce Opportunity extraction engine.

Given:
Opportunity Type = Retention

Valid Sub-Types:
- Price Objection
- Service Dissatisfaction
- Competitive Threat
- Contract Renewal Risk
- Feature Gap Frustration

Rules:
- Competitor mentions are HIGH PRIORITY
- Output ONLY valid JSON
- No explanations
""",
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
