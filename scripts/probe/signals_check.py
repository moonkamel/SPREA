"""Live check of /api/signals on a real area (central Lille), run from a
GitHub runner: rows fetched from ADEME, their dates, DVF sales per commune,
and the best scores. Read-only."""
import asyncio
import collections
import os
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api import prospection, signals  # noqa: E402

BBOX = os.getenv("BBOX", "3.040,50.625,3.075,50.645")


async def main():
    t = time.time()
    found = await prospection.search(BBOX, list(prospection.LABELS), since="2024-10-30")
    dates = sorted((d["date"] or "") for a in found["addresses"] for d in a["dpe"])
    print(f"ADEME: {len(found['addresses'])} adresses, total {found['total']}, tronqué {found['truncated']}, {time.time() - t:.1f}s")
    print("  dates DPE: min", dates[:1], "max", dates[-1:], "par mois:",
          sorted(collections.Counter(d[:7] for d in dates).items())[-8:])
    insee = collections.Counter(a.get("insee") for a in found["addresses"])
    print("  communes:", insee.most_common(5))
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        for c, _ in [x for x in insee.most_common(3) if x[0] and x[0][:1].isdigit()][:1]:
            t = time.time()
            try:
                data = await signals.commune_sales(client, c, date.today())
                print(f"DVF {c}: {len(data['sales'])} ventes depuis {data['since']}, {time.time() - t:.1f}s,",
                      "avec numéro:", sum(1 for s in data["sales"] if s.get("number")))
            except Exception:
                traceback.print_exc()
    t = time.time()
    res = await signals.area_signals(BBOX, None)
    print(f"Signaux: {res['total']} adresses, forts {res['strong']}, DVF depuis {res['dvf_since']}, {time.time() - t:.1f}s")
    print("  répartition des raisons:", collections.Counter(r["kind"] for x in res["items"] for r in x["reasons"]))
    for x in res["items"][:5]:
        print("  ", x["score"], x["address"], [r["label"][:40] for r in x["reasons"]])
    t = time.time()
    sales = await signals.area_sales(BBOX, 12)
    print(f"Ventes 12 mois: {len(sales['sales'])}, dernière {sales['latest']}, {time.time() - t:.1f}s")
    for x in sales["sales"][:3]:
        print("  ", x["date"], x["kind"], x["street"], x["price_m2"])


asyncio.run(main())
