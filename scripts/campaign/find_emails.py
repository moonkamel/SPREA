"""Contact email of each agency of the campaign list, read on its own website
(or, for an independent agent, on their page of the network's website).

For each SIREN: name, address and officer from the Annuaire des entreprises,
a web search for the agency's website, then the home, contact, team and
legal notice pages are read. Kept, in this order:
  1. the officer's email (their name in the address), « dirigeant »;
  2. an email shown next to « responsable des ventes / directeur commercial »,
     « responsable ventes »;
  3. the sales department's email (transaction@, ventes@), « service ventes »;
  4. the agency's general email (contact@, accueil@…), « contact général ».
Only addresses written on a page of a site that is clearly the agency's
(SIREN, or its name with its town or postcode, on the page): never guessed,
never taken from the listing portals.

  python scripts/campaign/find_emails.py --sirens 849703541 789459500 --out emails.csv
"""
import argparse
import base64
import os
import csv
import html
import re
import sys
import time
import unicodedata
import urllib.parse
from typing import Dict, Iterable, List, Optional, Tuple

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
API = "https://recherche-entreprises.api.gouv.fr/search"

# Listing portals and directories: never a source (their terms forbid it, or no emails)
SKIP = ("seloger", "leboncoin", "bienici", "logic-immo", "pap.fr", "figaro", "avendrealouer", "paruvendu",
        "meilleursagents", "lesiteimmo", "superimmo", "ouestfrance-immo", "green-acres", "luxuryestate",
        "immobilier.notaires", "pappers", "societe.com", "infogreffe", "verif.com", "manageo", "annuaire-entreprises",
        "pagesjaunes", "facebook", "instagram", "linkedin", "twitter", "x.com", "youtube", "tiktok", "google.",
        "wikipedia", "data.gouv", "kompass", "corporama", "score3", "entreprises.lefigaro", "societeinfo",
        "lagazettefrance", "bodacc", "opendatasoft", "mappy", "yelp", "tripadvisor", "trustpilot", "immodvisor",
        "opinionsystem", "bing.com", "duckduckgo", "qwant", "jedeclare", "hellowork", "indeed", "welcometothejungle",
        "francetravail", "unemplacement", "bureauxlocaux", "selogerneuf", "bellesdemeures", "proprietes-le-figaro",
        "etreproprio", "acheter-louer", "jinka", "nestoria", "trovit", "mitula", "lefigaro", "annuaire", "118")
# Agents' networks: only an email with the agent's name counts there
NETWORKS = ("iadfrance", "safti", "capifrance", "optimhome", "efficity", "bskimmobilier", "proprietes-privees",
            "megagence", "lafourmi-immo", "expertimo", "3gimmobilier", "sextantfrance", "kwfrance", "expfrance",
            "dr-house-immo", "immoreseau", "lacoteimmo", "partenaire-europeen", "bsk-immobilier", "iad")
FREE_MAIL = ("gmail.com", "hotmail.fr", "hotmail.com", "orange.fr", "wanadoo.fr", "free.fr", "outlook.fr",
             "outlook.com", "yahoo.fr", "yahoo.com", "laposte.net", "sfr.fr", "neuf.fr", "live.fr", "icloud.com",
             "bbox.fr", "aol.com", "numericable.fr")
BAD_LOCAL = ("webmaster", "dpo", "rgpd", "privacy", "noreply", "no-reply", "nepasrepondre", "recrutement", "jobs",
             "support", "abuse", "postmaster", "admin", "hostmaster", "sentry", "example", "votre", "nom", "email",
             "exemple", "test", "wordpress", "comptabilite", "compta", "facturation", "juridique", "presse", "rh")
BAD_DOMAIN = ("sentry", "wix", "example", "domain", "votredomaine", "monsite", "email.com", "ovh", "o2switch",
              "ionos", "1and1", "godaddy", "hostinger", "squarespace", "jimdo", "webflow", "cloudflare",
              "googlemail", "schema.org", "w3.org", "netlify", "vercel", "gandi", "lws", "sendinblue", "brevo",
              "mailchimp", "apimo", "hektor", "netty", "adaptimmo", "immo-facile", "ac3", "twimmopro", "orisha")
GENERIC = {"immobilier", "immobiliere", "immo", "agence", "agences", "sarl", "sas", "sasu", "eurl", "sci", "sa",
           "transaction", "transactions", "conseil", "conseils", "groupe", "the", "les", "des", "and", "et", "de",
           "du", "la", "le", "l", "d", "en", "france", "nord", "lille", "services", "service", "gestion", "cabinet",
           "property", "real", "estate", "home", "homes", "maison", "maisons", "habitat", "patrimoine", "invest",
           "consulting", "partners", "partenaires", "societe", "company", "holding", "ei", "mandataire"}
PAGE_HINT = re.compile(r"contact|mention|legal|l[ée]gal|equipe|[ée]quipe|team|qui-sommes|a-propos|about|agence|"
                       r"nous|conseiller|collaborateur|notre", re.I)
SALES_ROLE = re.compile(r"responsable\s+(des\s+)?(ventes|transactions?|commercial)|directeur\s+commercial|"
                        r"directrice\s+commerciale|n[ée]gociat\w+\s+(principal|responsable)|"
                        r"responsable\s+d['e]\s*agence|directeur\s+d['e]\s*agence|directrice\s+d['e]\s*agence", re.I)
EMAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
DEBUG = bool(os.getenv("DEBUG"))
STATS = {"brave_api": 0, "ddg": 0, "bing": 0, "brave": 0, "search_fail": 0}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9@.]+", " ", text).strip()


def get(url: str, timeout: float = 15, **kw) -> Optional[requests.Response]:
    try:
        res = session.get(url, timeout=timeout, allow_redirects=True, **kw)
        if res.status_code == 200 and "text/html" in res.headers.get("content-type", "text/html"):
            return res
    except requests.RequestException:
        pass
    return None


def company(siren: str) -> Optional[Dict]:
    for attempt in range(4):
        try:
            res = session.get(API, params={"q": siren}, timeout=20)
            if res.status_code == 200:
                for r in res.json().get("results") or []:
                    if r.get("siren") == siren:
                        siege = r.get("siege") or {}
                        names = [r.get("nom_raison_sociale") or "", r.get("nom_complet") or "",
                                 *(siege.get("liste_enseignes") or []), *(r.get("liste_enseignes") or [])]
                        officers = [(d.get("prenoms") or "", d.get("nom") or "") for d in r.get("dirigeants") or []
                                    if d.get("type_dirigeant") == "personne physique" and d.get("nom")]
                        return {"siren": siren, "names": [n for n in dict.fromkeys(names) if n],
                                "officers": officers, "postcode": siege.get("code_postal") or "",
                                "town": siege.get("libelle_commune") or "", "street": siege.get("adresse") or ""}
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 ** attempt)
    return None


# --- Web search ---

def ddg(query: str) -> List[str]:
    try:
        res = session.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "fr-fr"}, timeout=15)
    except requests.RequestException:
        return []
    out = []
    for href in re.findall(r'class="result__a"[^>]*href="([^"]+)"', res.text):
        href = html.unescape(href)
        if "uddg=" in href:
            href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [""])[0])
        out.append(href)
    return out


def unbing(href: str) -> str:
    """Bing wraps the result links: /ck/a?...&u=a1<base64 of the URL>."""
    href = html.unescape(href)
    if "bing.com/ck/" not in href:
        return href
    u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
    if u.startswith("a1"):
        try:
            return base64.urlsafe_b64decode(u[2:] + "=" * (-len(u[2:]) % 4)).decode()
        except (ValueError, UnicodeDecodeError):
            pass
    return ""


def bing(query: str) -> List[str]:
    res = get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "fr", "cc": "FR"}))
    if not res:
        return []
    out = []
    for block in res.text.split('<li class="b_algo"')[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"', block)
        if m:
            out.append(unbing(m.group(1)))
    return [u for u in out if u]


def brave(query: str) -> List[str]:
    res = get("https://search.brave.com/search?" + urllib.parse.urlencode({"q": query, "source": "web"}))
    if not res:
        return []
    return [h for h in re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*(?:heading-serpresult|result-header|l1)', res.text)]


def brave_api(query: str, attempt: int = 0) -> List[str]:
    """Brave Search API (BRAVE_API_KEY; free plan: 2 000 searches a month).
    The search engines' own pages answer bots from data centres with
    unrelated results, so this is the reliable path."""
    try:
        res = session.get("https://api.search.brave.com/res/v1/web/search", timeout=15,
                          params={"q": query, "country": "fr", "search_lang": "fr", "count": 10},
                          headers={"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"})
        if res.status_code == 429 and attempt < 3:
            # 1 request a second on the free plan; a monthly quota reached stays 429
            time.sleep(2 * (attempt + 1))
            return brave_api(query, attempt + 1)
        if res.status_code != 200:
            print(f"Brave Search : erreur {res.status_code}", file=sys.stderr, flush=True)
        return [r["url"] for r in (res.json().get("web") or {}).get("results") or []] if res.status_code == 200 else []
    except (requests.RequestException, ValueError, KeyError):
        return []


ENGINES = ([("brave_api", brave_api)] if os.getenv("BRAVE_API_KEY") else
           [("ddg", ddg), ("bing", bing), ("brave", brave)])


def search(query: str) -> List[str]:
    if ENGINES[0][0] == "brave_api":
        time.sleep(1.1)  # Free plan: 1 request a second
    for name, engine in ENGINES:
        urls = [u for u in engine(query) if u.startswith("http")]
        if urls:
            STATS[name] += 1
            return urls
        time.sleep(1)
    STATS["search_fail"] += 1
    return []


def host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def skipped(url: str) -> bool:
    h = host(url)
    return not h or any(s in h for s in SKIP)


def is_network(url: str) -> bool:
    return any(n in host(url) for n in NETWORKS)


# --- Pages and emails ---

def cf_decode(hexstr: str) -> str:
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def emails_in(page: str) -> List[Tuple[str, str]]:
    """(email, surrounding text) found in a page."""
    page = page.replace("&#64;", "@").replace("&#x40;", "@")
    for enc in re.findall(r'data-cfemail="([0-9a-f]+)"', page):
        page += " " + cf_decode(enc)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    found = []
    for source in (urllib.parse.unquote(page), text):
        for m in EMAIL.finditer(source):
            email = m.group(0).strip(".").lower()
            context = text[max(0, text.find(email) - 250): text.find(email) + 100] if email in text else ""
            found.append((email, context))
    seen, out = set(), []
    for e, c in found:
        if e not in seen or c:
            if e in seen:
                out = [(x, cx) for x, cx in out if x != e]
            seen.add(e)
            out.append((e, c))
    return out


def plausible(email: str) -> bool:
    local, _, domain = email.partition("@")
    if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|ico|pdf)$", email) or len(local) < 2:
        return False
    if any(b in domain for b in BAD_DOMAIN) or any(local.startswith(b) for b in BAD_LOCAL):
        return False
    return "." in domain


def matches(agency: Dict, text: str) -> bool:
    """The page is about this agency: its SIREN, or a distinctive word of its
    name with its town or postcode."""
    t = " " + re.sub(r"[.@]", " ", norm(text)) + " "
    if agency["siren"] in re.sub(r"\s", "", text):
        return True
    where = agency["postcode"] in t or f" {norm(agency['town'])} " in t
    for name in agency["names"]:
        words = [w for w in norm(re.sub(r"\(.*?\)", " ", name)).split() if w not in GENERIC and len(w) > 2]
        if words and all(f" {w} " in t for w in words[:2]) and where:
            return True
    return False


def officer_tokens(agency: Dict) -> List[Tuple[str, str]]:
    return [(norm(p.split(" ")[0]), norm(n).replace(" ", "")) for p, n in agency["officers"]]


def mentions_officer(agency: Dict, text: str) -> bool:
    t = norm(text)
    return any(last and first and last in t.replace(" ", "") and first in t for first, last in officer_tokens(agency))


def rank(agency: Dict, email: str, context: str, site: str, network: bool) -> Optional[Tuple[int, str]]:
    local, _, domain = email.partition("@")
    lnorm = local.replace(".", "").replace("-", "").replace("_", "")
    own = domain.removeprefix("www.") == site or site.endswith("." + domain) or domain in FREE_MAIL
    named = any(last and len(last) > 2 and last in lnorm for _, last in officer_tokens(agency))
    if network:
        # A network page: only the agent's own address
        return (0, "dirigeant") if named and (domain in FREE_MAIL or any(n in domain for n in NETWORKS)) else None
    if not own:
        return None
    if named:
        return (0, "dirigeant")
    if context and SALES_ROLE.search(context) and re.search(r"[a-z]{2,}[.\-_][a-z]{2,}", local):
        return (1, "responsable ventes")
    if re.search(r"vente|transac|commercial", local):
        return (2, "service ventes")
    if re.search(r"^(contact|accueil|info|infos|agence|bonjour|hello|immo|immobilier|secretariat|direction)", local):
        return (3, "contact général")
    if re.search(r"location|gestion|syndic|copro", local):
        return (5, "contact général")
    return (4, "contact général")


def site_links(base: str, page: str) -> List[str]:
    links = []
    for href, label in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        url = urllib.parse.urljoin(base, html.unescape(href))
        if host(url) == host(base) and (PAGE_HINT.search(href) or PAGE_HINT.search(re.sub(r"<[^>]+>", "", label))):
            links.append(url.split("?")[0])
    return list(dict.fromkeys(links))[:6]


def scan_site(agency: Dict, url: str) -> Optional[Dict]:
    network = is_network(url)
    first = get(url)
    if not first:
        return None
    pages = [(first.url, first.text)]
    if network:
        if not mentions_officer(agency, first.text):
            return None
    else:
        root = f"{urllib.parse.urlparse(first.url).scheme}://{urllib.parse.urlparse(first.url).netloc}/"
        if root.rstrip("/") != first.url.rstrip("/"):
            home = get(root)
            if home:
                pages.append((home.url, home.text))
        candidates = []
        for u, p in list(pages):
            candidates += site_links(u, p)
        for guess in ("contact", "mentions-legales", "nous-contacter", "equipe", "agence"):
            candidates.append(urllib.parse.urljoin(root, guess))
        for u in list(dict.fromkeys(candidates))[:8]:
            if u not in {x for x, _ in pages}:
                r = get(u, timeout=10)
                if r:
                    pages.append((r.url, r.text))
        if not any(matches(agency, p) for _, p in pages):
            return None
    site = host(first.url)
    best = None
    for u, p in pages:
        for email, context in emails_in(p):
            if not plausible(email):
                continue
            r = rank(agency, email, context, site, network)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], {"email": email, "email_type": r[1], "source_url": u})
    return best[1] if best else None


def queries(agency: Dict) -> Iterable[str]:
    name = re.sub(r"\(.*?\)", "", agency["names"][0]).strip()
    yield f'"{name}" {agency["town"]} immobilier'
    yield f'{name} agence immobilière {agency["postcode"]} contact'
    for p, n in agency["officers"][:1]:
        yield f'"{p.split(" ")[0]} {n}" immobilier {agency["town"]}'
    for other in agency["names"][1:2]:
        yield f'"{re.sub(r"[(].*?[)]", "", other).strip()}" {agency["postcode"]}'


def find(agency: Dict) -> Dict:
    tried = set()
    for q in queries(agency):
        for url in search(q)[:6]:
            if skipped(url):
                continue
            key = host(url) if not is_network(url) else url
            if key in tried:
                continue
            tried.add(key)
            hit = scan_site(agency, url)
            if DEBUG:
                print(f"  {url} -> {hit}", file=sys.stderr, flush=True)
            if hit:
                return hit
        time.sleep(1.5)
    return {"email": "", "email_type": "non trouvé", "source_url": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sirens", nargs="+", required=True)
    ap.add_argument("--out", default="emails.csv")
    args = ap.parse_args()
    sirens = [s for chunk in args.sirens for s in re.split(r"[\s,;]+", chunk) if s]
    rows = []
    for i, siren in enumerate(sirens, 1):
        agency = company(siren)
        row = {"siren": siren, **(find(agency) if agency else {"email": "", "email_type": "non trouvé", "source_url": ""})}
        rows.append(row)
        print(f"RESULT\t{i}\t{siren}\t{row['email']}\t{row['email_type']}\t{row['source_url']}", flush=True)
        if i % 20 == 0:
            print(f"{i}/{len(sirens)} — moteurs : {STATS}", file=sys.stderr, flush=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["siren", "email", "email_type", "source_url"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["email_type"]] = counts.get(r["email_type"], 0) + 1
    print(f"Bilan : {counts} — moteurs : {STATS}")


if __name__ == "__main__":
    main()
