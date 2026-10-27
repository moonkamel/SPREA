"""Figures of the prospection emails sent through Brevo (read-only): per day
and per email of the sequence (tags mail1 to mail4), then the links clicked.
Opens loaded by a proxy (Apple Mail privacy protection, Gmail image cache) are
counted apart: they are not people opening the email.

  BREVO_API_KEY=... python scripts/campaign/brevo_stats.py --days 7 --out stats.md
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta

BREVO = "https://api.brevo.com/v3"


def get(path: str, key: str, params: dict) -> dict:
    url = f"{BREVO}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"api-key": key, "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode() or "{}")


def events(key: str, start: str, end: str):
    """Every event of the prospection emails, page by page."""
    offset = 0
    while True:
        data = get("/smtp/statistics/events", key, {"startDate": start, "endDate": end, "tags": "prospection",
                                                    "limit": 2500, "offset": offset, "sort": "asc"})
        rows = data.get("events") or []
        yield from rows
        if len(rows) < 2500:
            return
        offset += 2500


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f} %" if d else "–"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    key = os.getenv("BREVO_API_KEY", "")
    if not key:
        sys.exit("BREVO_API_KEY manquant")
    end = date.today()
    start = end - timedelta(days=args.days - 1)

    # Per day and per email of the sequence: who received, opened (people / proxies), clicked
    by: dict = defaultdict(lambda: defaultdict(set))
    links: Counter = Counter()
    kinds: Counter = Counter()
    for e in events(key, start.isoformat(), end.isoformat()):
        day = (e.get("date") or "")[:10]
        # One tag (« tag ») or several (« tags »), depending on the event
        tags = e.get("tags") or ([e["tag"]] if e.get("tag") else [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        step = next((t for t in tags if t.startswith("mail")), "mail?")
        kind = e.get("event") or ""
        kinds[kind] += 1
        who = (e.get("email") or "").lower()
        for k in ((day, step), ("total", step), ("total", "tous")):
            by[k][kind].add(who)
        if kind == "clicks" and e.get("link"):
            links[urllib.parse.urlsplit(e["link"])._replace(query="").geturl()] += 1

    lines = [f"# Prospection Brevo du {start:%d/%m} au {end:%d/%m/%Y}", "",
             "| Jour | Mail | Envoyés | Délivrés | Ouvertures (personnes) | Chargés par proxy | Clics | Désinscrits | Rebonds |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for (day, step) in sorted(by, key=lambda k: (k[0] == "total", k)):
        s = by[(day, step)]
        sent = len(s["requests"])
        delivered = len(s["delivered"])
        proxy = s["proxy_open"] | s["proxyOpen"] | s["loadedByProxy"]
        people = (s["opened"] | s["unique_opened"]) - proxy
        clicked = s["clicks"]
        lines.append(f"| {day} | {step} | {sent} | {delivered} | {len(people)} ({pct(len(people), delivered)}) | {len(proxy)} | "
                     f"{len(clicked)} ({pct(len(clicked), delivered)}) | {len(s['unsubscribed'])} | "
                     f"{len(s['hardBounces'] | s['softBounces'] | s['blocked'])} |")
    lines += ["", "## Liens cliqués", ""]
    lines += [f"- {n} × {link}" for link, n in links.most_common(20)] or ["Aucun clic pour l'instant."]
    lines += ["", "_Événements reçus : " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) + "_"]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
