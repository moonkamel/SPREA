"""Sale signals of the owners of whole buildings (api/sale_signals.py): reads
the BODACC notices of every company in monopro_owners and stores, for those
with recent events, a score and the events (monopro_signals), copied on
their buildings (monopro_buildings.signal_score / signal_level) for the map.

  python scripts/monopro/signals.py [--limit 200] [--dry-run]

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (except with --dry-run).
Run weekly by .github/workflows/monopro-signals.yml.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from api.sale_signals import BODACC_URL, FIELDS, classify, score  # noqa: E402
from import_bdnb import Rest  # noqa: E402

WORKERS = 6


def log(*args):
    print(*args, flush=True)


def get_json(url: str) -> Optional[Dict]:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SPREA"}), timeout=30) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                return None
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 ** attempt)
    return None


def notices(siren: str) -> List[Dict]:
    where = f'registre="{siren}" and familleavis_lib!="Dépôts des comptes"'
    params = {"where": where, "select": FIELDS, "order_by": "dateparution desc", "limit": "40"}
    data = get_json(f"{BODACC_URL}?{urllib.parse.urlencode(params)}")
    return (data or {}).get("results") or []


def signal(siren: str, today: date) -> Optional[Dict]:
    events = [e for r in notices(siren) for e in classify(r)]
    result = score(events, today)
    if not result["score"]:
        return None
    return {"siren": siren, **result, "checked_on": today.isoformat()}


def owner_sirens(rest: Rest) -> List[str]:
    out: List[str] = []
    while True:
        page = json.loads(rest.call("GET", f"monopro_owners?select=siren&order=siren&offset={len(out)}&limit=1000",
                                    prefer="count=none") or b"[]")
        out += [r["siren"] for r in page]
        if len(page) < 1000:
            return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--siren", nargs="*", help="Only these companies (test)")
    args = ap.parse_args()
    today = date.today()
    rest = None if args.dry_run else Rest(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    sirens = args.siren or owner_sirens(rest)
    if args.limit:
        sirens = sirens[:args.limit]
    log(f"{len(sirens)} sociétés à vérifier")

    found: List[Dict] = []
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, s in enumerate(pool.map(lambda x: signal(x, today), sirens), 1):
            if s:
                found.append(s)
            if i % 500 == 0:
                log(f"  {i} vérifiées, {len(found)} avec des signaux")
    found.sort(key=lambda s: -s["score"])
    levels = {lvl: sum(1 for s in found if s["level"] == lvl) for lvl in ("fort", "moyen", "faible")}
    log(f"Signaux : {len(found)} sociétés ({levels})")
    for s in found[:10]:
        log(f"  {s['siren']} {s['score']} {', '.join(e['label'] for e in s['events'][:3])}")
    if args.dry_run:
        return

    # Replaced as a whole: a company whose events got old loses its signal.
    # The explanations already written stay when the events have not changed.
    for i in range(0, len(found), 500):
        rest.call("POST", "monopro_signals?on_conflict=siren", json.dumps(found[i:i + 500]).encode(),
                  "resolution=merge-duplicates,return=minimal")
    rest.call("DELETE", f"monopro_signals?checked_on=lt.{today.isoformat()}")
    rest.call("PATCH", "monopro_buildings?signal_score=not.is.null",
              json.dumps({"signal_score": None, "signal_level": None}).encode())
    for s in found:
        rest.call("PATCH", f"monopro_buildings?owner_siren=eq.{s['siren']}",
                  json.dumps({"signal_score": s["score"], "signal_level": s["level"]}).encode())
    log("Enregistré.")


if __name__ == "__main__":
    main()
