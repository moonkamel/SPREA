import importlib.util
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("brevo_sync", Path(__file__).parent.parent / "scripts/campaign/brevo_sync.py")
brevo_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brevo_sync)


def test_hook_wording():
    h = brevo_sync.hook("Lambersart", 23, 210, 4, 1)
    assert h == ("À Lambersart, 23 logements classés F ou G ont reçu un nouveau DPE ces 30 derniers jours : autant de propriétaires "
                 "qui préparent souvent une vente ou une location, et 4 immeubles entiers appartiennent à une SCI ou une société, "
                 "dont 1 avec un signal de vente au BODACC (dissolution, liquidation…).")
    assert brevo_sync.hook("Bondues", 1, 5, 1, 0).startswith("À Bondues, 1 logement classé F ou G a reçu")
    assert "1 immeuble entier appartient" in brevo_sync.hook("Bondues", 1, 5, 1, 0)
    assert brevo_sync.hook("Sainghin", 0, 3, 0, 0) == "À Sainghin, 3 logements classés F ou G ont reçu un DPE ces douze derniers mois."
    assert brevo_sync.hook("Hameau", 0, 0, 0, 0) == "À Hameau, les nouveaux DPE de votre secteur arrivent chaque matin."


def test_figures(monkeypatch):
    monkeypatch.setattr(brevo_sync, "dpe_count", lambda insee, since: 12 if (date(2026, 10, 10) - since).days == 30 else 150)
    monkeypatch.setattr(brevo_sync, "building_counts", lambda insee: (7, 2))
    f = brevo_sync.figures("59350", "Lille", date(2026, 10, 10))
    assert f["SPREA_DPE_30J"] == 12 and f["SPREA_DPE_12M"] == 150 and f["SPREA_SIGNAUX"] == 2
    assert f["SPREA_LIEN"].endswith("utm_campaign=agences_59") and f["SPREA_MAJ"] == "2026-10-10"
    assert set(f) == set(brevo_sync.ATTRIBUTES)
