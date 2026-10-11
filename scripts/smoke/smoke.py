"""Production smoke test: public pages, SEO files, API health, access control
of private endpoints, security headers, response times. Read-only.

  python scripts/smoke/smoke.py https://sprea.app
"""
import os
import re
import sys
import time

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://sprea.app").rstrip("/")
PAGES = ["/", "/tarifs", "/demo", "/cgv", "/mentions-legales", "/confidentialite", "/observatoire", "/observatoire/nord-59",
         "/observatoire/paris-75", "/prospection", "/rejoindre"]
PLACEHOLDER = re.compile(r"TODO|lorem ipsum|XXX|à compléter|\[[A-Z ]{4,}\]|example\.com", re.I)
# Private endpoints: never open without a session
PRIVATE = [("GET", "/api/me"), ("GET", "/api/search-dpe/2659E2384457J"), ("GET", "/api/search-address?q=1%20rue%20de%20Paris%20Lille"),
           ("GET", "/api/market-price?insee=59350&building_type=Maison&surface=80"), ("POST", "/api/simulate"),
           ("GET", "/api/prospection?bbox=3.05,50.62,3.08,50.64&labels=F,G"), ("GET", "/api/rge?lat=50.63&lon=3.06&works=iti"),
           ("GET", "/api/immeuble?dpe=2659E2384457J"), ("GET", "/api/monopro?bbox=3.05,50.62,3.08,50.64"),
           ("GET", "/api/alerts"), ("GET", "/api/leads"), ("GET", "/api/copro-docs"), ("GET", "/api/team"),
           ("GET", "/api/agent-page"), ("POST", "/api/reports"), ("POST", "/api/valuation"), ("POST", "/api/billing/portal"),
           ("GET", "/api/cron/alerts"), ("GET", "/api/cron/copro-docs")]
HEADERS = ["strict-transport-security", "x-content-type-options", "referrer-policy", "x-frame-options"]

problems, lines = [], []


def check(ok: bool, message: str):
    if not ok:
        problems.append(message)


with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "SPREA-smoke/1.0"}) as client:
    for path in PAGES:
        t = time.time()
        r = client.get(BASE + path)
        dt = time.time() - t
        title = re.search(r"<title>(.*?)</title>", r.text, re.S)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", r.text, re.S)
        lines.append(f"{r.status_code} {dt:4.1f}s {path} | {title.group(1)[:70] if title else 'SANS TITRE'} | h1 prérendu : {'oui' if h1 else 'non'}")
        check(r.status_code == 200, f"{path} : HTTP {r.status_code}")
        check(bool(title), f"{path} : pas de <title>")
        check(dt < 5, f"{path} : {dt:.1f} s")
        m = PLACEHOLDER.search(r.text)
        check(not m, f"{path} : texte provisoire « {m.group(0) if m else ''} »")
    r = client.get(BASE + "/page-qui-n-existe-pas")
    lines.append(f"{r.status_code} page inexistante")
    for path in ["/robots.txt", "/sitemap.xml", "/og.jpg", "/favicon.svg"]:
        r = client.get(BASE + path)
        check(r.status_code == 200, f"{path} : HTTP {r.status_code}")
        if path == "/sitemap.xml":
            urls = re.findall(r"<loc>(.*?)</loc>", r.text)
            lines.append(f"sitemap : {len(urls)} URL, domaine {set(re.sub(r'(https?://[^/]+).*', r'\1', u) for u in urls)}")
            check(all(u.startswith(BASE) for u in urls), "sitemap : URL hors du domaine de production")
        if path == "/robots.txt":
            lines.append("robots.txt : " + r.text.strip().replace("\n", " | ")[:200])
    # API
    for path, key in [("/api/config", None), ("/api/works", "works"), ("/api/observatoire", None)]:
        t = time.time()
        r = client.get(BASE + path)
        dt = time.time() - t
        ok = r.status_code == 200
        try:
            body = r.json()
        except ValueError:
            body, ok = None, False
        lines.append(f"{r.status_code} {dt:4.1f}s {path}" + (f" | clés : {sorted(body)[:12]}" if isinstance(body, dict) else ""))
        check(ok, f"{path} : HTTP {r.status_code} ou réponse non JSON")
        if path == "/api/config" and isinstance(body, dict):
            for k in ("auth_enabled", "billing_enabled"):
                check(body.get(k) is True, f"/api/config : {k} = {body.get(k)}")
    for method, path in PRIVATE:
        r = client.request(method, BASE + path, json={} if method in ("POST", "PUT") else None)
        lines.append(f"{r.status_code} {method} {path} (sans session)")
        check(r.status_code in (401, 403, 405, 422, 429), f"{method} {path} accessible sans session : HTTP {r.status_code}")
    r = client.post(BASE + "/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=faux"})
    lines.append(f"{r.status_code} webhook Stripe avec une fausse signature")
    check(r.status_code in (400, 401, 403), f"webhook Stripe accepté avec une fausse signature : HTTP {r.status_code}")
    # Headers and redirects
    r = client.get(BASE + "/")
    for h in HEADERS:
        lines.append(f"en-tête {h} : {r.headers.get(h, 'ABSENT')}")
        check(h in r.headers, f"en-tête de sécurité absent : {h}")
    r = httpx.get(BASE.replace("https://", "http://") + "/", follow_redirects=False, timeout=20)
    lines.append(f"http:// → {r.status_code} {r.headers.get('location', '')}")
    check(r.status_code in (301, 302, 307, 308), "http:// ne redirige pas vers https://")
    for alias in ("https://www.sprea.app/", "https://sprea.vercel.app/"):
        try:
            r = httpx.get(alias, follow_redirects=False, timeout=20)
            lines.append(f"{alias} → {r.status_code} {r.headers.get('location', '')}")
        except httpx.HTTPError as e:
            lines.append(f"{alias} → {type(e).__name__}")

text = "## Test de production : " + ("aucun problème" if not problems else f"{len(problems)} problème(s)") + "\n\n"
text += "\n".join(f"- ✗ {p}" for p in problems) + ("\n\n" if problems else "") + "```\n" + "\n".join(lines) + "\n```\n"
print(text)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text)
sys.exit(1 if problems else 0)
