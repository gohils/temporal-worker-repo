from wf_ai_fastapi.routers.prompts.cc_router import SYSTEM_PROMPT as ROUTER_SYSTEM, USER_PROMPT as ROUTER_USER
from wf_ai_fastapi.routers.prompts.cc_retention import SYSTEM_PROMPT as RETENTION_SYSTEM, USER_PROMPT as RETENTION_USER
from wf_ai_fastapi.routers.prompts.cc_upsell import SYSTEM_PROMPT as UPSELL_SYSTEM, USER_PROMPT as UPSELL_USER
from wf_ai_fastapi.routers.prompts.cc_cross_sell import SYSTEM_PROMPT as CROSS_SELL_SYSTEM, USER_PROMPT as CROSS_SELL_USER
from wf_ai_fastapi.routers.prompts.cc_next_best_campaign import SYSTEM_PROMPT as NBC_SYSTEM, USER_PROMPT as NBC_USER


PROMPTS = {
    "opportunity_router": {
        "system": ROUTER_SYSTEM,
        "user": ROUTER_USER,
    },

    "opportunity_retention_extractor": {
        "system": RETENTION_SYSTEM,
        "user": RETENTION_USER,
    },

    "opportunity_upsell_extractor": {
        "system": UPSELL_SYSTEM,
        "user": UPSELL_USER,
    },

    "opportunity_cross_sell_extractor": {
        "system": CROSS_SELL_SYSTEM,
        "user": CROSS_SELL_USER,
    },

    "ai_retention_campaign_router": {
        "system": NBC_SYSTEM,
        "user": NBC_USER,
    }
}