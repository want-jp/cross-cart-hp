"""n8n webhook service for fetching personal information (addresses).

Cloud Run → n8n Webhook (POST /webhook/tracking-address) → Sales Order Data Table → JSON

Sales Order Data Table fields:
  deliveryName, deliveryAddress1, deliveryAddress2, deliveryCity,
  deliveryState, deliveryZipCode, deliveryCountry, deliveryPhoneNumber,
  billingName, billingAddress1, billingAddress2, billingCity,
  billingState, billingZipCode, billingCountry, billingPhoneNumber
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import N8N_WEBHOOK_URL, N8N_API_KEY

logger = logging.getLogger(__name__)


@dataclass
class Address:
    name: str
    line1: str
    line2: str | None
    city: str
    state: str | None
    postal_code: str
    country: str
    phone: str | None = None


@dataclass
class PersonalInfo:
    shipping_address: Address
    billing_address: Address
    email: str | None = None


def _parse_response(data: dict) -> PersonalInfo:
    """Parse n8n webhook response (Sales Order Data Table row) into PersonalInfo."""
    return PersonalInfo(
        shipping_address=Address(
            name=data.get("deliveryName", ""),
            line1=data.get("deliveryAddress1", ""),
            line2=data.get("deliveryAddress2") or None,
            city=data.get("deliveryCity", ""),
            state=data.get("deliveryState") or None,
            postal_code=data.get("deliveryZipCode", ""),
            country=data.get("deliveryCountry", ""),
            phone=data.get("deliveryPhoneNumber") or None,
        ),
        billing_address=Address(
            name=data.get("billingName", ""),
            line1=data.get("billingAddress1", ""),
            line2=data.get("billingAddress2") or None,
            city=data.get("billingCity", ""),
            state=data.get("billingState") or None,
            postal_code=data.get("billingZipCode", ""),
            country=data.get("billingCountry", ""),
            phone=data.get("billingPhoneNumber") or None,
        ),
        email=data.get("email") or None,
    )


def _mock_personal_info() -> PersonalInfo:
    """Return mock personal info for development."""
    return PersonalInfo(
        shipping_address=Address(
            name="Daniel Lee",
            line1="44 Early Ave Unit 2",
            line2=None,
            city="Medford",
            state="Massachusetts",
            postal_code="02155",
            country="US",
            phone="+1 8169776694",
        ),
        billing_address=Address(
            name="Daniel Lee",
            line1="44 Early Ave Unit 2",
            line2=None,
            city="Medford",
            state="Massachusetts",
            postal_code="02155",
            country="US",
            phone="+1 8169776694",
        ),
        email="danielkuangpulee@sbcglobal.net",
    )


async def get_personal_info(order_id: str) -> PersonalInfo | None:
    """Fetch personal info from n8n webhook (or mock if USE_MOCK_DATA)."""
    from app.config import USE_MOCK_DATA
    if USE_MOCK_DATA:
        return _mock_personal_info()

    if not N8N_WEBHOOK_URL:
        return None

    headers = {}
    if N8N_API_KEY:
        headers["X-API-Key"] = N8N_API_KEY

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                N8N_WEBHOOK_URL,
                json={"order_id": order_id},
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data or (isinstance(data, list) and len(data) == 0):
                return None

            # n8n may return a single object or a list
            row = data[0] if isinstance(data, list) else data
            return _parse_response(row)
    except Exception:
        logger.exception("Failed to fetch personal info from n8n webhook")
        return None
