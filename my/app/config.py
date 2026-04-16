import os

# HMAC secret for URL signature verification
HMAC_SECRET: str = os.environ.get("TRACKING_HMAC_SECRET", "dev-secret-change-in-production")

# GCP / BigQuery
GCP_PROJECT: str = os.environ.get("GCP_PROJECT", "")
BQ_DATASET: str = os.environ.get("BQ_DATASET", "")

# n8n
N8N_WEBHOOK_URL: str = os.environ.get("N8N_WEBHOOK_URL", "")
N8N_API_KEY: str = os.environ.get("N8N_API_KEY", "")

# Internal API
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")

# App settings
USE_MOCK_DATA: bool = os.environ.get("USE_MOCK_DATA", "true").lower() == "true"
DEFAULT_LANG: str = "en"
SUPPORTED_LANGS: list[str] = ["en", "zh"]

# Contact
CONTACT_EMAIL: str = os.environ.get("CONTACT_EMAIL", "support@cross-cart.jp")
