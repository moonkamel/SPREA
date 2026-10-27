"""Daily prospection send through Brevo (transactional API): the 4-email
sequence of docs/prospection-sequence.md, one recipient per email, from the
files of the campaign-suivi branch:
  prospects_a_contacter.csv  agencies to contact (agence;ville;email;...)
  prospection-suivi.csv      one line per address: etape (1-4), dernier_envoi, statut

Follow-ups first (7 days after the previous email, statut « en cours »,
etape < 4), then new contacts, up to the daily quota. Addresses Brevo blocks
(unsubscribed, hard bounce, spam complaint) leave the sequence. Replies (STOP
or other) are read in the contact@sprea.app inbox and set in the tracking
file before the send; the sender's replies go there (replyTo).

  BREVO_API_KEY=... python scripts/campaign/send_brevo.py --dir suivi --quota 50
  python scripts/campaign/send_brevo.py --dir suivi --dry-run      # no email sent, prints the plan
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
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

BREVO = "https://api.brevo.com/v3"
SENDER = {"name": "SPREA", "email": "contact@sprea.app"}
REPLY_TO = {"email": "contact@sprea.app", "name": "SPREA"}
DEMO = "https://sprea.app/demo?utm_source=email&amp;utm_medium=prospection&amp;utm_campaign={campaign}"
TRACK_COLS = ["siren", "agence", "ville", "email", "etape", "dernier_envoi", "statut", "source_url"]
FOLLOW_UP_DAYS = 7
SMALL = {"de", "du", "des", "la", "le", "les", "et", "d", "l", "en", "sur", "lez", "à", "au", "aux", "par"}
UPPER = {"sarl", "sas", "sasu", "eurl", "sci", "sa", "ei", "glv", "nbbs", "mc", "ab", "mav", "epim", "sbi", "ilo"}

FONT = "font-family:Arial, Helvetica, sans-serif; font-size:15px; line-height:23px; color:#1f2937; max-width:580px"
P = '<p style="margin:0 0 14px">{}</p>'
BUTTON = ('<table cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px"><tr><td style="background:#0a0f1a; '
          'border-radius:6px"><a href="{href}" style="display:inline-block; padding:12px 22px; color:#ffffff; '
          'text-decoration:none; font-weight:bold; font-size:15px">{label}</a></td></tr></table>')
SIGN_OFF = ('<p style="margin:0 0 4px">Bien à vous,</p><p style="margin:0 0 18px"><b>L\'équipe SPREA</b></p>')
# Same card as the contact@sprea.app signature
SIGNATURE = ('<table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial, Helvetica, sans-serif; '
             'color:#1f2937; font-size:13px; line-height:18px; margin:4px 0 0"><tr><td style="border-left:3px solid '
             '#c9a45c; padding-left:12px"><div style="font-family:Georgia, \'Times New Roman\', serif; font-size:20px; '
             'line-height:24px; font-weight:bold; color:#0a0f1a; letter-spacing:0.5px">SPREA</div><div style="color:'
             '#8a6d2f; font-size:12px">L\'outil DPE des pros de l\'immobilier</div><div style="margin-top:6px">'
             'contact@sprea.app · <a href="https://sprea.app" style="color:#8a6d2f; font-weight:bold; text-decoration:'
             'none">sprea.app</a></div><div style="color:#6b7280; font-size:11px; margin-top:4px">Prospection des '
             'passoires thermiques · Simulateur de rénovation · Avis de valeur</div></td></tr></table>')
FOOTER = ('<div style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#9ca3af; '
          'border-top:1px solid #e5e7eb; padding-top:8px; margin-top:20px; max-width:580px">SPREA EI, 239b rue du '
          'Jardin des Plantes, 59000 Lille. Pour ne plus recevoir nos messages, répondez simplement « STOP ».</div>')


# Independent advisors of a network: the address is theirs (prenom.nom@domain)
NETWORKS = {"iadfrance.fr": "mandataires"}


def first_name(address: str, name: str = "") -> Optional[str]:
    """First name of a network advisor (« laurie-ann.vieilly@iadfrance.fr » -> « Laurie-Ann »), "" when the
    address has only an initial and the name shows none either, None for an agency address."""
    local, _, domain = address.strip().lower().partition("@")
    if domain not in NETWORKS or "." not in local:
        return None
    first = local.split(".")[0]
    if len(first) < 2:
        words = name.split()
        first = words[0].lower() if len(words) > 1 and len(words[0].strip(".")) > 1 else ""
    return "-".join(p[:1].upper() + p[1:] for p in first.split("-")) if first else ""


def nice(text: str) -> str:
    """« L'IMMOBILIERE DE FACHES » -> « L'Immobiliere de Faches » (accents kept as written)."""
    if any(c.islower() for c in text):
        return text.strip()
    out = []
    for i, w in enumerate(re.split(r"(\s+|-|'|’)", text.strip().lower())):
        if not w or re.fullmatch(r"\s+|-|'|’", w):
            out.append(w)
        elif w in UPPER:
            out.append(w.upper())
        else:
            out.append(w if (w in SMALL and i > 0) else w[:1].upper() + w[1:])
    return "".join(out)


def numbered(items: List[tuple]) -> str:
    rows = "".join(f'<tr><td style="padding:4px 10px 4px 0; vertical-align:top; color:#b8913f; font-weight:bold">{n}.</td>'
                   f'<td style="padding:4px 0"><b>{b}</b>{rest}</td></tr>' for n, (b, rest) in enumerate(items, 1))
    return f'<table cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px; font-size:15px; line-height:22px; color:#1f2937">{rows}</table>'


def email(step: int, agence: str, ville: str, campaign: str, prenom: Optional[str] = None) -> Dict[str, str]:
    """prenom not None: an independent advisor of a network (iad...), addressed by first name when known."""
    a, v = html.escape(agence), html.escape(ville)
    demo = DEMO.format(campaign=campaign)
    if step == 1:
        subject = f"Les propriétaires de passoires de {ville}, avant les autres"
        body = (P.format(f"À {v}, des logements classés <b>F ou G</b> reçoivent chaque mois un <b>nouveau DPE</b>. Un DPE "
                         "récent précède souvent une <b>vente ou une mise en location</b> : ce sont autant de propriétaires "
                         "à contacter <b>avant les autres agences</b>.")
                + '<p style="margin:0 0 8px">Nous avons créé <b>SPREA</b> pour '
                + ('les conseillers indépendants comme vous :</p>' if prenom is not None else f'les agences comme <b>{a}</b> :</p>')
                + numbered([("Chaque matin, les nouveaux DPE de votre secteur", " sur une carte, adresse par adresse"),
                            ("Un courrier prêt à envoyer", " au propriétaire, en un clic"),
                            ("Un dossier chiffré à lui remettre", " : travaux, aides, valeur avant et après rénovation")])
                + BUTTON.format(href=demo, label="Voir la visite guidée (3 minutes) →")
                + P.format("Si c'est utile, <b>nous vous le montrons en 20 minutes sur vos propres rues</b>. Un créneau "
                           "cette semaine ? Il suffit de répondre à ce mail."))
    elif step == 2:
        subject = "Une passoire en mandat qui ne part pas ?"
        body = (P.format("Un complément à notre message de la semaine dernière.")
                + P.format("Quand un bien classé <b>F ou G</b> ne se vend pas, c'est souvent parce que les acheteurs "
                           "imaginent un gouffre. Depuis SPREA, vous générez <b>en deux minutes un dossier acheteur à vos "
                           "couleurs</b> :")
                + numbered([("Le programme de travaux", " adapté au bien"),
                            ("Les aides", " auxquelles l'acheteur a droit"),
                            ("La valeur après rénovation", ", appuyée sur les ventes comparables du quartier, et le loyer possible")])
                + P.format("L'acheteur ne voit plus une passoire, mais <b>un projet chiffré</b>. Le même dossier, en version "
                           f"propriétaire, vous sert au premier rendez-vous pour décrocher le mandat suivant.")
                + BUTTON.format(href=demo, label="Voir un dossier en images →"))
    elif step == 3:
        subject = "Un mandat paie des années d'abonnement"
        body = (P.format("Le calcul est simple : sur une vente à 250 000 €, les honoraires dépassent <b>10 000 € HT</b>. "
                         "L'abonnement SPREA démarre à <b>79 € TTC par mois</b>. Un seul mandat signé grâce à un DPE repéré "
                         "à temps le rembourse <b>plus de dix fois</b>.")
                + P.format(f"Nous vous proposons <b>20 minutes en visio, sur {'votre secteur' if prenom is not None else 'le secteur de ' + a}</b> : vous voyez les "
                           "propriétaires de vos rues et les immeubles de SCI qui risquent de se vendre, puis vous décidez. "
                           "Répondez simplement avec un créneau.")
                + BUTTON.format(href=demo, label="Voir la visite guidée (3 minutes) →"))
    else:
        subject = "Nous ne vous relancerons plus"
        body = (P.format("Nous ne vous écrirons plus à ce sujet.")
                + P.format(f"Si un jour vous voulez voir les <b>nouveaux DPE</b> et les <b>biens à fort potentiel</b> de "
                           f"{v}, la visite guidée reste ici :")
                + BUTTON.format(href=demo, label="Voir la visite guidée →"))
    hello = f"Bonjour {html.escape(prenom)}," if prenom else "Bonjour,"
    content = (f'<div style="{FONT}">' + P.format(hello) + body + SIGN_OFF + "</div>" + SIGNATURE + FOOTER)
    return {"subject": subject, "html": content}


def api(method: str, path: str, key: str, body: Optional[Dict] = None):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        req = urllib.request.Request(BREVO + path, data=data, method=method,
                                     headers={"api-key": key, "accept": "application/json", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.code == 429 and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"message": raw.decode(errors="replace")[:300]}
    return 429, {"message": "rate limited"}


def blocked(key: str) -> Dict[str, str]:
    """Addresses Brevo no longer delivers to: email -> reason."""
    out, offset = {}, 0
    while True:
        status, data = api("GET", f"/smtp/blockedContacts?limit=100&offset={offset}", key)
        if status != 200:
            print(f"Contacts bloqués illisibles : {status} {data}", file=sys.stderr)
            return out
        items = data.get("contacts") or []
        for c in items:
            out[c["email"].lower()] = (c.get("reason") or {}).get("code") or "bloqué"
        if len(items) < 100:
            return out
        offset += 100


def read(path: str) -> List[Dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="checkout of the campaign-suivi branch")
    ap.add_argument("--quota", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args()
    key = os.getenv("BREVO_API_KEY", "")
    if not key and not args.dry_run:
        sys.exit("BREVO_API_KEY manquant")
    today = date.fromisoformat(args.today)
    track_path = os.path.join(args.dir, "prospection-suivi.csv")
    track = read(track_path)
    prospects = read(os.path.join(args.dir, "prospects_a_contacter.csv"))

    if key:
        for email_addr, reason in blocked(key).items():
            for t in track:
                if t["email"].lower() == email_addr and t["statut"] == "en cours":
                    t["statut"] = "STOP" if "unsub" in reason.lower() or "spam" in reason.lower() else "rebond"

    due = [t for t in track if t["statut"] == "en cours" and int(t["etape"] or 1) < 4 and t["dernier_envoi"]
           and date.fromisoformat(t["dernier_envoi"]) + timedelta(days=FOLLOW_UP_DAYS) <= today]
    known = {t["email"].lower() for t in track}
    fresh, seen = [], set()
    for p in prospects:
        e = p["email"].strip().lower()
        if e and e not in known and e not in seen:
            seen.add(e)
            fresh.append(p)
    plan = [("relance", t) for t in due] + [("nouveau", p) for p in fresh]
    plan = plan[:args.quota]
    print(f"{len(due)} relances dues, {len(fresh)} nouveaux contacts ; envoi de {len(plan)} (quota {args.quota})")

    sent = errors = 0
    for kind, row in plan:
        step = int(row["etape"]) + 1 if kind == "relance" else 1
        agence, ville = nice(row["agence"]), nice(row["ville"])
        prenom = first_name(row["email"], row["agence"])
        cp = row.get("code_postal") or ""
        if prenom is not None:
            # (follow-ups come from the tracking file, which has the town but no postcode)
            campaign = f"{NETWORKS[row['email'].strip().lower().rpartition('@')[2]]}_{re.sub(r'[^a-z]+', '-', ville.lower())}"
        else:
            campaign = "agences_75" if cp.startswith("75") or ville.lower() == "paris" else "agences_59"
        msg = email(step, agence, ville, campaign, prenom)
        if args.dry_run:
            print(f"[essai] mail {step} -> {row['email']} : {msg['subject']}")
            continue
        status, data = api("POST", "/smtp/email", key, {
            "sender": SENDER, "replyTo": REPLY_TO, "to": [{"email": row["email"].strip(), "name": agence}],
            "subject": msg["subject"], "htmlContent": msg["html"], "tags": ["prospection", f"mail{step}"],
        })
        if status not in (200, 201):
            errors += 1
            print(f"ERREUR {status} {row['email']} : {data.get('message')}", flush=True)
            if status in (401, 403) or errors >= 3:
                print("Arrêt des envois du jour.", flush=True)
                break
            continue
        sent += 1
        print(f"OK mail {step} -> {row['email']} ({data.get('messageId', '')})", flush=True)
        if kind == "relance":
            row["etape"], row["dernier_envoi"] = str(step), today.isoformat()
        else:
            track.append({"siren": row.get("siren", ""), "agence": row["agence"], "ville": row["ville"],
                          "email": row["email"].strip(), "etape": "1", "dernier_envoi": today.isoformat(),
                          "statut": "en cours", "source_url": row.get("source_url", "")})
        time.sleep(2)

    if not args.dry_run:
        with open(track_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TRACK_COLS, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(track)
    print(f"Bilan {datetime.now():%Y-%m-%d %H:%M} : {sent} envoyés, {errors} erreurs")


if __name__ == "__main__":
    main()
