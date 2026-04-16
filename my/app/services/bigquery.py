"""BigQuery service for fetching order data.

When USE_MOCK_DATA is True, returns mock data for development.
All queries use the datalake dataset for freshest data.

Data sources (cross-cart.datalake):
- sales_orders               受注
- sales_order_events         受注イベント（status: 11=placed, 21=shipped, 50=cancelled）
- sales_order_products       受注商品（商品名・数量・単価）
- sales_order_prices         価格明細（JSON: oversea_shipping_costs, domestic_shipping_costs）
- purchase_orders            国内注文
- purchase_order_events      国内注文イベント（status: 1=created, 2=shop shipped, 3=cancelled）
- delivery_orders            配送注文（tracking_number, courier_code）
- payment_orders             決済（payment_method: integer）
- sellers                    ショップ情報（name, url）
- vendor_product_images      商品画像
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import USE_MOCK_DATA, GCP_PROJECT

logger = logging.getLogger(__name__)

# Tracking URL patterns for carriers
TRACKING_URLS: dict[str, str] = {
    "EMS": "https://trackings.post.japanpost.jp/services/srv/search/?requestNo1={tn}&search.x=1&search.y=1&locale=en",
    "ECMS": "https://www.ecmsglobal.com/track?documentCode={tn}",
    "Fedex-P": "https://www.fedex.com/fedextrack/?trknbr={tn}",
    "FedEx": "https://www.fedex.com/fedextrack/?trknbr={tn}",
}

AFTERSHIP_URL = "https://wantjapan.aftership.com/{tn}"


@dataclass
class OrderItem:
    name: str
    quantity: int
    price: float
    currency: str = "USD"
    image_url: str | None = None
    variation: str | None = None


@dataclass
class ShippingInfo:
    carrier: str
    tracking_number: str
    tracking_url: str
    aftership_url: str
    shipped_date: str


@dataclass
class PriceBreakdown:
    items_subtotal: float
    domestic_shipping: float
    international_shipping: float
    handling_fee: float
    payment_fee: float
    total: float
    currency: str = "USD"


@dataclass
class ShopInfo:
    name: str
    url: str


@dataclass
class OrderData:
    order_id: str
    status: str  # "placed", "shipped_domestic", "shipped_international", "cancelled"
    order_date: str
    items: list[OrderItem] = field(default_factory=list)
    price: PriceBreakdown | None = None
    shipments: list[ShippingInfo] = field(default_factory=list)
    shop: ShopInfo | None = None
    payment_method: str = ""
    shipping_service: str = ""


def _build_tracking_url(carrier: str, tracking_number: str) -> str:
    """Build a tracking URL for the given carrier and tracking number."""
    template = TRACKING_URLS.get(carrier, "")
    if template:
        return template.format(tn=tracking_number)
    return ""


_MOCK_SCENARIOS: dict[str, dict] = {
    "placed": {"status": "placed", "shipments": []},
    "shipped_domestic": {"status": "shipped_domestic", "shipments": []},
    "shipped_international": {
        "status": "shipped_international",
        "shipments": [
            ShippingInfo(
                carrier="ECMS",
                tracking_number="ECOFLXX019725670",
                tracking_url=_build_tracking_url("ECMS", "ECOFLXX019725670"),
                aftership_url=AFTERSHIP_URL.format(tn="ECOFLXX019725670"),
                shipped_date="2026-04-10",
            ),
            ShippingInfo(
                carrier="ECMS",
                tracking_number="ECOFLXX019725671",
                tracking_url=_build_tracking_url("ECMS", "ECOFLXX019725671"),
                aftership_url=AFTERSHIP_URL.format(tn="ECOFLXX019725671"),
                shipped_date="2026-04-11",
            ),
        ],
    },
    "cancelled": {"status": "cancelled", "shipments": []},
}


def _mock_order(order_id: str) -> OrderData:
    """Return mock order data for development.

    Set MOCK_STATUS env var to test different statuses:
    placed, shipped_domestic, shipped_international, cancelled
    """
    import os
    scenario_key = os.environ.get("MOCK_STATUS", "shipped_domestic")
    scenario = _MOCK_SCENARIOS.get(scenario_key, _MOCK_SCENARIOS["shipped_domestic"])

    return OrderData(
        order_id=order_id,
        status=scenario["status"],
        order_date="2026-02-04",
        items=[
            OrderItem(
                name="スノープランナー：ニューシーズン",
                quantity=1,
                price=16720.0,
                currency="JPY",
                image_url="https://baseec-img-mng.akamaized.net/images/item/origin/7511b287ac2c7c57011519ba2dc2551a.png",
            ),
            OrderItem(
                name="スノープランナー",
                quantity=1,
                price=16720.0,
                currency="JPY",
                image_url="https://baseec-img-mng.akamaized.net/images/item/origin/d45a61ed51d6c0541b43fc0d98cef5a0.png",
            ),
            OrderItem(
                name="スノープランナー：ニューチャレンジ",
                quantity=1,
                price=16720.0,
                currency="JPY",
                image_url="https://baseec-img-mng.akamaized.net/images/item/origin/77ca6183dd8d3e8da8f16759360728b3.png",
            ),
        ],
        price=PriceBreakdown(
            items_subtotal=16720.0,
            domestic_shipping=640.0,
            international_shipping=10164.0,
            handling_fee=1672.0,
            payment_fee=822.0,
            total=29379.0,
            currency="JPY",
        ),
        shipments=scenario["shipments"],
        shop=ShopInfo(name="14games", url="https://14games.base.shop/"),
        payment_method="American Express",
        shipping_service="FedEx Priority",
    )


PAYMENT_METHOD_MAP: dict[int, str] = {
    1: "Visa", 2: "Mastercard", 3: "Amex", 4: "Diners", 5: "JCB",
    11: "PayPal", 21: "Apple Pay", 22: "Google Pay", 23: "Alipay", 24: "WeChat Pay",
    99: "Unknown",
}


def _resolve_status(
    max_sales_event: int,
    max_purchase_event: int,
    has_delivery: bool,
) -> str:
    """Resolve tracking page status from datalake event statuses.

    sales_order_events:  11=placed, 21=shipped, 50=cancelled
    purchase_order_events: 1=created, 2=shop shipped, 3=cancelled
    delivery_orders: exists with tracking_number = shipped internationally
    """
    if max_sales_event >= 50:
        return "cancelled"
    if has_delivery:
        return "shipped_international"
    if max_purchase_event >= 2:
        return "shipped_domestic"
    return "placed"


async def get_order_data(order_id: str) -> OrderData | None:
    """Fetch order data from BigQuery datalake (or mock)."""
    if USE_MOCK_DATA:
        return _mock_order(order_id)

    import json
    from google.cloud import bigquery

    client = bigquery.Client(project=GCP_PROJECT)
    params = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("order_id", "STRING", order_id),
        ]
    )

    # 1) Core order data — all from datalake
    order_query = f"""
    SELECT
        so.id AS order_id,
        so.ordered_at,
        sop_price.selling_price_currency AS currency,
        sop_price.selling_price_amount AS total,
        sop_price.product_cost_amount AS subtotal,
        sop_price.want_margin_amount AS handling_fee,
        sop_price.payment_fee_amount AS payment_fee,
        sop_price.oversea_shipping_costs,
        sop_price.domestic_shipping_costs,
        po_pay.payment_method AS payment_method_id,
        (SELECT MAX(se.status) FROM `{GCP_PROJECT}.datalake.sales_order_events` se
         WHERE se.sales_order_id = @order_id) AS max_sales_event,
        (SELECT MAX(pe.status) FROM `{GCP_PROJECT}.datalake.purchase_order_events` pe
         JOIN `{GCP_PROJECT}.datalake.purchase_orders` po ON pe.purchase_order_id = po.id
         WHERE po.sales_order_id = @order_id) AS max_purchase_event,
        (SELECT COUNT(*) FROM `{GCP_PROJECT}.datalake.delivery_orders` d
         WHERE d.sales_order_id = @order_id AND d.tracking_number IS NOT NULL) AS delivery_count
    FROM `{GCP_PROJECT}.datalake.sales_orders` so
    LEFT JOIN `{GCP_PROJECT}.datalake.sales_order_prices` sop_price ON so.id = sop_price.sales_order_id
    LEFT JOIN `{GCP_PROJECT}.datalake.payment_orders` po_pay ON so.id = po_pay.sales_order_id
    WHERE so.id = @order_id
    LIMIT 1
    """

    try:
        result = client.query(order_query, job_config=params).result()
        rows = list(result)
    except Exception:
        logger.exception("BigQuery order query failed")
        return None

    if not rows:
        return None

    row = rows[0]

    # Resolve status
    status = _resolve_status(
        max_sales_event=row.max_sales_event or 0,
        max_purchase_event=row.max_purchase_event or 0,
        has_delivery=(row.delivery_count or 0) > 0,
    )

    # Parse shipping costs from JSON strings
    intl_shipping = 0.0
    shipping_service = ""
    if row.oversea_shipping_costs:
        try:
            costs = json.loads(row.oversea_shipping_costs)
            if costs:
                intl_shipping = float(costs[0].get("amount", 0))
                shipping_service = costs[0].get("courierCode", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    domestic_shipping = 0.0
    if row.domestic_shipping_costs:
        try:
            costs = json.loads(row.domestic_shipping_costs)
            if costs:
                domestic_shipping = float(costs[0].get("amount", 0))
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    currency = row.currency or "JPY"
    payment_method = PAYMENT_METHOD_MAP.get(row.payment_method_id or 99, "Unknown")

    price = PriceBreakdown(
        items_subtotal=float(row.subtotal or 0),
        domestic_shipping=domestic_shipping,
        international_shipping=intl_shipping,
        handling_fee=float(row.handling_fee or 0),
        payment_fee=float(row.payment_fee or 0),
        total=float(row.total or 0),
        currency=currency,
    )

    # 2) Shipments
    shipments: list[ShippingInfo] = []
    if status == "shipped_international":
        shipments_query = f"""
        SELECT tracking_number, courier_code, created_at
        FROM `{GCP_PROJECT}.datalake.delivery_orders`
        WHERE sales_order_id = @order_id AND tracking_number IS NOT NULL
        ORDER BY created_at
        """
        try:
            shipments_result = client.query(shipments_query, job_config=params).result()
            for s_row in shipments_result:
                carrier = s_row.courier_code or shipping_service or ""
                shipments.append(ShippingInfo(
                    carrier=carrier,
                    tracking_number=s_row.tracking_number,
                    tracking_url=_build_tracking_url(carrier, s_row.tracking_number),
                    aftership_url=AFTERSHIP_URL.format(tn=s_row.tracking_number),
                    shipped_date=str(s_row.created_at.date()) if s_row.created_at else "",
                ))
        except Exception:
            logger.exception("BigQuery shipments query failed")

    # 3) Order items
    items_query = f"""
    SELECT
        sop.name,
        sop.variation_name,
        sop.qty,
        sop.unit_price_amount,
        sop.unit_price_currency,
        vpi.url AS image_url
    FROM `{GCP_PROJECT}.datalake.sales_order_products` sop
    LEFT JOIN (
        SELECT vendor_product_id, url,
               ROW_NUMBER() OVER (PARTITION BY vendor_product_id ORDER BY seq) AS rn
        FROM `{GCP_PROJECT}.datalake.vendor_product_images`
    ) vpi ON vpi.vendor_product_id = sop.vendor_product_id AND vpi.rn = 1
    WHERE sop.sales_order_id = @order_id
    ORDER BY sop.created_at
    """

    items: list[OrderItem] = []
    try:
        items_result = client.query(items_query, job_config=params).result()
        for item_row in items_result:
            items.append(OrderItem(
                name=item_row.name or "",
                variation=item_row.variation_name or None,
                quantity=item_row.qty or 1,
                price=float(item_row.unit_price_amount or 0),
                currency=item_row.unit_price_currency or currency,
                image_url=item_row.image_url,
            ))
    except Exception:
        logger.exception("BigQuery items query failed")

    # 4) Shop info
    shop = None
    shop_query = f"""
    SELECT DISTINCT s.name, s.url
    FROM `{GCP_PROJECT}.datalake.sales_order_products` sop
    JOIN `{GCP_PROJECT}.datalake.sellers` s ON sop.product_seller_id = s.id
    WHERE sop.sales_order_id = @order_id
    LIMIT 1
    """
    try:
        shop_result = client.query(shop_query, job_config=params).result()
        for shop_row in shop_result:
            if shop_row.name:
                shop = ShopInfo(name=shop_row.name, url=shop_row.url or "")
    except Exception:
        logger.exception("BigQuery shop query failed")

    return OrderData(
        order_id=order_id,
        status=status,
        order_date=str(row.ordered_at.date()) if row.ordered_at else "",
        items=items,
        price=price,
        shipments=shipments,
        shop=shop,
        payment_method=payment_method,
        shipping_service=shipping_service,
    )
