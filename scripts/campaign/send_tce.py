"""First email to the TCE/RGE firms of the chantiers file (scripts/apify/tce_chantiers.py):
one building owned by a company near each firm, with its SPREA dossier (signed link,
no account). Brevo transactional API, one recipient per email.

Inputs, in the checkout of the apify-tce branch (--dir):
  prospection_TCE_chantiers.csv        firms ranked by relevance, one building each
  prospection_tce_hauts_de_france.csv  the firms (address, type)
  4_immeubles_fg.json                  the buildings (id behind each dossier link)
  envois_tce.csv                       tracking: one line per address written to

Only facts are written: the share of F/G dwellings comes from the DPE published
for the building (Supabase, monopro_buildings), the value lines are promised only
when the PDF really has them (each dossier is opened and read before the send).
Left out: no address, internal-service or unchecked domains, companies in
liquidation (their owner does not "face" the works), an address already written to.

  python scripts/campaign/send_tce.py --dir out --limit 300 --dry-run   # preview, no email
  BREVO_API_KEY=... python scripts/campaign/send_tce.py --dir out --limit 300 --quota 150
"""
import argparse
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
from send_brevo import api, credits_left, nice  # noqa: E402

SENDER = {"name": "Tarik Lakel - SPREA", "email": "contact@sprea.app"}
REPLY_TO = {"email": "contact@sprea.app", "name": "Tarik Lakel"}
TRACK = "envois_tce.csv"
TRACK_COLS = ["email", "entreprise", "immeuble", "lien", "envoi", "statut"]
SKIP_STATUS = {"À éviter (service interne)", "Domaine à vérifier"}
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


def dwellings_sentence(nb_log: int, fg: Optional[int], diagnosed: Optional[int], label: str, dpe_date: str) -> str:
    """What the published DPE say, no more: all the dwellings F/G, or how many of the diagnosed ones."""
    when = f" ({month_year(dpe_date)})" if month_year(dpe_date) else ""
    if fg is not None and fg >= nb_log:
        return f"Les {nb_log} logements de cet immeuble sont classés F ou G{when}."
    head = f"Les DPE publiés pour cet immeuble de {nb_log} logements le classent {label}{when}"
    if not fg:
        return head + "."
    if diagnosed and diagnosed < nb_log:
        return head + f" : {fg} des {diagnosed} logements diagnostiqués sont classés F ou G."
    return head + (f" : {fg} de ses {nb_log} logements sont classés F ou G." if fg > 1 else
                   f" : 1 de ses {nb_log} logements est classé F ou G.")


def ban_sentence(label: str, holder: str) -> str:
    if label == "G":
        rule = ("Les logements classés G ne peuvent plus être proposés à un nouveau locataire depuis le "
                "1er janvier 2025, et les logements classés F suivront le 1er janvier 2028")
    else:
        rule = "Les logements classés F ne pourront plus être proposés à un nouveau locataire à partir du 1er janvier 2028"
    return (f"{rule} : le propriétaire ({holder}) est directement concerné par ces restrictions locatives, et des "
            f"travaux d'envergure seront nécessaires pour continuer à louer ces logements.")


def compose(row: Dict, firm: Dict, building: Dict, has_value: bool) -> Dict:
    surface = m2(row["Surface_m2"])
    btown, ftown = town(row["Immeuble_Adresse"]), town(firm.get("Adresse", ""))
    label = row["DPE"]
    prenom = first_name(row["Dirigeant"])
    company = display(row["Entreprise"])
    holder = owner(row["SCI_Nom"])
    dist = float(row["Distance_km"])
    dist_txt = "moins d'1 km" if dist < 1 else f"{dist:.0f}{NBSP}km"
    link = row["Lien_Dossier"]
    contents = ("l'estimation détaillée des travaux, la décote actuelle du bien et sa valeur après rénovation"
                if has_value else "l'estimation détaillée des travaux, logement par logement")
    subject = f"Opportunité : Immeuble de {surface}{NBSP}m² classé {label} à {btown}"
    paras = [
        f"Bonjour {prenom}," if prenom else "Bonjour,",
        f"Je me permets de vous contacter car j'ai identifié que votre entreprise, {company}, est en mesure de mener "
        f"des chantiers de rénovation globale dans le secteur de {ftown}.",
        f"En croisant les bases de données publiques (ADEME, DVF, Cadastre), je suis tombé sur une opportunité qui "
        f"correspond à votre zone d'intervention : un immeuble en monopropriété de {surface}{NBSP}m² situé à {btown} "
        f"({row['Immeuble_Adresse']}), à seulement {dist_txt} de votre entreprise.",
        dwellings_sentence(int(building["nb_log"]), building.get("dpe_fg"), building.get("dpe_count"), label,
                           row.get("Date_DPE", "")) + " "
        + ban_sentence(label, holder),
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


def eligible(rows: List[Dict], written: set) -> List[Dict]:
    out, seen = [], set(written)
    for r in rows:
        e = r["Email"].strip().lower()
        if not e or r["Email_Statut"] in SKIP_STATUS or e in seen or "iquidat" in r.get("SCI_Gerant", ""):
            continue
        seen.add(e)
        out.append(r)
    return out


def dpe_counts(ids: List[str]) -> Dict[str, Dict]:
    """nb_log and F/G dwellings of the buildings, from Supabase."""
    url, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    out = {}
    for i in range(0, len(ids), 100):
        q = urllib.parse.urlencode({"select": "id,nb_log,dpe_count,dpe_fg", "id": f"in.({','.join(ids[i:i + 100])})"})
        req = urllib.request.Request(f"{url}/rest/v1/monopro_buildings?{q}",
                                     headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as res:
            out.update({b["id"]: b for b in json.load(res)})
    return out


def pdf_check(link: str, cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    """None: the dossier does not open; else whether it shows the value lines."""
    if link in cache:
        return cache[link]
    import pdfplumber
    result = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(link, timeout=120) as res:
                raw = res.read()
            if raw[:4] == b"%PDF":
                with pdfplumber.open(io.BytesIO(raw)) as pdf:
                    txt = " ".join(p.extract_text() or "" for p in pdf.pages)
                result = "après rénovation" in txt and "Décote liée au DPE" in txt
            break
        except Exception as e:  # noqa: BLE001
            print(f"Dossier illisible ({e}) : {link}", flush=True)
            time.sleep(5)
    cache[link] = result
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--limit", type=int, default=300, help="the first N firms by relevance")
    ap.add_argument("--quota", type=int, default=150, help="emails at most for this run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.getenv("BREVO_API_KEY", "")
    if not args.dry_run and not key:
        sys.exit("BREVO_API_KEY manquant")

    rows = read(os.path.join(args.dir, "prospection_TCE_chantiers.csv"))
    firms = {r["Entreprise_Nom"]: r for r in read(os.path.join(args.dir, "prospection_tce_hauts_de_france.csv"))}
    facts = json.load(open(os.path.join(args.dir, "4_immeubles_fg.json"), encoding="utf-8"))
    by_link = {f["link"]: f for f in facts if f.get("link")}
    track_path = os.path.join(args.dir, TRACK)
    track = read(track_path)
    written = {t["email"].strip().lower() for t in track}

    # The first N of the ranking are the campaign; those already written to are done
    campaign = eligible(rows, set())[:args.limit]
    todo = [r for r in campaign if r["Email"].strip().lower() not in written]
    print(f"{len(rows)} lignes, campagne : les {len(campaign)} premières adresses valables, "
          f"{len(campaign) - len(todo)} déjà écrites, {len(todo)} à écrire")
    counts = dpe_counts(sorted({by_link[r["Lien_Dossier"]]["id"] for r in todo if r["Lien_Dossier"] in by_link}))

    budget = len(todo) if args.dry_run else args.quota
    if not args.dry_run:
        left = credits_left(key)
        if left is not None:
            budget = min(budget, max(0, left))
        print(f"Crédits Brevo du jour : {'?' if left is None else left} -> {budget} envois au plus")

    cache: Dict[str, Optional[bool]] = {}
    plan, previews, sent, errors, skipped = [], [], 0, 0, 0
    for r in todo:
        if sent >= budget and not args.dry_run:
            break
        f = by_link.get(r["Lien_Dossier"])
        b = counts.get(f["id"]) if f else None
        has_value = pdf_check(r["Lien_Dossier"], cache)
        if not b or has_value is None:
            skipped += 1
            print(f"Écarté (dossier ou immeuble introuvable) : {r['Entreprise']}", flush=True)
            continue
        msg = compose(r, firms.get(r["Entreprise"], {}), b, has_value)
        plan.append({"email": r["Email"].strip(), "entreprise": r["Entreprise"], "score": r["Score"],
                     "objet": msg["subject"], "valeur_dans_pdf": "oui" if has_value else "non",
                     "logements_fg": f"{b.get('dpe_fg')}/{b['nb_log']}"})
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
        print(f"OK -> {r['Email']} ({data.get('messageId', '')})", flush=True)
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
        with open(track_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=TRACK_COLS, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(track)
        print(f"Bilan {datetime.now():%Y-%m-%d %H:%M} : {sent} envoyés, {errors} erreurs, {skipped} écartés")


if __name__ == "__main__":
    main()
