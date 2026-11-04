"""Keep in the database the registered office and officers of the companies that own
the buildings of the TCE campaign (monopro_owners.company), read from the Annuaire des
entreprises at a pace it accepts. The signed dossier links then show them even when the
Annuaire refuses the site's request (api/monopro.py company_for). Read-only on the
Annuaire; writes only those two columns.

  python scripts/apify/prefill_companies.py [--all]   # --all: every owner of an F/G building in 59 and 62
"""
import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.monopro import COMPANY_URL, company_details  # noqa: E402

URL, KEY = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
PAUSE = 0.6  # the Annuaire accepts a few requests per second from one address


def owners_to_fill(client: httpx.Client, every: bool) -> list:
    params = {"select": "owner_siren", "owner_siren": "not.is.null", "dep": "in.(59,62)", "limit": "5000"}
    if not every:
        params["dpe_label"] = "in.(F,G)"
    sirens = sorted({b["owner_siren"] for b in client.get(f"{URL}/rest/v1/monopro_buildings", params=params,
                                                          headers=HEADERS).json()})
    done = set()
    for i in range(0, len(sirens), 150):
        rows = client.get(f"{URL}/rest/v1/monopro_owners", headers=HEADERS, params={
            "select": "siren,company", "siren": f"in.({','.join(sirens[i:i + 150])})"}).json()
        done |= {r["siren"] for r in rows if r.get("company")}
    return [s for s in sirens if s not in done]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    filled = refused = missing = 0
    with httpx.Client(timeout=20) as client:
        todo = owners_to_fill(client, args.all)
        print(f"{len(todo)} sociétés sans siège ni dirigeant gardés", flush=True)
        for n, siren in enumerate(todo, 1):
            res = None
            for attempt in range(5):
                res = client.get(COMPANY_URL, params={"q": siren, "per_page": 1})
                if res.status_code != 429:
                    break
                time.sleep(5 * (attempt + 1))
            if res is None or res.status_code != 200:
                refused += 1
                continue
            hits = [r for r in res.json().get("results") or [] if r.get("siren") == siren]
            if not hits:
                missing += 1
                continue
            client.patch(f"{URL}/rest/v1/monopro_owners", params={"siren": f"eq.{siren}"}, headers=HEADERS,
                         json={"company": company_details(hits[0]), "company_at": datetime.now(timezone.utc).isoformat()}
                         ).raise_for_status()
            filled += 1
            if n % 50 == 0:
                print(f"  {n} traitées", flush=True)
            time.sleep(PAUSE)
    print(f"Bilan : {filled} gardées, {missing} absentes de l'Annuaire, {refused} refusées")


if __name__ == "__main__":
    main()
