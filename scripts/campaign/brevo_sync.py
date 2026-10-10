"""Weekly figures of each prospect's town, written on their Brevo contact, so
that the campaign emails quote real, fresh local numbers ({{ contact.SPREA_ACCROCHE }}).

For each contact of the Brevo list (attribute CODE_INSEE, or CODE_POSTAL and
VILLE): poor DPE (F, G) published in the town in the last 30 days and 12
months (ADEME), whole buildings owned by a company and those with a sale
signal (SPREA database). Read-only on SPREA; writes contact attributes only.

  BREVO_API_KEY=... BREVO_LIST_ID=3 python scripts/campaign/brevo_sync.py
  python scripts/campaign/brevo_sync.py --dry-run --insee 59350 59360   # no Brevo, prints the figures

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for the building figures
(optional: without them, DPE figures only).
"""
import argparse
import json
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

ADEME = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
GEO = "https://geo.api.gouv.fr/communes"
BREVO = "https://api.brevo.com/v3"
SITE = os.getenv("PUBLIC_APP_URL", "https://sprea.app").rstrip("/")
ATTRIBUTES = {"SPREA_ACCROCHE": "text", "SPREA_VILLE": "text", "SPREA_DPE_30J": "float", "SPREA_DPE_12M": "float",
              "SPREA_IMMEUBLES": "float", "SPREA_SIGNAUX": "float", "SPREA_LIEN": "text", "SPREA_MAJ": "date"}


def log(*a):
    print(*a, flush=True)


def http(method: str, url: str, body: Optional[Dict] = None, headers: Optional[Dict] = None) -> Tuple[int, Dict, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": "SPREA", "Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, dict(res.headers), res.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            return e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("-", " ").strip()


def insee_of(postcode: str, town: str) -> Optional[Tuple[str, str]]:
    """INSEE code and name of a town from its postcode (and name when the postcode has several)."""
    status, _, raw = http("GET", f"{GEO}?{urllib.parse.urlencode({'codePostal': postcode, 'fields': 'nom,code'})}")
    towns = json.loads(raw) if status == 200 else []
    if not towns:
        return None
    match = next((t for t in towns if plain(t["nom"]) == plain(town)), towns[0] if len(towns) == 1 else None)
    return (match["code"], match["nom"]) if match else None


def town_name(insee: str) -> str:
    status, _, raw = http("GET", f"{GEO}/{insee}?fields=nom")
    return json.loads(raw).get("nom", insee) if status == 200 else insee


def dpe_count(insee: str, since: date) -> int:
    qs = f'code_insee_ban:"{insee}" AND etiquette_dpe:(F OR G) AND date_etablissement_dpe:[{since.isoformat()} TO *]'
    status, _, raw = http("GET", f"{ADEME}?{urllib.parse.urlencode({'qs': qs, 'size': '0'})}")
    return int(json.loads(raw).get("total", 0)) if status == 200 else 0


def building_counts(insee: str) -> Tuple[int, int]:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return 0, 0
    headers = {"apikey": key, "Prefer": "count=exact", "Range": "0-0"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"

    def count(extra: str) -> int:
        status, h, _ = http("GET", f"{url.rstrip('/')}/rest/v1/monopro_buildings?select=id&insee=eq.{insee}&owner_siren=not.is.null{extra}",
                            headers=headers)
        total = (h.get("Content-Range") or h.get("content-range") or "*/0").split("/")[-1]
        return int(total) if status in (200, 206) and total.isdigit() else 0
    return count(""), count("&signal_level=in.(fort,moyen)")


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def hook(town: str, dpe30: int, dpe12: int, buildings: int, signals: int) -> str:
    """The sentence the first email opens with, from the town's figures."""
    if dpe30:
        first = (f"À {town}, {plural(dpe30, 'logement classé F ou G a', 'logements classés F ou G ont')} reçu un nouveau DPE "
                 "ces 30 derniers jours : autant de propriétaires qui préparent souvent une vente ou une location")
    elif dpe12:
        first = f"À {town}, {plural(dpe12, 'logement classé F ou G a', 'logements classés F ou G ont')} reçu un DPE ces douze derniers mois"
    else:
        first = f"À {town}, les nouveaux DPE de votre secteur arrivent chaque matin"
    if buildings:
        second = f", et {plural(buildings, 'immeuble entier appartient', 'immeubles entiers appartiennent')} à une SCI ou une société"
        if signals:
            second += f", dont {signals} avec un signal de vente au BODACC (dissolution, liquidation…)"
        return first + second + "."
    return first + "."


def figures(insee: str, town: str, today: date) -> Dict:
    dpe30 = dpe_count(insee, today - timedelta(days=30))
    dpe12 = dpe_count(insee, today - timedelta(days=365))
    buildings, signals = building_counts(insee)
    return {"SPREA_ACCROCHE": hook(town, dpe30, dpe12, buildings, signals), "SPREA_VILLE": town,
            "SPREA_DPE_30J": dpe30, "SPREA_DPE_12M": dpe12, "SPREA_IMMEUBLES": buildings, "SPREA_SIGNAUX": signals,
            "SPREA_LIEN": f"{SITE}/demo?utm_source=brevo&utm_medium=email&utm_campaign=agences_{insee[:2]}",
            "SPREA_MAJ": today.isoformat()}


class Brevo:
    def __init__(self, key: str):
        self.headers = {"api-key": key, "accept": "application/json"}

    def ensure_attributes(self):
        for name, kind in ATTRIBUTES.items():
            status, _, raw = http("POST", f"{BREVO}/contacts/attributes/normal/{name}", {"type": kind}, self.headers)
            if status not in (200, 201, 204, 400):  # 400: already there
                raise RuntimeError(f"Attribut {name} : {status} {raw[:200]!r}")

    def contacts(self, list_id: str) -> List[Dict]:
        out: List[Dict] = []
        while True:
            status, _, raw = http("GET", f"{BREVO}/contacts/lists/{list_id}/contacts?limit=500&offset={len(out)}", headers=self.headers)
            if status != 200:
                raise RuntimeError(f"Liste {list_id} : {status} {raw[:200]!r}")
            page = json.loads(raw).get("contacts") or []
            out += page
            if len(page) < 500:
                return out

    def update(self, email: str, attributes: Dict) -> bool:
        status, _, _ = http("PUT", f"{BREVO}/contacts/{urllib.parse.quote(email)}", {"attributes": attributes}, self.headers)
        return status in (200, 204)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--insee", nargs="*", help="With --dry-run: towns to compute")
    args = ap.parse_args()
    today = date.today()
    cache: Dict[str, Dict] = {}

    def for_town(insee: str, name: Optional[str] = None) -> Dict:
        if insee not in cache:
            cache[insee] = figures(insee, name or town_name(insee), today)
        return cache[insee]

    if args.dry_run:
        for insee in args.insee or ["59350"]:
            log(json.dumps(for_town(insee), ensure_ascii=False, indent=1))
        return

    brevo = Brevo(os.environ["BREVO_API_KEY"].strip())
    brevo.ensure_attributes()
    contacts = brevo.contacts(os.environ["BREVO_LIST_ID"].strip())
    log(f"{len(contacts)} contacts dans la liste")
    done = skipped = 0
    for c in contacts:
        a = c.get("attributes") or {}
        insee, name = str(a.get("CODE_INSEE") or "").strip(), None
        if not insee and a.get("CODE_POSTAL"):
            found = insee_of(str(a["CODE_POSTAL"]).strip().zfill(5), str(a.get("VILLE") or ""))
            insee, name = found if found else ("", None)
        if not insee:
            skipped += 1
            continue
        if brevo.update(c["email"], for_town(insee, name)):
            done += 1
    log(f"{done} contacts mis à jour, {skipped} sans commune reconnue, {len(cache)} communes calculées")


if __name__ == "__main__":
    main()
