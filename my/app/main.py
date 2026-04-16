from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import SUPPORTED_LANGS, DEFAULT_LANG, INTERNAL_API_KEY
from app.security import generate_signature, verify_signature, is_valid_order_id
from app.i18n import get_translations
from app.services.bigquery import get_order_data
from app.services.n8n import get_personal_info

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Cross Cart Order Tracking", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _detect_lang(request: Request) -> str:
    """Detect language from query param or Accept-Language header."""
    lang = request.query_params.get("lang", "").lower()
    if lang in SUPPORTED_LANGS:
        return lang
    accept = request.headers.get("accept-language", "")
    if "zh" in accept:
        return "zh"
    return DEFAULT_LANG


@app.get("/{order_id}/{signature}", response_class=HTMLResponse)
async def order_tracking(
    request: Request,
    order_id: str,
    signature: str,
):
    lang = _detect_lang(request)
    t = get_translations(lang)

    # Validate order ID format (ULID-based: C-xxx)
    if not is_valid_order_id(order_id):
        return templates.TemplateResponse(
            "preparing.html",
            {"request": request, "t": t, "lang": lang},
        )

    # Verify HMAC signature
    if not verify_signature(order_id, signature):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "t": t, "lang": lang, "status_code": 403},
            status_code=403,
        )

    # Fetch order data
    order = await get_order_data(order_id)
    if order is None:
        return templates.TemplateResponse(
            "preparing.html",
            {"request": request, "t": t, "lang": lang},
        )

    # Fetch personal info (addresses) from n8n webhook if configured
    personal_info = await get_personal_info(order_id)

    return templates.TemplateResponse(
        "order.html",
        {
            "request": request,
            "t": t,
            "lang": lang,
            "order": order,
            "personal_info": personal_info,
            "order_id": order_id,
            "signature": signature,
        },
    )


class GenerateUrlRequest(BaseModel):
    orderId: str


@app.post("/api/generate-url")
async def generate_url(body: GenerateUrlRequest, x_api_key: str = Header()):
    if not INTERNAL_API_KEY or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not is_valid_order_id(body.orderId):
        raise HTTPException(status_code=400, detail="Invalid order ID format")
    sig = generate_signature(body.orderId)
    return {
        "orderId": body.orderId,
        "signature": sig,
        "myOrderUrl": f"https://my.cross-cart.jp/{body.orderId}/{sig}",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
