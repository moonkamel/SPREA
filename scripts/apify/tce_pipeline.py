"""Fichier de prospection B2B : entreprises du bâtiment « tout corps d'état »
(TCE) et entreprises générales des Hauts-de-France (02, 59, 60, 62, 80).

Pipeline (API HTTP Apify, bibliothèque standard uniquement) :

  1a. Registre RGE de l'ADEME     scrapersdelight/rge-installers-fr-scraper
      (l'Actor fit_melon/french-rge-certified-contractors-finder-ademe
      n'existe pas sur Apify : celui-ci lit le même registre officiel,
      une ligne par entreprise avec toutes ses qualifications)
      -> filtre TCE : une qualification « Rénovation globale », ou au moins
         3 corps de métier distincts parmi les qualifications RGE.
  1b. Entreprises générales        euroscrape/france-companies
      NAF 41.20A, 41.20B, 43.99C, 43.99D + label RGE, avec effectif et CA.
      Le même Actor complète l'effectif et le CA des TCE trouvées en 1a
      (mode « sirens »).
  2.  Dirigeant                     corent1robert/rge-siren-enrich
      (mode « sirets », rowDepth « directors »)
      + label Éco Artisan           corent1robert/capeb-scraper
      (activité « entreprise générale », départements des Hauts-de-France)
  3.  Scores : multi-compétence, capacité chantier, proximité des passoires.
      La densité de DPE F/G vient de l'API publique de l'ADEME (gratuite),
      par code postal : l'Actor dpe-fg-proprietaires-siren lit au plus
      quelques centaines de DPE par run et renvoie des propriétaires, pas une
      densité.
  4.  CSV final trié par score.

Budget : chaque run reçoit un plafond (maxTotalChargeUsd) calculé sur les prix
du palier Apify « Free », les plus élevés ; le total ne dépasse jamais
BUDGET_USD. Les JSON intermédiaires sont gardés dans --out.

  export APIFY_TOKEN=...            # jamais dans le code
  python scripts/apify/tce_pipeline.py --out tce_hdf          # exécution
  python scripts/apify/tce_pipeline.py --out tce_hdf --dry-run # plan et coût, sans run
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

API = "https://api.apify.com/v2"
ADEME_DPE = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
DEPARTMENTS = ["02", "59", "60", "62", "80"]
BUDGET_USD = 15.0

# Prix par ligne au palier « Free » (le plus cher), lus sur les fiches des Actors
# le 3/11/2026 : ils servent à plafonner chaque run, pas à facturer.
PRICES = {
    "rge": 0.0009,          # scrapersdelight : company-scraped
    "companies": 0.004,     # euroscrape : company (2,80 $/1000 au palier Gold)
    "directors": 0.00499,   # rge-siren-enrich : rge-artisan-directors
    "capeb": 0.005,         # capeb-scraper : artisan-with-email (le plus cher)
}
START_FEE = 0.003           # démarrage d'un run (marge)

# Plafonds de lignes par étape : ~60 000 entreprises RGE en France, dont environ
# 8 % dans les Hauts-de-France ; le reste est calibré pour tenir sous 15 $.
CAPS = {"rge": 6000, "companies_naf": 500, "companies_sirens": 700, "directors": 600, "capeb": 150}

# Corps de métier : chaque domaine RGE du registre ADEME rattaché à un lot.
# Les études et l'architecture ne sont pas des travaux : ignorées.
TRADES = {
    "Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds": "Isolation",
    "Isolation des combles perdus": "Isolation",
    "Isolation des murs par l'extérieur": "Isolation",
    "Isolation des toitures terrasses ou des toitures par l'extérieur": "Isolation",
    "Isolation des planchers bas": "Isolation",
    "Fenêtres, volets, portes donnant sur l'extérieur": "Menuiserie",
    "Fenêtres de toit": "Menuiserie",
    "Pompe à chaleur : chauffage": "Chauffage",
    "Chaudière condensation ou micro-cogénération gaz ou fioul": "Chauffage",
    "Chaudière bois": "Chauffage",
    "Poêle ou insert bois": "Chauffage",
    "Radiateurs électriques, dont régulation.": "Électricité / chauffage électrique",
    "Chauffe-Eau Thermodynamique": "Eau chaude sanitaire",
    "Chauffage et/ou eau chaude solaire": "Eau chaude sanitaire",
    "Ventilation mécanique": "Ventilation",
    "Panneaux solaires photovoltaïques": "Photovoltaïque",
    "Forage géothermique": "Géothermie",
    "Projet complet de rénovation": "Rénovation globale",
}
GLOBAL = "Rénovation globale"
MIN_TRADES_TCE = 3
GENERAL_NAF = {"41.20A", "41.20B"}  # construction de bâtiments : entreprise générale


# --- Apify : appels HTTP ---------------------------------------------------

def http(method: str, url: str, token: Optional[str] = None, body: Any = None, timeout: int = 120) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                raw = res.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} : HTTP {e.code} {e.read()[:300]!r}")
    raise RuntimeError(f"{method} {url} : trop d'échecs")


class Budget:
    """Dépense cumulée, estimée au prix Free à partir des lignes facturées."""

    def __init__(self, limit: float):
        self.limit, self.spent = limit, 0.0

    def cap_for(self, rows: int, price: float) -> float:
        wanted = rows * price + START_FEE
        left = self.limit - self.spent
        if left <= START_FEE:
            raise RuntimeError(f"Budget épuisé ({self.spent:.2f} $ sur {self.limit:.2f} $)")
        return round(min(wanted, left), 2)


def run_actor(actor: str, run_input: Dict, token: str, price: float, rows: int, out_dir: str, name: str,
              budget: Budget) -> List[Dict]:
    """Lance un Actor, attend sa fin, rapatrie son dataset et le sauvegarde en JSON."""
    path = os.path.join(out_dir, f"{name}.json")
    if os.path.exists(path):  # reprise : une étape déjà faite n'est pas repayée
        print(f"[{name}] déjà présent, relu depuis {path}")
        return json.load(open(path, encoding="utf-8"))
    max_charge = budget.cap_for(rows, price)
    q = urllib.parse.urlencode({"maxTotalChargeUsd": max_charge})
    run = http("POST", f"{API}/acts/{actor.replace('/', '~')}/runs?{q}", token, run_input)["data"]
    print(f"[{name}] run {run['id']} lancé (plafond {max_charge} $)")
    while run["status"] in ("READY", "RUNNING"):
        run = http("GET", f"{API}/actor-runs/{run['id']}?waitForFinish=60", token)["data"]
    if run["status"] != "SUCCEEDED":
        raise RuntimeError(f"[{name}] run {run['id']} terminé en {run['status']}")
    items, offset = [], 0
    while True:
        page = http("GET", f"{API}/datasets/{run['defaultDatasetId']}/items?"
                    + urllib.parse.urlencode({"format": "json", "clean": "true", "offset": offset, "limit": 1000}), token)
        items += page
        if len(page) < 1000:
            break
        offset += 1000
    # Dépense estimée : lignes livrées au prix Free de l'étape, jamais plus que le plafond du run
    budget.spent += min(max_charge, len(items) * price + START_FEE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print(f"[{name}] {len(items)} lignes, dépense cumulée estimée {budget.spent:.2f} $")
    return items


# --- Étape 1 : collecte et filtre TCE -------------------------------------

def trades_of(company: Dict) -> List[str]:
    """Corps de métier distincts couverts par les qualifications RGE d'une entreprise."""
    found = set()
    for d in company.get("workDomains") or []:
        if d in TRADES:
            found.add(TRADES[d])
    for q in company.get("qualifications") or []:
        if isinstance(q, dict):
            if q.get("workDomain") in TRADES or q.get("domain") in TRADES:
                found.add(TRADES.get(q.get("workDomain")) or TRADES[q.get("domain")])
            if GLOBAL in (q.get("workCategory") or q.get("metaDomain") or ""):
                found.add(GLOBAL)
    if any(GLOBAL in c for c in company.get("workCategories") or []):
        found.add(GLOBAL)
    return sorted(found)


def is_tce(company: Dict) -> bool:
    trades = trades_of(company)
    return GLOBAL in trades or len([t for t in trades if t != GLOBAL]) >= MIN_TRADES_TCE


def siren_of(row: Dict) -> Optional[str]:
    s = str(row.get("siren") or row.get("siret") or "").replace(" ", "")
    return s[:9] if len(s) >= 9 and s[:9].isdigit() else None


# --- Étape 3 : scores -----------------------------------------------------

def score_multi(trades: List[str]) -> int:
    """+1 par corps de métier distinct (la rénovation globale compte pour un), plafonné à 5."""
    return min(5, len(trades))


def employees_at_least_10(company: Dict) -> bool:
    """Tranche d'effectif INSEE : 11 = 10 à 19 salariés, et au-delà."""
    e = company.get("employees")
    code = e.get("code") if isinstance(e, dict) else e
    label = e.get("label", "") if isinstance(e, dict) else ""
    if code and str(code).isdigit():
        return int(code) >= 11
    return any(x in label for x in ("10 à", "20 à", "50 à", "100 à", "200 à", "250 à", "500 à"))


def revenue_of(company: Dict) -> Optional[float]:
    fin = company.get("latestFinances") or {}
    try:
        return float(fin.get("revenue")) if fin.get("revenue") is not None else None
    except (TypeError, ValueError):
        return None


def score_capacity(company: Optional[Dict]) -> int:
    """Effectif d'au moins 10 salariés : +2 ; CA supérieur à 1 M€ : +3."""
    if not company:
        return 0
    rev = revenue_of(company)
    return (2 if employees_at_least_10(company) else 0) + (3 if rev and rev > 1_000_000 else 0)


def fg_density(postcode: str, cache: Dict[str, int]) -> int:
    """Nombre de DPE F et G de l'ADEME dans un code postal (API publique, gratuite)."""
    if not postcode:
        return 0
    if postcode not in cache:
        q = urllib.parse.urlencode({"qs": f'code_postal_ban:"{postcode}" AND etiquette_dpe:(F OR G)', "size": 0})
        try:
            cache[postcode] = int(http("GET", f"{ADEME_DPE}?{q}", timeout=30).get("total") or 0)
        except RuntimeError as e:
            print(f"ADEME indisponible pour {postcode} : {e}", file=sys.stderr)
            cache[postcode] = 0
    return cache[postcode]


def score_proximity(count: int) -> int:
    """Grappe de passoires dans le code postal de l'entreprise : +3 à +5 selon la densité."""
    if count >= 500:
        return 5
    if count >= 200:
        return 4
    if count >= 50:
        return 3
    return 0


# --- Assemblage ------------------------------------------------------------

COLUMNS = ["Entreprise_Nom", "Entreprise_Type", "Dirigeant_Nom", "Email", "Téléphone", "Adresse", "CodePostal", "SIRET",
           "Codes_NAF", "Qualifications_RGE", "Nb_Corps_Metier", "Effectif", "CA", "Score_Multi_Competence",
           "Score_Capacite_Chantier", "Score_Proximite", "Score_Final", "Eco_Artisan_CAPEB"]


def plain(text: Any) -> str:
    """Minuscules sans accents ni tirets, pour comparer des libellés (« Éco-Artisan »)."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(text)).encode("ascii", "ignore").decode().lower()
    return t.replace("-", " ")


def first(*values):
    return next((v for v in values if v not in (None, "", [])), "")


def build_rows(rge_tce: Dict[str, Dict], companies: Dict[str, Dict], directors: Dict[str, Dict],
               capeb: Dict[str, Dict], density: Dict[str, int]) -> List[Dict]:
    rows = []
    for siren in sorted(set(rge_tce) | set(companies)):
        r, c, d, k = rge_tce.get(siren, {}), companies.get(siren, {}), directors.get(siren, {}), capeb.get(siren, {})
        hq = c.get("headquarters") or {}
        trades = trades_of(r) if r else []
        naf = first(c.get("nafCode"), d.get("nafCode"))
        postcode = str(first(r.get("postalCode"), hq.get("postalCode"), d.get("postalCode"), k.get("postalCode")))
        multi, capa = score_multi(trades), score_capacity(c)
        prox = score_proximity(density.get(postcode, 0))
        emp = c.get("employees")
        quals = sorted({q.get("certificate") or q.get("name") or q.get("workDomain") or ""
                        for q in r.get("qualifications") or [] if isinstance(q, dict)} - {""}) or r.get("certificates") or []
        rows.append({
            "Entreprise_Nom": first(r.get("companyName"), c.get("name"), c.get("legalName"), d.get("companyName")),
            "Entreprise_Type": "Entreprise Générale" if naf in GENERAL_NAF else "TCE",
            "Dirigeant_Nom": first(d.get("directorName"),
                                   " ".join(x for x in (d.get("directorFirstName"), d.get("directorLastName")) if x),
                                   k.get("contactName")),
            "Email": first(d.get("email"), r.get("email"), c.get("primaryEmail"), k.get("email")),
            "Téléphone": first(d.get("phone"), r.get("phone"), (c.get("phones") or [None])[0], k.get("phone")),
            "Adresse": first(r.get("fullAddress"), r.get("streetAddress"), d.get("address"), k.get("address")),
            "CodePostal": postcode,
            "SIRET": first(r.get("siret"), d.get("siret"), k.get("siret"), siren),
            "Codes_NAF": naf,
            "Qualifications_RGE": " | ".join(quals) if isinstance(quals, list) else str(quals),
            "Nb_Corps_Metier": len([t for t in trades if t != GLOBAL]),
            "Effectif": emp.get("label", "") if isinstance(emp, dict) else (emp or ""),
            "CA": revenue_of(c) or "",
            "Score_Multi_Competence": multi,
            "Score_Capacite_Chantier": capa,
            "Score_Proximite": prox,
            "Score_Final": multi + capa + prox,
            "Eco_Artisan_CAPEB": "oui" if any("eco artisan" in plain(x) for x in k.get("labels") or []) else "",
        })
    rows.sort(key=lambda x: (-x["Score_Final"], x["Entreprise_Nom"]))
    return rows


def by_siren(items: Iterable[Dict]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for it in items:
        s = siren_of(it)
        if s and s not in out:
            out[s] = it
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tce_hdf", help="dossier des JSON intermédiaires et du CSV")
    ap.add_argument("--dry-run", action="store_true", help="affiche le plan et le coût maximal, sans lancer de run")
    ap.add_argument("--budget", type=float, default=BUDGET_USD)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    plan = [("rge", CAPS["rge"], PRICES["rge"]), ("companies_naf", CAPS["companies_naf"], PRICES["companies"]),
            ("companies_sirens", CAPS["companies_sirens"], PRICES["companies"]),
            ("directors", CAPS["directors"], PRICES["directors"]), ("capeb", CAPS["capeb"], PRICES["capeb"])]
    worst = sum(n * p + START_FEE for _, n, p in plan)
    print("Plan (plafond de lignes x prix Free) :")
    for name, n, p in plan:
        print(f"  {name:17s} {n:5d} lignes x {p} $ = {n * p:.2f} $")
    print(f"  coût maximal {worst:.2f} $ pour un budget de {args.budget:.2f} $")
    if args.dry_run:
        return
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        sys.exit("APIFY_TOKEN manquant (variable d'environnement)")
    budget = Budget(args.budget)

    # 1a. Registre RGE des Hauts-de-France, une ligne par entreprise
    rge = run_actor("scrapersdelight/rge-installers-fr-scraper", {
        "postalPrefixes": DEPARTMENTS, "oneRowPerCompany": True, "onlyCurrentQualifications": True,
        "maxCompanies": CAPS["rge"],
    }, token, PRICES["rge"], CAPS["rge"], args.out, "1a_rge_registre", budget)
    rge_tce = {s: c for s, c in by_siren(rge).items() if is_tce(c)}
    json.dump(list(rge_tce.values()), open(os.path.join(args.out, "1a_rge_tce.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"1a : {len(rge)} entreprises RGE, dont {len(rge_tce)} TCE (rénovation globale ou {MIN_TRADES_TCE}+ corps)")

    # 1b. Entreprises générales RGE par code NAF, avec effectif et CA
    naf = run_actor("euroscrape/france-companies", {
        "nafCodes": ["41.20A", "41.20B", "43.99C", "43.99D"], "departments": DEPARTMENTS, "labels": ["rge"],
        "onlyActive": True, "maxItems": CAPS["companies_naf"], "findContacts": False,
    }, token, PRICES["companies"], CAPS["companies_naf"], args.out, "1b_entreprises_naf", budget)
    companies = by_siren(naf)
    # Effectif et CA des TCE du registre absentes de la recherche NAF
    missing = [s for s in rge_tce if s not in companies][:CAPS["companies_sirens"]]
    if missing:
        extra = run_actor("euroscrape/france-companies", {
            "sirens": missing, "onlyActive": True, "maxItems": len(missing), "findContacts": False,
        }, token, PRICES["companies"], len(missing), args.out, "1b_entreprises_tce_sirens", budget)
        companies.update({s: c for s, c in by_siren(extra).items() if s not in companies})

    # 2. Dirigeant des entreprises retenues (TCE du registre d'abord, puis entreprises générales)
    targets = list(rge_tce) + [s for s in companies if s not in rge_tce]
    sirets = [first(rge_tce.get(s, {}).get("siret"), s) for s in targets][:CAPS["directors"]]
    directors = by_siren(run_actor("corent1robert/rge-siren-enrich", {
        "mode": "sirets", "sirets": sirets, "rowDepth": "directors", "howMany": "all",
    }, token, PRICES["directors"], len(sirets), args.out, "2_dirigeants", budget))
    capeb = by_siren(run_actor("corent1robert/capeb-scraper", {
        "filterActivities": ["entreprise générale"], "departments": DEPARTMENTS, "collectEmails": True,
        "maxItems": CAPS["capeb"],
    }, token, PRICES["capeb"], CAPS["capeb"], args.out, "2_capeb_entreprise_generale", budget))

    # 3. Densité de passoires par code postal (API ADEME gratuite, gardée en cache)
    cache_path = os.path.join(args.out, "3_densite_fg.json")
    density: Dict[str, int] = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    postcodes = {str(first(c.get("postalCode"), (c.get("headquarters") or {}).get("postalCode")))
                 for c in list(rge_tce.values()) + list(companies.values())}
    for pc in sorted(p for p in postcodes if p):
        fg_density(pc, density)
    json.dump(density, open(cache_path, "w"), indent=1)

    # 4. CSV final
    rows = build_rows(rge_tce, companies, directors, capeb, density)
    csv_path = os.path.join(args.out, "prospection_tce_hauts_de_france.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} entreprises dans {csv_path} ; dépense estimée {budget.spent:.2f} $")


if __name__ == "__main__":
    main()
