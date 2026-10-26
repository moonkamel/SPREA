"""Creates what the site needs in a Stripe account (live or test, from the key):
the subscription prices found by lookup key, the one-off report price and the
webhook endpoint. Idempotent: what already exists is kept. Prints the price ids
to put in Vercel; the webhook signing secret is never printed (Stripe dashboard >
Webhooks > Reveal).
    STRIPE_SECRET_KEY=sk_live_... python scripts/stripe/setup_live.py
"""
import json
import os
import sys

import requests

API = "https://api.stripe.com/v1"
KEY = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://sprea.app/api/stripe/webhook")
# Same events as api/accounts.py stripe_webhook
EVENTS = ["checkout.session.completed", "checkout.session.async_payment_succeeded",
          "customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"]
# Electronically supplied services
TAX_CODE = "txcd_10000000"
# Amounts TTC (cents), as shown on the site
PLANS = {
    "solo_monthly": ("SPREA Solo", 7900, "month"),
    "solo_yearly": ("SPREA Solo", 79000, "year"),
    "agence_monthly": ("SPREA Agence (par agent)", 5900, "month"),
    "agence_yearly": ("SPREA Agence (par agent)", 59000, "year"),
    "report_single": ("Rapport SPREA", 3900, None),
}


def call(method, path, **params):
    r = requests.request(method, API + path, auth=(KEY, ""), data=params if method == "POST" else None,
                         params=params if method == "GET" else None, timeout=30)
    body = r.json()
    if r.status_code >= 400:
        sys.exit(f"{method} {path}: {body.get('error', {}).get('message')}")
    return body


def product(name):
    for p in call("GET", "/products", active="true", limit=100)["data"]:
        if p["name"] == name:
            return p["id"]
    return call("POST", "/products", name=name, tax_code=TAX_CODE)["id"]


mode = "live" if KEY.startswith(("sk_live_", "rk_live_")) else "test"
out = {"mode": mode, "prices": {}}
for key, (name, amount, interval) in PLANS.items():
    found = call("GET", "/prices", **{"lookup_keys[]": key, "active": "true"})["data"]
    if found:
        price, status = found[0], "existant"
    else:
        params = {"product": product(name), "unit_amount": amount, "currency": "eur",
                  "tax_behavior": "inclusive", "lookup_key": key}
        if interval:
            params["recurring[interval]"] = interval
        price, status = call("POST", "/prices", **params), "créé"
    out["prices"][key] = {"id": price["id"], "montant": price["unit_amount"] / 100, "statut": status}

hooks = [w for w in call("GET", "/webhook_endpoints", limit=100)["data"] if w["url"] == WEBHOOK_URL]
if hooks:
    out["webhook"] = {"id": hooks[0]["id"], "statut": "existant", "événements": hooks[0]["enabled_events"]}
else:
    params = {"url": WEBHOOK_URL, "description": "SPREA"}
    for i, e in enumerate(EVENTS):
        params[f"enabled_events[{i}]"] = e
    w = call("POST", "/webhook_endpoints", **params)
    out["webhook"] = {"id": w["id"], "statut": "créé", "événements": EVENTS}

out["vercel"] = {"STRIPE_PRICE_PRO": out["prices"]["solo_monthly"]["id"],
                 "STRIPE_PRICE_REPORT": out["prices"]["report_single"]["id"]}
print(json.dumps(out, ensure_ascii=False, indent=1))
os.makedirs("stripe-report", exist_ok=True)
with open("stripe-report/setup.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
