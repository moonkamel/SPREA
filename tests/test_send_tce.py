import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "campaign"))
import send_tce as st  # noqa: E402

ROW = {"Score": "9.5", "Entreprise": "NORD BATI CONSTRUCTION", "Dirigeant": "François Fernand Paul Busato",
       "Email": "contact@nordbati.com", "Email_Statut": "Générique", "Distance_km": "2.2",
       "Immeuble_Adresse": "8 Rue Philippe Lebon 59100 Roubaix", "Logements": "16", "Surface_m2": "792", "DPE": "F",
       "Date_DPE": "2025-09-16", "SCI_Nom": "SCI LEBON", "SCI_Gerant": "Jean Dupont (Gérant)", "Lien_Dossier": "https://x/d?t=1"}
FIRM = {"Adresse": "159 TER RUE JOUFFROY, 59100 ROUBAIX"}


def test_mail_states_the_share_of_fg_dwellings_and_names_the_towns():
    m = st.compose(ROW, FIRM, {"nb_log": 16, "dpe_fg": 2, "dpe_count": 16}, True)
    assert m["subject"] == "Opportunité : Immeuble de 792 m² classé F à Roubaix"
    t = m["text"]
    assert t.startswith("Bonjour François,") and "NORD BATI" not in t and "Nord Bati Construction" in t
    assert "ADEME, DVF" not in t and "à l'intelligence artificielle." in t
    assert "secteur de Roubaix" in t and "2 km de votre entreprise" in t
    assert ("Les DPE publiés pour cet immeuble de 16 logements le classent F (septembre 2025) : 2 de ses 16 "
            "logements sont classés F ou G.") in t
    assert "Les 16 logements" not in t and "(la SCI Lebon)" in t
    assert "décote actuelle du bien et sa valeur après rénovation" in t and "99 € HT" in t
    assert "https://x/d?t=1" in m["html"] and "STOP" in m["html"]


def test_all_dwellings_and_no_value_in_pdf():
    m = st.compose(dict(ROW, DPE="G", SCI_Nom="JOLETA"), FIRM, {"nb_log": 16, "dpe_fg": 16, "dpe_count": 16}, False)
    assert "Les 16 logements de cet immeuble sont classés F ou G (septembre 2025)." in m["text"]
    assert "depuis le 1er janvier 2025" in m["text"] and "(la société Joleta)" in m["text"]
    assert "décote" not in m["text"]


def test_eligible_skips_bad_addresses_liquidations_duplicates_and_written():
    rows = [dict(ROW, Email="a@x.fr"), dict(ROW, Email="a@x.fr"), dict(ROW, Email=""),
            dict(ROW, Email="b@x.fr", Email_Statut="À éviter (service interne)"),
            dict(ROW, Email="c@x.fr", SCI_Gerant="Me X (Liquidateur)"), dict(ROW, Email="d@x.fr"),
            dict(ROW, Email="e@x.fr")]
    assert [r["Email"] for r in st.eligible(rows, {"d@x.fr"})] == ["a@x.fr", "e@x.fr"]


def test_first_name_needs_a_full_name():
    assert st.first_name("Grand") == "" and st.first_name("Marie Durand") == "Marie"
    assert st.town("22 RUE X, 59400 CAMBRAI CEDEX") == "Cambrai"


def test_only_some_dwellings_diagnosed_and_acronyms():
    m = st.compose(dict(ROW, DPE="G", SCI_Nom="JJM LIVE TOGETHER"), FIRM, {"nb_log": 10, "dpe_fg": 2, "dpe_count": 3}, True)
    assert "le classent G (septembre 2025) : 2 des 3 logements diagnostiqués sont classés F ou G." in m["text"]
    assert "(la société JJM Live Together)" in m["text"]


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
