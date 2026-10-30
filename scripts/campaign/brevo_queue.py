"""Cancel the prospection emails still waiting at Brevo. Above the daily cap of
the free plan Brevo queues the emails and sends them after the reset of the
quota, around 1:30 at night: a prospection email at that hour makes no sense.

An address of the tracking file sent in the last days with no event of
delivery yet (delivered, bounce, blocked...) is still in the queue: its
message is looked up and deleted. Only the rows whose deletion Brevo accepted
are marked « annulé (file Brevo) » in the tracking file.

  BREVO_API_KEY=... python scripts/campaign/brevo_queue.py --dir suivi [--dry-run]
"""
import argparse
import csv
import os
import sys
import urllib.parse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from brevo_stats import events  # noqa: E402
from send_brevo import TRACK_COLS, api, read  # noqa: E402

# Events that mean the email left Brevo
GONE = {"delivered", "softBounces", "hardBounces", "blocked", "invalid", "error", "spam", "unsubscribed",
        "opened", "uniqueOpened", "proxyOpen", "uniqueProxyOpen", "clicks", "deferred"}
CANCELLED = "annulé (file Brevo)"


def queued_messages(key: str, email: str, since: date):
    """Message ids of the prospection emails sent to this address since the date."""
    q = urllib.parse.urlencode({"email": email, "startDate": since.isoformat(), "endDate": date.today().isoformat(),
                                "sort": "desc", "limit": 20})
    status, data = api("GET", f"/smtp/emails?{q}", key)
    if status != 200:
        print(f"Liste illisible pour {email} : {status} {data}", flush=True)
        return []
    return [m["messageId"] for m in data.get("transactionalEmails") or [] if m.get("messageId")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="checkout of the campaign-suivi branch")
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.getenv("BREVO_API_KEY", "")
    if not key:
        sys.exit("BREVO_API_KEY manquant")
    since = date.today() - timedelta(days=args.days)
    track_path = os.path.join(args.dir, "prospection-suivi.csv")
    track = read(track_path)

    gone = set()
    for e in events(key, since.isoformat(), date.today().isoformat()):
        if e.get("event") in GONE and e.get("email"):
            gone.add(e["email"].lower())
    recent = [t for t in track if t["statut"] == "en cours" and t["dernier_envoi"] >= since.isoformat()]
    waiting = [t for t in recent if t["email"].strip().lower() not in gone]
    print(f"{len(recent)} envois depuis le {since:%d/%m}, {len(recent) - len(waiting)} déjà partis, "
          f"{len(waiting)} encore en file chez Brevo", flush=True)
    by_day = {}
    for t in waiting:
        by_day[t["dernier_envoi"]] = by_day.get(t["dernier_envoi"], 0) + 1
    print("En file par jour d'envoi :", dict(sorted(by_day.items())), flush=True)
    if args.dry_run:
        return

    cancelled = failed = 0
    for t in waiting:
        ids = queued_messages(key, t["email"].strip(), since)
        ok = False
        for mid in ids:
            status, data = api("DELETE", f"/smtp/email/{urllib.parse.quote(mid, safe='')}", key)
            if status == 204:
                ok = True
            else:
                print(f"Refus {status} {t['email']} : {data.get('message') if isinstance(data, dict) else data}",
                      flush=True)
        if ok:
            t["statut"] = CANCELLED
            cancelled += 1
        else:
            failed += 1
        if failed >= 5 and not cancelled:
            print("Brevo refuse les annulations : arrêt.", flush=True)
            break

    with open(track_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACK_COLS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(track)
    print(f"Bilan : {cancelled} annulés, {failed} non annulés", flush=True)


if __name__ == "__main__":
    main()
