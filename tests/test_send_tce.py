import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "campaign"))
import send_tce as st  # noqa: E402

ROW = {"Score": "9.5", "Entreprise": "NORD BATI CONSTRUCTION", "Dirigeant": "François Fernand Paul Busato",
       "Email": "contact@nordbati.com", "Email_Statut": "Générique", "Distance_km": "2.2",
       "Immeuble_Adresse": "8 Rue Philippe Lebon 59100 Roubaix", "Logements": "16", "Surface_m2": "792", "DPE": "F",
       "Date_DPE": "2025-09-16", "SCI_Nom": "SCI LEBON", "SCI_Gerant": "Jean Dupont (Gérant)", "Lien_Dossier": "https://x/d?t=1"}
FIRM = {"Adresse": "159 TER RUE JOUFFROY, 59100 ROUBAIX"}


from datetime import date  # noqa: E402

from api import monopro_pdf, monopro_report  # noqa: E402
from tests.test_monopro import DOSSIER_BUILDING, OWNERS, TODAY, flat  # noqa: E402


def facts(rows, nb_log, label="F", market=None, **building):
    d = monopro_report.build_dossier({**DOSSIER_BUILDING, "nb_log": nb_log, "dpe_label": label, **building}, OWNERS[0], None,
                                     0, rows, market, {}, TODAY)
    return st.dossier_facts(d)


def collective(label, surface=300):
    return {"numero_dpe": "IMM", "type_batiment": "immeuble", "date_etablissement_dpe": "2026-03-10",
            "surface_habitable_immeuble": surface, "etiquette_dpe": label, "adresse_ban": DOSSIER_BUILDING["address"]}


def test_mail_from_a_building_with_few_fg_dwellings():
    """140 rue de Wazemmes: C D D E E G, no collective DPE."""
    f = facts([flat(i, c) for i, c in enumerate("CDDEEG")], 6, "G")
    assert f["ok"] and not f["major"] and f["known_fg"] == 1 and f["worst"] == "G"
    m = st.compose(ROW, FIRM, f)
    assert m["subject"].startswith("Opportunité : Immeuble de ") and m["subject"].endswith("à Roubaix, 1 logement classé F ou G")
    t = m["text"]
    assert t.startswith("Bonjour François,") and "Nord Bati Construction" in t and "secteur de Roubaix" in t
    assert "1 des 6 logements de cet immeuble est classé F ou G." in t and "classé G à" not in t
    assert "des travaux seront nécessaires" in t and "envergure" not in t
    assert "décote" not in t and "99\u00a0€ HT" in t and "STOP" in m["html"] and ROW["Lien_Dossier"] in m["html"]


def test_mail_from_a_single_dpe():
    """19 rue des Monnayeurs: 4 dwellings, one DPE F."""
    f = facts([flat(1, "F")], 4, "F")
    assert f["ok"] and f["major"]
    t = st.compose(ROW, FIRM, f)["text"]
    assert "Le seul DPE publié pour cet immeuble de 4 logements classe son logement F" in t
    assert "Les logements classés F ne pourront plus" in t and "d'envergure" in t


def test_mail_from_a_collective_dpe_and_value():
    rows = [collective("G")] + [flat(i, "GFE"[i % 3]) for i in range(4)]
    f = facts(rows, 12, "G", market={"price_per_m2": 6000, "source": "DVF"})
    m = st.compose(ROW, FIRM, f)
    assert m["subject"] == "Opportunité : Immeuble de 300\u00a0m² classé G à Roubaix"
    assert "Le DPE collectif de cet immeuble de 12 logements le classe G (mars 2026), et 3 des 4 logements" in m["text"]
    assert f["has_value"] and "décote actuelle du bien et sa valeur après rénovation" in m["text"]
    # Same promise as the PDF: the value lines are in it
    d = monopro_report.build_dossier({**DOSSIER_BUILDING, "nb_log": 12, "dpe_label": "G"}, OWNERS[0], None, 0, rows,
                                     {"price_per_m2": 6000, "source": "DVF"}, {}, TODAY)
    from tests.test_pdf import pdf_text
    assert "Décote liée au DPE" in pdf_text(monopro_pdf.generate(d, "tce"))


def test_buildings_a_dossier_cannot_back_are_left_out():
    # No DPE found at the address: only the class of our base, nothing to show
    assert not facts([], 4, "F")["ok"]
    # The latest DPE of the dwellings are no longer F or G
    assert not facts([flat(i, c) for i, c in enumerate("CDE")], 3, "F")["ok"]
    # A collective DPE G contradicted by every dwelling DPE
    assert not facts([collective("G")] + [flat(i, "D") for i in range(3)], 3, "G")["ok"]
    # A collective DPE F alone is enough
    assert facts([collective("F")], 4, "F")["ok"]


def test_order_puts_mostly_fg_buildings_first():
    rows = [dict(ROW, Email="a@x.fr", Email_Statut="Nominatif (dirigeant)", Lien_Dossier="L1"),
            dict(ROW, Email="b@x.fr", Email_Statut="Générique", Lien_Dossier="L2"),
            dict(ROW, Email="c@x.fr", Email_Statut="Nominatif (dirigeant)", Lien_Dossier="L2")]
    fx = {"b1": {"major": False}, "b2": {"major": True}}
    assert [r["Email"] for r in st.order(rows, fx, {"L1": "b1", "L2": "b2"})] == ["c@x.fr", "b@x.fr", "a@x.fr"]


def test_eligible_skips_bad_addresses_liquidations_duplicates_and_written():
    rows = [dict(ROW, Email="a@x.fr"), dict(ROW, Email="a@x.fr"), dict(ROW, Email=""),
            dict(ROW, Email="b@x.fr", Email_Statut="À éviter (service interne)"),
            dict(ROW, Email="c@x.fr", SCI_Gerant="Me X (Liquidateur)"), dict(ROW, Email="d@x.fr"),
            dict(ROW, Email="e@x.fr")]
    assert [r["Email"] for r in st.eligible(rows, {"d@x.fr"})] == ["a@x.fr", "e@x.fr"]


def test_first_name_needs_a_full_name():
    assert st.first_name("Grand") == "" and st.first_name("Marie Durand") == "Marie"
    assert st.town("22 RUE X, 59400 CAMBRAI CEDEX") == "Cambrai"


def test_nominative_addresses_first_score_order_kept():
    rows = [dict(ROW, Email="g@x.fr", Email_Statut="Générique"), dict(ROW, Email="p@x.fr", Email_Statut="Messagerie perso"),
            dict(ROW, Email="d1@x.fr", Email_Statut="Nominatif (dirigeant)"), dict(ROW, Email="n@x.fr", Email_Statut="Nominatif"),
            dict(ROW, Email="d2@x.fr", Email_Statut="Nominatif (dirigeant)")]
    ordered = sorted(st.eligible(rows, set()), key=lambda r: st.STATUS_ORDER.get(r["Email_Statut"], 9))
    assert [r["Email"] for r in ordered] == ["d1@x.fr", "d2@x.fr", "n@x.fr", "g@x.fr", "p@x.fr"]


def test_already_sent_reads_brevo_and_stops_if_unreadable(monkeypatch):
    calls = []

    def fake_api(method, path, key, body=None):
        calls.append(path)
        return 200, {"events": [{"email": "A@x.fr"}, {"email": "b@x.fr"}, {"email": ""}]}
    monkeypatch.setattr(st, "api", fake_api)
    assert st.already_sent("k") == {"a@x.fr", "b@x.fr"} and "tags=tce-mail1" in calls[0]
    monkeypatch.setattr(st, "api", lambda *a, **k: (500, {}))
    import pytest
    with pytest.raises(SystemExit):
        st.already_sent("k")


def test_architects_and_non_works_firms_left_out():
    assert st.does_works({"Codes_NAF": "43.22B"}) and st.does_works({"Codes_NAF": "41.20A, 71.11Z"})
    assert not st.does_works({"Codes_NAF": "71.11Z"}) and not st.does_works({"Codes_NAF": "46.74B"})
    assert st.does_works(None) and st.does_works({"Codes_NAF": ""})
    rows = [dict(ROW, Email="a@x.fr", Entreprise="ARCHI"), dict(ROW, Email="b@x.fr", Entreprise="BATI")]
    firms = {"ARCHI": {"Codes_NAF": "71.11Z"}, "BATI": {"Codes_NAF": "43.99C"}}
    assert [r["Email"] for r in st.eligible(rows, set(), firms)] == ["b@x.fr"]
