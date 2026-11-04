"""First email to the TCE/RGE firms of the chantiers file (scripts/apify/tce_chantiers.py):
one building owned by a company near each firm, with its SPREA dossier (signed link,
no account). Brevo transactional API, one recipient per email.

Inputs, in the checkout of the apify-tce branch (--dir):
  prospection_TCE_chantiers.csv        firms ranked by relevance, one building each
  prospection_tce_hauts_de_france.csv  the firms (address, type)
  4_immeubles_fg.json                  the buildings (id behind each dossier link)
  envois_tce.csv                       tracking: one line per address written to

The email is written from the dossier itself: each building's dossier is rebuilt
exactly as the signed link does (api/monopro_report.py, with the DPE of the ADEME
and the DVF prices), and the subject, the F/G dwellings, the order of the sends
and the promise of the value lines all come from it, so the email and the PDF
never disagree. Left out: no address, internal-service or unchecked domains,
firms that carry out no works, companies in liquidation, an address already
written to, and buildings a dossier cannot back (no F/G dwelling among the
published DPE, nor a collective DPE classed F or G).

  python scripts/campaign/send_tce.py --dir out --limit 300 --dry-run   # preview, no email
  BREVO_API_KEY=... python scripts/campaign/send_tce.py --dir out --limit 300 --quota 150
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from send_brevo import api, credits_left, nice  # noqa: E402

SENDER = {"name": "SPREA", "email": "contact@sprea.app"}
REPLY_TO = {"email": "contact@sprea.app", "name": "Tarik Lakel"}
TRACK = "envois_tce.csv"
TRACK_COLS = ["email", "entreprise", "immeuble", "lien", "envoi", "statut"]
SKIP_STATUS = {"À éviter (service interne)", "Domaine à vérifier"}
# Within the campaign, the addresses most likely read by the person written to go first
# (and protect the domain's reputation while it warms up)
STATUS_ORDER = {"Nominatif (dirigeant)": 0, "Nominatif": 1, "Générique": 2, "Messagerie perso": 3}
NBSP = " "
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]

FONT = "font-family:Arial, Helvetica, sans-serif; font-size:15px; line-height:23px; color:#1f2937; max-width:600px"
P = '<p style="margin:0 0 14px">{}</p>'
FOOTER = ('<div style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#9ca3af; '
          'border-top:1px solid #e5e7eb; padding-top:8px; margin-top:20px; max-width:600px">SPREA, sprea.app. '
          'Pour ne plus recevoir de message de ma part, répondez simplement « STOP ».</div>')


def read(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def town(address: str) -> str:
    """« 8 Rue Philippe Lebon 59100 Roubaix » / « 159 RUE X, 59100 ROUBAIX » -> « Roubaix »."""
    m = re.search(r"\b\d{5}\s+(.+)$", address or "")
    t = (m.group(1) if m else (address or "").rsplit(",", 1)[-1]).strip()
    t = re.sub(r"\s+CEDEX.*$", "", t, flags=re.I)
    return nice(t) if t.isupper() else t


def first_name(director: str) -> str:
    words = (director or "").split()
    return words[0] if len(words) >= 2 else ""


def display(name: str) -> str:
    """« JJM LIVE TOGETHER » -> « JJM Live Together » : a short word without a vowel is an acronym."""
    return " ".join(w.upper() if re.fullmatch(r"[bcdfghjklmnpqrstvwxz&]{2,4}", w.lower()) else w
                    for w in nice(name).split())


def owner(name: str) -> str:
    """« SCI LEBON » -> « la SCI Lebon », « JOLETA » -> « la société Joleta »."""
    n = display(name)
    return f"la {n}" if re.match(r"(?i)^(sci|scpi|sarl|sas|sasu|eurl|sa|snc)\b", n) else f"la société {n}"


def month_year(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    return f"{MONTHS[d.month - 1]} {d.year}"


def m2(v) -> str:
    return f"{int(float(v)):,}".replace(",", NBSP)


def verb(n: int) -> str:
    return "sont classés" if n > 1 else "est classé"


def dossier_facts(d: Dict) -> Dict:
    """What the dossier of the building shows about its DPE: the email says this and nothing else."""
    u, b = d["units"], d["building"]
    coll = d.get("building_dpe") or {}
    known_fg = u["known"]["F"] + u["known"]["G"]
    coll_fg = coll.get("label") in ("F", "G")
    worst = ("G" if u["known"]["G"] or coll.get("label") == "G" else
             "F" if u["known"]["F"] or coll.get("label") == "F" else None)
    n = u["n_known"]
    try:
        from api.monopro_pdf import value_pays
    except ImportError:
        from monopro_pdf import value_pays
    return {
        "nb_log": int(b["nb_log"]), "n_known": n, "known_fg": known_fg, "worst": worst, "shab": d["shab"],
        "collective": coll.get("label"), "collective_date": coll.get("date") or "",
        # a building the dossier backs: F/G dwellings among the published DPE, or a collective DPE F/G
        # with no dwelling DPE contradicting it
        "ok": bool(known_fg or (coll_fg and not n)),
        # most dwellings F/G: told by a collective DPE, or by at least two dwelling DPE (one says little)
        "major": bool(coll_fg or ((n >= 2 or n == int(b["nb_log"])) and known_fg * 2 >= n)),
        "has_value": value_pays(d),
    }


def place(nb: int) -> str:
    """« cette maison », « ce bâtiment de 2 logements », « cet immeuble de 6 logements »."""
    return "cette maison" if nb == 1 else "ce bâtiment de 2 logements" if nb == 2 else f"cet immeuble de {nb} logements"


def dwellings_sentence(f: Dict) -> str:
    """The published DPE as the dossier shows them, never a class the building does not have."""
    nb, n, kfg = f["nb_log"], f["n_known"], f["known_fg"]
    short = place(nb).split(" de ")[0]
    if nb == 1:
        return f"Le DPE de cette maison la classe {f['worst']}."
    if f["collective"] in ("F", "G"):
        when = f" ({month_year(f['collective_date'])})" if month_year(f["collective_date"]) else ""
        s = f"Le DPE collectif de {place(nb)} le classe {f['collective']}{when}"
        return s + (f", et {kfg} des {n} logements diagnostiqués {verb(kfg)} F ou G." if n else ".")
    if n == nb and kfg == nb:
        return f"Les {nb} logements de {short} sont classés F ou G."
    if n == 1:
        return (f"Le seul DPE publié pour {place(nb)} classe son logement {f['worst']}, et les autres "
                "logements n'ont pas encore de DPE.")
    if n == nb:
        return f"{kfg} des {nb} logements de {short} {verb(kfg)} F ou G."
    return f"{kfg} des {n} logements diagnostiqués de {place(nb)} {verb(kfg)} F ou G."


def subject_line(f: Dict, btown: str) -> str:
    surface = f"{m2(f['shab'])}{NBSP}m²"
    if f["nb_log"] == 1:
        return f"Opportunité : Maison de {surface} classée {f['worst']} à {btown}"
    noun = "Bâtiment" if f["nb_log"] == 2 else "Immeuble"
    if f["collective"] in ("F", "G"):
        return f"Opportunité : {noun} de {surface} classé {f['collective']} à {btown}"
    k = f["known_fg"]
    return f"Opportunité : {noun} de {surface} à {btown}, {k} logement{'s' if k > 1 else ''} classé{'s' if k > 1 else ''} F ou G"


def ban_sentence(label: str, holder: str, major: bool = True, house: bool = False) -> str:
    """major: at least half of the dwellings known are F or G; else « d'envergure » would overstate the job."""
    if house:
        rule = ("Une maison classée G ne peut plus être proposée à un nouveau locataire depuis le 1er janvier 2025"
                if label == "G" else
                "Une maison classée F ne pourra plus être proposée à un nouveau locataire à partir du 1er janvier 2028")
        return (f"{rule} : si elle est louée, le propriétaire ({holder}) est directement concerné, et des travaux "
                "seront nécessaires pour continuer à la louer.")
    if label == "G":
        rule = ("Les logements classés G ne peuvent plus être proposés à un nouveau locataire depuis le "
                "1er janvier 2025, et les logements classés F suivront le 1er janvier 2028")
    else:
        rule = "Les logements classés F ne pourront plus être proposés à un nouveau locataire à partir du 1er janvier 2028"
    works = "des travaux d'envergure seront nécessaires" if major else "des travaux seront nécessaires"
    return (f"{rule} : le propriétaire ({holder}) est directement concerné par ces restrictions locatives, et "
            f"{works} pour continuer à louer ces logements.")


def what_is(nb: int) -> str:
    return "une maison" if nb == 1 else "un bâtiment de 2 logements" if nb == 2 else "un immeuble en monopropriété"


def compose(row: Dict, firm: Dict, f: Dict) -> Dict:
    """f: dossier_facts() of the building."""
    surface = m2(f["shab"])
    btown, ftown = town(row["Immeuble_Adresse"]), town(firm.get("Adresse", ""))
    prenom = first_name(row["Dirigeant"])
    company = display(row["Entreprise"])
    holder = owner(row["SCI_Nom"])
    dist = float(row["Distance_km"])
    dist_txt = "moins d'1 km" if dist < 1 else f"{dist:.0f}{NBSP}km"
    link = row["Lien_Dossier"]
    contents = ("l'estimation détaillée des travaux, la décote actuelle du bien et sa valeur après rénovation"
                if f["has_value"] else "l'estimation détaillée des travaux, logement par logement")
    subject = subject_line(f, btown)
    paras = [
        f"Bonjour {prenom}," if prenom else "Bonjour,",
        f"Je me permets de vous contacter car j'ai identifié que votre entreprise, {company}, est en mesure de mener "
        f"des chantiers de rénovation globale dans le secteur de {ftown}.",
        "SPREA, la plateforme que j'ai développée, associe une expertise technique du bâtiment (performance "
        "énergétique, chiffrage des travaux) à l'intelligence artificielle.",
        f"En analysant le parc immobilier de votre secteur, elle a repéré une opportunité qui correspond à votre zone "
        f"d'intervention : {what_is(f['nb_log'])} de {surface}{NBSP}m² situé{'e' if f['nb_log'] == 1 else ''} à {btown} "
        f"({row['Immeuble_Adresse']}), à seulement {dist_txt} de votre entreprise.",
        dwellings_sentence(f) + " " + ban_sentence(f["worst"], holder, f["major"], f["nb_log"] == 1),
        f"Pour vous faire gagner un temps considérable, j'ai utilisé mon outil d'analyse pour générer le dossier "
        f"complet de ce chantier. Vous y trouverez {contents}.",
        "Vous pouvez télécharger l'analyse PDF gratuitement ici :",
    ]
    tail = [
        "Je ne vends pas de simples fichiers d'adresses. Si ce type de dossier vous intéresse, je peux vous fournir un "
        "flux régulier d'opportunités de chantiers pré-qualifiés, ciblés spécifiquement pour votre entreprise.",
        f"Mon Pack Découverte comprend 3 dossiers de ce type pour 99{NBSP}€ HT.",
        "Si vous souhaitez en discuter ou récupérer d'autres opportunités dans votre secteur, répondez simplement à "
        "cet email.",
        "Bonne réception, et n'hésitez pas à me faire un retour sur le dossier PDF !",
    ]
    href = html.escape(link, quote=True)
    body = "".join(P.format(html.escape(p)) for p in paras)
    body += P.format(f'<a href="{href}" style="color:#8a6d2f; font-weight:bold">Télécharger le dossier PDF de '
                     f'l\'immeuble</a>')
    body += "".join(P.format(html.escape(p)) for p in tail)
    body += P.format("Cordialement,<br><br><b>Tarik Lakel</b><br>Fondateur SPREA<br>"
                     '<a href="https://sprea.app" style="color:#8a6d2f">sprea.app</a>')
    text = "\n\n".join(paras + [link] + tail + ["Cordialement,\n\nTarik Lakel\nFondateur SPREA\nsprea.app",
                                                 "Pour ne plus recevoir de message de ma part, répondez « STOP »."])
    return {"subject": subject, "html": f'<div style="{FONT}">{body}</div>{FOOTER}', "text": text}


def order(todo: List[Dict], facts: Dict[str, Dict], building_of: Dict[str, str]) -> List[Dict]:
    """Buildings where most known dwellings are F or G first (the strongest worksites), then the
    addresses most likely read by the person written to; score order kept within (stable sort)."""
    def key(r):
        f = facts.get(building_of.get(r["Lien_Dossier"], ""))
        return (0 if f and f["major"] else 1, STATUS_ORDER.get(r["Email_Statut"], 9))
    return sorted(todo, key=key)


def does_works(firm: Optional[Dict]) -> bool:
    """A firm that carries out works (NAF 41.20 building, 43.xx specialised trades): architects (71.11Z),
    design offices, developers or wholesalers are not « en mesure de mener des chantiers »."""
    if firm is None:
        return True  # not in the firms file: kept, as before
    codes = re.findall(r"\d{2}\.\d{2}[A-Z]?", firm.get("Codes_NAF") or "")
    return not codes or any(c.startswith(("41.2", "43.")) for c in codes)


def eligible(rows: List[Dict], written: set, firms: Optional[Dict[str, Dict]] = None) -> List[Dict]:
    out, seen = [], set(written)
    for r in rows:
        e = r["Email"].strip().lower()
        if not e or r["Email_Statut"] in SKIP_STATUS or e in seen or "iquidat" in r.get("SCI_Gerant", ""):
            continue
        if firms is not None and not does_works(firms.get(r["Entreprise"])):
            continue
        seen.add(e)
        out.append(r)
    return out


def supabase_rows(table: str, field: str, values: List[str], select: str = "*") -> List[Dict]:
    url, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    out = []
    for i in range(0, len(values), 100):
        q = urllib.parse.urlencode({"select": select, field: f"in.({','.join(values[i:i + 100])})"})
        req = urllib.request.Request(f"{url}/rest/v1/{table}?{q}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as res:
            out += json.load(res)
    return out


async def building_dossier(client, b: Dict, owner: Optional[Dict]) -> Dict:
    """The dossier of the building as the signed link builds it (api/monopro.py dossier_response):
    DPE of the ADEME around it, local DVF prices. The company details do not change the facts."""
    from api.dvf import market_price
    from api.immeuble import ademe_rows
    from api.monopro_report import build_dossier, unit_surface
    rows: List[Dict] = []
    try:
        rows = await ademe_rows(client, {"geo_distance": f"{b['lon']},{b['lat']},30", "size": "300"})
    except Exception as e:  # noqa: BLE001  as the site: the dossier is made without them
        print(f"ADEME illisible pour {b['id']} : {type(e).__name__}", flush=True)
    market = None
    try:
        market = await market_price(b.get("insee") or "", "Appartement", b["lat"], b["lon"], unit_surface(b, rows))
    except Exception:  # noqa: BLE001
        pass
    return build_dossier(b, owner, None, 0, rows, market, {"agency_name": "SPREA"})


def campaign_facts(candidates: List[Dict], written: set, building_of: Dict[str, str], limit: int):
    """Walk the ranking: an address already written to counts in the campaign; another one counts only
    if the dossier of its building backs it. Returns (todo, facts per building, excluded rows)."""
    import asyncio
    import httpx
    ids = sorted({building_of[r["Lien_Dossier"]] for r in candidates if r["Lien_Dossier"] in building_of})
    buildings = {b["id"]: b for b in supabase_rows("monopro_buildings", "id", ids)}
    sirens = sorted({b["owner_siren"] for b in buildings.values() if b.get("owner_siren")})
    owners = {o["siren"]: o for o in supabase_rows("monopro_owners", "siren", sirens)}
    facts: Dict[str, Dict] = {}

    async def run():
        todo, excluded, count = [], [], 0
        async with httpx.AsyncClient(timeout=30) as client:
            for r in candidates:
                if count >= limit:
                    break
                if r["Email"].strip().lower() in written:
                    count += 1
                    continue
                bid = building_of.get(r["Lien_Dossier"])
                b = buildings.get(bid)
                if not b:
                    excluded.append((r, "immeuble introuvable"))
                    continue
                if bid not in facts:
                    facts[bid] = dossier_facts(await building_dossier(client, b, owners.get(b.get("owner_siren"))))
                if not facts[bid]["ok"]:
                    excluded.append((r, "aucun logement F ou G parmi les DPE publiés"))
                    continue
                todo.append(r)
                count += 1
        return todo, excluded
    todo, excluded = asyncio.run(run())
    return todo, facts, excluded


def already_sent(key: str, days: int = 60) -> set:
    """Addresses Brevo already holds a TCE email for (tag tce-mail1): the tracking file
    can miss some if a run was cut short, Brevo cannot."""
    out, offset = set(), 0
    start, end = (date.today() - timedelta(days=days)).isoformat(), date.today().isoformat()
    while True:
        q = urllib.parse.urlencode({"startDate": start, "endDate": end, "tags": "tce-mail1", "event": "requests",
                                    "limit": 2500, "offset": offset})
        status, data = api("GET", f"/smtp/statistics/events?{q}", key)
        if status != 200:
            sys.exit(f"Envois Brevo illisibles ({status}) : arrêt, pour ne jamais écrire deux fois")
        rows = data.get("events") or []
        out |= {(e.get("email") or "").strip().lower() for e in rows}
        if len(rows) < 2500:
            return out - {""}
        offset += 2500


def save_track(path: str, track: List[Dict]):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRACK_COLS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(track)


def link_ok(link: str) -> bool:
    """The signed link opens a PDF: checked once per run, before any email points to it."""
    try:
        with urllib.request.urlopen(link, timeout=90) as res:
            return res.read(4) == b"%PDF"
    except Exception as e:  # noqa: BLE001
        print(f"Lien de dossier en échec ({e}) : {link}", flush=True)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--limit", type=int, default=300, help="the first N firms by relevance")
    ap.add_argument("--quota", type=int, default=40, help="emails at most for this run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-to", default="", help="send only the first email, through Brevo, to this address")
    args = ap.parse_args()
    key = os.getenv("BREVO_API_KEY", "")
    if args.test_to:
        args.dry_run = False
    if not args.dry_run and not key:
        sys.exit("BREVO_API_KEY manquant")

    rows = read(os.path.join(args.dir, "prospection_TCE_chantiers.csv"))
    firms = {r["Entreprise_Nom"]: r for r in read(os.path.join(args.dir, "prospection_tce_hauts_de_france.csv"))}
    facts = json.load(open(os.path.join(args.dir, "4_immeubles_fg.json"), encoding="utf-8"))
    by_link = {f["link"]: f for f in facts if f.get("link")}
    track_path = os.path.join(args.dir, TRACK)
    track = read(track_path)
    written = {t["email"].strip().lower() for t in track}
    if key and not args.dry_run:
        brevo = already_sent(key)
        missing = brevo - written
        if missing:
            print(f"{len(missing)} adresses déjà écrites selon Brevo mais absentes du suivi : ajoutées", flush=True)
            for e in sorted(missing):
                track.append({"email": e, "envoi": "", "statut": "envoyé (repris de Brevo)"})
            written |= missing

    # The first N of the ranking backed by a dossier are the campaign; those already written to count in it
    building_of = {link: f["id"] for link, f in by_link.items()}
    todo, facts, excluded = campaign_facts(eligible(rows, set(), firms), written, building_of, args.limit)
    print(f"{len(rows)} lignes ; {len(todo)} à écrire, {len(excluded)} écartées (dossier sans F/G établi)", flush=True)
    for r, why in excluded:
        print(f"  écartée : {r['Entreprise']} ({r['Immeuble_Adresse']}) : {why}", flush=True)
    todo = order(todo, facts, building_of)
    if todo and not args.dry_run and not link_ok(todo[0]["Lien_Dossier"]):
        sys.exit("Le site ne renvoie pas le dossier : aucun envoi")

    budget = len(todo) if args.dry_run else args.quota
    if not args.dry_run:
        left = credits_left(key)
        if left is not None:
            budget = min(budget, max(0, left))
        print(f"Crédits Brevo du jour : {'?' if left is None else left} -> {budget} envois au plus")

    plan, previews, sent, errors, skipped = [], [], 0, 0, 0
    for r in todo:
        if sent >= budget and not args.dry_run:
            break
        f = facts[building_of[r["Lien_Dossier"]]]
        msg = compose(r, firms.get(r["Entreprise"], {}), f)
        if args.test_to:  # the real email of the first firm, to a test inbox; nothing tracked
            status, data = api("POST", "/smtp/email", key, {
                "sender": SENDER, "replyTo": REPLY_TO, "to": [{"email": args.test_to}],
                "subject": msg["subject"], "htmlContent": msg["html"], "textContent": msg["text"], "tags": ["tce-test"]})
            print(f"Test Brevo -> {args.test_to} : {status} {data}")
            return
        plan.append({"email": r["Email"].strip(), "entreprise": r["Entreprise"], "score": r["Score"],
                     "objet": msg["subject"], "valeur_dans_pdf": "oui" if f["has_value"] else "non",
                     "logements_fg": f"{f['known_fg']}/{f['n_known']} connus, {f['nb_log']} logements"})
        if args.dry_run:
            if len(previews) < 5:
                previews.append(msg)
            continue
        status, data = api("POST", "/smtp/email", key, {
            "sender": SENDER, "replyTo": REPLY_TO, "to": [{"email": r["Email"].strip(), "name": display(r["Entreprise"])}],
            "subject": msg["subject"], "htmlContent": msg["html"], "textContent": msg["text"],
            "tags": ["tce", "tce-mail1"],
        })
        if status not in (200, 201):
            errors += 1
            print(f"ERREUR {status} {r['Email']} : {data.get('message') if isinstance(data, dict) else data}", flush=True)
            if status in (401, 403) or errors >= 3:
                print("Arrêt des envois.", flush=True)
                break
            continue
        sent += 1
        track.append({"email": r["Email"].strip(), "entreprise": r["Entreprise"], "immeuble": r["Immeuble_Adresse"],
                      "lien": r["Lien_Dossier"], "envoi": date.today().isoformat(), "statut": "envoyé"})
        print(f"OK {sent} -> {r['Email']} ({data.get('messageId', '')})", flush=True)
        save_track(track_path, track)  # after each email: a run cut short never writes twice
        time.sleep(2)

    if args.dry_run:
        with open(os.path.join(args.dir, "apercu_envoi_tce.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(plan[0]) if plan else ["email"], delimiter=";")
            w.writeheader()
            w.writerows(plan)
        with open(os.path.join(args.dir, "apercu_envoi_tce.html"), "w", encoding="utf-8") as fh:
            fh.write("<meta charset='utf-8'>" + "<hr style='margin:30px 0'>".join(
                f"<p style='font-family:Arial'><b>Objet :</b> {html.escape(m['subject'])}</p>{m['html']}"
                for m in previews))
        print(f"Essai : {len(plan)} emails prêts, {skipped} écartés, "
              f"{sum(1 for p in plan if p['valeur_dans_pdf'] == 'oui')} dossiers avec la valeur après rénovation")
    else:
        save_track(track_path, track)
        print(f"Bilan {datetime.now():%Y-%m-%d %H:%M} : {sent} envoyés, {errors} erreurs, {skipped} écartés")


if __name__ == "__main__":
    main()
