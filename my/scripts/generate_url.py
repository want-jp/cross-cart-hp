#!/usr/bin/env python3
"""Generate a tracking URL with HMAC signature.

Usage:
    python scripts/generate_url.py <sales_order_id>
    python scripts/generate_url.py   # uses sample ID
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security import generate_signature


def main():
    if len(sys.argv) == 2:
        order_id = sys.argv[1]
    else:
        order_id = "C-01KNTSX8ZCRRPRGNTCGS3R55XR"

    sig = generate_signature(order_id)
    base_url = os.environ.get("BASE_URL", "http://localhost:8080")

    print(f"Order ID:  {order_id}")
    print(f"Signature: {sig}")
    print()
    print(f"URL: {base_url}/{order_id}/{sig}")


if __name__ == "__main__":
    main()
