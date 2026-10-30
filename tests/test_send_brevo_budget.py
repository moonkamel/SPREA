import importlib.util
import os
from datetime import date

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "campaign"))
spec = importlib.util.spec_from_file_location(
    "send_brevo", os.path.join(os.path.dirname(__file__), "..", "scripts", "campaign", "send_brevo.py"))
send_brevo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_brevo)


def rows(day: str, n: int):
    return [{"dernier_envoi": day} for _ in range(n)]


def test_no_backlog_when_each_day_stays_under_the_cap():
    track = rows("2026-10-26", 300) + rows("2026-10-27", 300)
    assert send_brevo.backlog(track, date(2026, 10, 28), 300) == 0


def test_backlog_of_two_sends_in_one_day_is_carried_day_by_day():
    # 27/10: 365, 28/10: 600, 29/10 (this morning, sent before the reset): 300
    track = rows("2026-10-27", 365) + rows("2026-10-28", 600) + rows("2026-10-29", 300)
    assert send_brevo.backlog(track, date(2026, 10, 29), 300) == 365
    assert send_brevo.backlog(track, date(2026, 10, 30), 300) == 365
    assert send_brevo.backlog(track, date(2026, 10, 31), 300) == 65
    assert send_brevo.backlog(track, date(2026, 11, 2), 300) == 0


def test_rows_without_a_date_are_ignored():
    assert send_brevo.backlog([{"dernier_envoi": ""}, {}], date(2026, 10, 29), 300) == 0


def test_still_queued_reads_the_delivery_events(monkeypatch):
    import brevo_stats
    track = [{"email": "a@x.fr", "dernier_envoi": "2026-10-29", "statut": "en cours"},
             {"email": "B@x.fr", "dernier_envoi": "2026-10-29", "statut": "en cours"},
             {"email": "c@x.fr", "dernier_envoi": "2026-10-20", "statut": "en cours"},
             {"email": "d@x.fr", "dernier_envoi": "2026-10-29", "statut": "STOP"}]
    monkeypatch.setattr(brevo_stats, "events", lambda key, start, end: iter(
        [{"email": "a@x.fr", "event": "delivered"}, {"email": "b@x.fr", "event": "requests"}]))
    waiting = send_brevo.still_queued("k", track, date(2026, 10, 30))
    assert [t["email"] for t in waiting] == ["B@x.fr"]


def test_still_queued_is_unknown_when_brevo_cannot_be_read(monkeypatch):
    import urllib.error

    import brevo_stats

    def fail(*a):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(brevo_stats, "events", fail)
    assert send_brevo.still_queued("k", [], date(2026, 10, 30)) is None
