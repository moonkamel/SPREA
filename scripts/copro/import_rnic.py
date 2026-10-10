"""Loads the national registry of copropriétés (RNIC, Anah, Licence Ouverte)
into the Supabase table coproprietes (supabase/migrations/010_coproprietes.sql).

Run monthly by .github/workflows/copro-import.yml:

  python scripts/copro/import_rnic.py            # latest quarterly file of data.gouv.fr
  python scripts/copro/import_rnic.py --file f.csv --dry-run

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (except with --dry-run).
Rows are upserted on the registration number; copropriétés no longer in the
file are removed at the end, when the file looked complete. Standard library only.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from typing import Dict, Iterable, Iterator, List, Optional

DATASET_API = "https://www.data.gouv.fr/api/1/datasets/registre-national-dimmatriculation-des-coproprietes/"
UA = {"User-Agent": "sprea-copro-import/1.0 (+https://sprea.app)"}
BATCH = 1000
# A complete national file has more than 600 000 copropriétés: below this,
# the stale rows are kept (truncated download, partial file)
MIN_COMPLETE = 300_000

csv.field_size_limit(10_000_000)


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def latest_csv(api_json: Dict) -> str:
    """URL of the newest data file of the dataset (not the data dictionary)."""
    files = [r for r in api_json.get("resources", [])
             if (r.get("format") or "").lower() == "csv" and "diction" not in (r.get("title") or "").lower()]
    if not files:
        raise RuntimeError("No CSV resource in the RNIC dataset")
    files.sort(key=lambda r: r.get("created_at") or r.get("last_modified") or "", reverse=True)
    return files[0]["url"]


def _text(value: Optional[str], limit: int = 200) -> Optional[str]:
    v = (value or "").strip()
    return v[:limit] or None


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(float((value or "").replace(",", ".")))
    except ValueError:
        return None


def _float(value: Optional[str]) -> Optional[float]:
    try:
        f = float((value or "").replace(",", "."))
        return f if f == f else None
    except ValueError:
        return None


def _date(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", v)
    if m:
        return f"{m[3]}-{m[2]}-{m[1]}"
    return None


def _bool(value: Optional[str]) -> Optional[bool]:
    v = (value or "").strip().lower()
    if v in ("oui", "true", "vrai", "1", "o"):
        return True
    if v in ("non", "false", "faux", "0", "n"):
        return False
    return None


def to_row(r: Dict[str, str], today: str) -> Optional[Dict]:
    immat = (r.get("numero_d_immatriculation") or "").strip().upper()
    if not immat:
        return None
    syndic_type = _text(r.get("type_de_syndic_benevole_professionnel_non_connu"), 40)
    professional = "pro" in (syndic_type or "").lower()
    lat, lon = _float(r.get("lat")), _float(r.get("long"))
    if lat is not None and not -90 <= lat <= 90 or lon is not None and not -180 <= lon <= 180:
        lat = lon = None
    return {
        "immat": immat,
        "name": _text(r.get("nom_d_usage_de_la_copropriete")),
        "address": _text(r.get("adresse_de_reference")),
        "postcode": _text(r.get("code_postal_adresse_de_reference"), 10),
        "insee": _text(r.get("commune"), 10) or _text(r.get("code_officiel_commune"), 10),
        "lat": lat, "lon": lon,
        "lots_total": _int(r.get("nombre_total_de_lots")),
        "lots_main": _int(r.get("nombre_total_de_lots_a_usage_d_habitation_de_bureaux_ou_de_comm")),
        "lots_housing": _int(r.get("nombre_de_lots_a_usage_d_habitation")),
        "lots_parking": _int(r.get("nombre_de_lots_de_stationnement")),
        "period": _text(r.get("periode_de_construction"), 40),
        "rules_date": _date(r.get("date_du_reglement_de_copropriete")),
        "syndic_type": syndic_type,
        # Volunteer syndics are private persons: their name is not kept
        "syndic_name": _text(r.get("raison_sociale_du_representant_legal")) if professional else None,
        "syndic_siret": _text(r.get("siret_du_representant_legal"), 20) if professional else None,
        "mandate_end": _date(r.get("date_de_fin_du_dernier_mandat")),
        "aided": _bool(r.get("copro_aidee")),
        "in_pdp": _bool(r.get("copro_dans_pdp")),
        "qpv": _text(r.get("nom_qp_2024"), 120),
        "registry_updated": _date(r.get("date_de_la_derniere_maj")),
        "imported_on": today,
    }


def read_rows(stream: io.TextIOBase, today: str) -> Iterator[Dict]:
    first = stream.readline()
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(first), delimiter=delimiter)
    fields = reader.fieldnames
    for raw in csv.DictReader(stream, fieldnames=fields, delimiter=delimiter):
        row = to_row(raw, today)
        if row:
            yield row


def batches(rows: Iterable[Dict], size: int = BATCH) -> Iterator[List[Dict]]:
    batch: Dict[str, Dict] = {}
    for row in rows:
        batch[row["immat"]] = row  # A batch must not upsert the same key twice
        if len(batch) >= size:
            yield list(batch.values())
            batch = {}
    if batch:
        yield list(batch.values())


class Rest:
    def __init__(self, url: str, key: str):
        self.base = f"{url.rstrip('/')}/rest/v1/coproprietes"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"

    def call(self, method: str, query: str, body: Optional[bytes] = None, prefer: str = "return=minimal"):
        for attempt in range(5):
            req = urllib.request.Request(f"{self.base}?{query}", data=body, method=method,
                                         headers={**self.headers, "Prefer": prefer})
            try:
                with urllib.request.urlopen(req, timeout=120) as res:
                    return res.read()
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt == 4:
                    raise RuntimeError(f"{method} failed: {e.code} {e.read()[:300]!r}")
            except urllib.error.URLError:
                if attempt == 4:
                    raise
            time.sleep(2 ** attempt)

    def upsert(self, rows: List[Dict]):
        self.call("POST", "on_conflict=immat", json.dumps(rows).encode(), "resolution=merge-duplicates,return=minimal")

    def delete_stale(self, today: str):
        self.call("DELETE", f"imported_on=lt.{today}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Local CSV instead of the latest data.gouv.fr file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    today = date.today().isoformat()

    rest = None
    if not args.dry_run:
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        rest = Rest(url, key)

    if args.file:
        stream = open(args.file, encoding="utf-8-sig", newline="")
    else:
        with urllib.request.urlopen(urllib.request.Request(DATASET_API, headers=UA), timeout=60) as res:
            csv_url = latest_csv(json.load(res))
        log(f"Downloading {csv_url}")
        res = urllib.request.urlopen(urllib.request.Request(csv_url, headers=UA), timeout=300)
        stream = io.TextIOWrapper(res, encoding="utf-8-sig", newline="")

    count = located = 0
    rows = read_rows(stream, today)
    for batch in batches(rows):
        if args.limit and count >= args.limit:
            break
        count += len(batch)
        located += sum(1 for r in batch if r["lat"] is not None)
        if rest:
            rest.upsert(batch)
        if count % 50_000 < BATCH:
            log(f"{count} copropriétés")
    log(f"{count} copropriétés read, {located} located")
    if rest and not args.limit:
        if count >= MIN_COMPLETE:
            rest.delete_stale(today)
            log("Stale rows removed")
        else:
            log(f"Only {count} rows: stale rows kept")


if __name__ == "__main__":
    main()
