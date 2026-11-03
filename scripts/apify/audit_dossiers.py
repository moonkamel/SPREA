"""Audit of the worksite dossiers sent to the TCE firms: each building of the
campaign is rebuilt as the signed link does (api/monopro.py, audience "tce"),
with the live data (Supabase, ADEME, DVF, Annuaire des entreprises), and checked
against rules a firm would see break. Read-only: nothing is sent or written to
the site.

  python scripts/apify/audit_dossiers.py --dir out --limit 300
Output: out/audit_dossiers.csv (one line per building) and a summary.
"""
import argparse
import asyncio
import csv
import io
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Optional

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "campaign"))
from api import monopro_pdf  # noqa: E402
from api.monopro import fetch_company  # noqa: E402
from api.monopro_report import FILLER  # noqa: E402
import send_tce as st  # noqa: E402

COLS = ["immeuble", "statut", "adresse", "logements", "dpe_connus", "estimes", "fg", "entete", "budget_bas", "budget_haut",
        "eur_m2_bas", "part_poste_generique", "valeur_affichee", "dirigeant", "pages", "mail_majoritaire",
        "dossier_majoritaire", "note", "alertes"]


def supabase(path: str, params: Dict) -> List[Dict]:
    url, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    res = httpx.get(f"{url}/rest/v1/{path}", params=params, headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    timeout=60)
    res.raise_for_status()
    return res.json()


def checks(d: Dict, text: str, pages: int, counts: Optional[Dict]) -> List[str]:
    """What a building firm reading the dossier would see as wrong or weak."""
    out = []
    u, w, b = d["units"], d.get("works_tce"), d["building"]
    fg = u["total"]["F"] + u["total"]["G"]
    if not fg:
        out.append("aucun logement F ou G")
    if not u["n_known"]:
        out.append("aucun DPE de logement publié")
    # More dwellings estimated than known is stated in the dossier (« dont 3 estimés »): a note, not an alert
    if not d.get("building_dpe") and "· classé" in text:
        out.append("classe d'immeuble sans DPE collectif")
    if "d'après le DPE de l'immeuble" in text:
        out.append("estimation attribuée à un DPE collectif absent")
    if "audit énergétique (classe" in text and not d.get("building_dpe"):
        out.append("audit affirmé sans DPE collectif")
    if w:
        per_m2 = w["low"] / d["shab"] if d["shab"] else 0
        if not 80 <= per_m2 <= 800:
            out.append(f"budget hors normes ({per_m2:.0f} €/m² au bas)")
        filler = sum(it["low"] for it in w["items"] if it["name"] == FILLER)
        if w["low"] and filler / w["low"] > 0.5:
            out.append("poste générique > 50 % du budget")
    else:
        out.append("pas de budget travaux")
    if pages > 2:
        out.append(f"{pages} pages")
    if not re.search(r"Dirigeant : ", text):
        out.append("pas de dirigeant")
    if "(BRIQUETEUR)" in text or re.search(r"Dirigeant : [^\n]*\([^)]*\) \(", text):
        out.append("nom du dirigeant à nettoyer")
    # The email is written from these same facts (send_tce.dossier_facts): it says what the dossier shows
    f = st.dossier_facts(d)
    if f["has_value"] != ("Décote liée au DPE" in text or "après rénovation (classe C)" in text):
        out.append("valeur promise par le mail absente du PDF (ou l'inverse)")
    if "remettent les logements F" in text:
        out.append("logements F « remis » sur le marché")
    return out


async def audit_one(client: httpx.AsyncClient, b: Dict, owner: Optional[Dict], counts: Optional[Dict]) -> Dict:
    d = await st.building_dossier(client, b, owner)
    f = st.dossier_facts(d)
    if not f["ok"]:
        return {"immeuble": b["id"], "statut": "écarté de la campagne", "adresse": b.get("address"),
                "logements": b["nb_log"], "dpe_connus": d["units"]["n_known"], "fg": f["known_fg"], "alertes": ""}
    d["company"] = await fetch_company(b["owner_siren"]) if b.get("owner_siren") else None
    pdf = monopro_pdf.generate(d, "tce")
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        text = "\n".join(pg.extract_text() or "" for pg in p.pages)
        pages = len(p.pages)
    u, w = d["units"], d.get("works_tce") or {}
    filler = sum(it["low"] for it in w.get("items", []) if it["name"] == FILLER)
    head = re.search(r"habitables[^\n]*", text)
    alerts = checks(d, text, pages, counts)
    known = u["n_known"] or 0
    return {
        "immeuble": b["id"], "statut": "envoyable", "adresse": b.get("address"), "logements": b["nb_log"], "dpe_connus": known,
        "estimes": sum(u["estimated"].values()), "fg": u["total"]["F"] + u["total"]["G"],
        "entete": head.group(0) if head else "", "budget_bas": w.get("low"), "budget_haut": w.get("high"),
        "eur_m2_bas": round(w["low"] / d["shab"]) if w.get("low") and d["shab"] else "",
        "part_poste_generique": f"{100 * filler / w['low']:.0f} %" if w.get("low") else "",
        "valeur_affichee": "oui" if "Décote liée au DPE" in text or "après rénovation (classe C)" in text else "non",
        "dirigeant": (re.search(r"Dirigeant : ([^\n]*)", text) or [None, ""])[1],
        "pages": pages, "mail_majoritaire": f["major"],
        "dossier_majoritaire": bool(known) and (u["known"]["F"] + u["known"]["G"]) * 2 >= known,
        "note": "plus de logements estimés que connus" if sum(u["estimated"].values()) > known else "",
        "alertes": " ; ".join(alerts),
    }


async def main_async(args):
    rows = st.read(os.path.join(args.dir, "prospection_TCE_chantiers.csv"))
    firms = {r["Entreprise_Nom"]: r for r in st.read(os.path.join(args.dir, "prospection_tce_hauts_de_france.csv"))}
    import json
    facts = json.load(open(os.path.join(args.dir, "4_immeubles_fg.json"), encoding="utf-8"))
    by_link = {f["link"]: f["id"] for f in facts if f.get("link")}
    # The campaign as sent: the first N firms that carry out works, and those already written to
    sent = {t["email"].strip().lower() for t in st.read(os.path.join(args.dir, st.TRACK))}
    campaign = st.eligible(rows, set(), firms)[:args.limit]
    written = [r for r in rows if r["Email"].strip().lower() in sent]
    ids = sorted({by_link[r["Lien_Dossier"]] for r in campaign + written if r["Lien_Dossier"] in by_link})
    print(f"{len(ids)} immeubles à contrôler", flush=True)
    buildings, owners = [], {}
    for i in range(0, len(ids), 100):
        buildings += supabase("monopro_buildings", {"select": "*", "id": f"in.({','.join(ids[i:i + 100])})"})
    sirens = sorted({b["owner_siren"] for b in buildings if b.get("owner_siren")})
    for i in range(0, len(sirens), 150):
        owners.update({o["siren"]: o for o in supabase("monopro_owners", {"select": "*", "siren": f"in.({','.join(sirens[i:i + 150])})"})})
    out = []
    async with httpx.AsyncClient(timeout=30) as client:
        for n, b in enumerate(buildings, 1):
            counts = {"nb_log": b["nb_log"], "dpe_fg": b.get("dpe_fg"), "dpe_count": b.get("dpe_count")}
            try:
                out.append(await audit_one(client, b, owners.get(b.get("owner_siren")), counts))
            except Exception as e:  # noqa: BLE001
                out.append({"immeuble": b["id"], "adresse": b.get("address"), "alertes": f"erreur : {type(e).__name__} {e}"})
            if n % 20 == 0:
                print(f"  {n} dossiers contrôlés", flush=True)
            await asyncio.sleep(0.2)
    path = os.path.join(args.dir, "audit_dossiers.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    alerts = Counter(a.strip().split(" (")[0] for r in out for a in (r.get("alertes") or "").split(";") if a.strip())
    sendable = [r for r in out if r.get("statut") == "envoyable"]
    clean = sum(1 for r in sendable if not r.get("alertes"))
    print(f"\n{len(out)} immeubles : {len(sendable)} envoyables, {len(out) - len(sendable)} écartés de la campagne")
    print(f"Envoyables : {clean} sans alerte ; {sum(1 for r in sendable if r.get('note'))} avec plus de logements "
          "estimés que connus (indiqué dans le dossier)")
    for a, n in alerts.most_common():
        print(f"  {n:4d}  {a}")
    print(f"Valeur affichée : {sum(1 for r in out if r.get('valeur_affichee') == 'oui')}")
    print(f"-> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out")
    ap.add_argument("--limit", type=int, default=10000, help="the first N firms of the ranking (all by default)")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
