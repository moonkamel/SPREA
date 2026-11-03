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
    assert m["subject"] == "Opportunité : Immeuble de 792\u00a0m² à Roubaix, 2 logements classés F ou G"
    t = m["text"]
    assert t.startswith("Bonjour François,") and "NORD BATI" not in t and "Nord Bati Construction" in t
    assert "ADEME, DVF" not in t and "à l'intelligence artificielle." in t
    assert "secteur de Roubaix" in t and "2 km de votre entreprise" in t
    assert "2 des 16 logements de cet immeuble sont classés F ou G (DPE de septembre 2025)." in t
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


def test_large_works_only_when_most_dwellings_are_f_or_g():
    small = st.compose(dict(ROW, Surface_m2="187"), FIRM, {"nb_log": 3, "dpe_fg": 1, "dpe_count": 3}, True)["text"]
    assert "des travaux seront nécessaires pour continuer à louer" in small and "envergure" not in small
    big = st.compose(ROW, FIRM, {"nb_log": 10, "dpe_fg": 2, "dpe_count": 3}, True)["text"]  # 2 of the 3 diagnosed
    assert "des travaux d'envergure seront nécessaires" in big
    assert st.mostly_fg({"nb_log": 16, "dpe_fg": 16, "dpe_count": 16})
    assert not st.mostly_fg({"nb_log": 16, "dpe_fg": 2, "dpe_count": 16}) and not st.mostly_fg({"nb_log": 4, "dpe_fg": None})


def test_few_fg_dwellings_never_called_a_class_for_the_building():
    m = st.compose(dict(ROW, DPE="G", Surface_m2="287"), FIRM, {"nb_log": 6, "dpe_fg": 1, "dpe_count": 6}, True)
    assert m["subject"] == "Opportunité : Immeuble de 287 m² à Roubaix, 1 logement classé F ou G"
    t = m["text"]
    assert "1 des 6 logements de cet immeuble est classé F ou G (DPE de septembre 2025)." in t
    assert "le classent" not in t and "envergure" not in t
    m = st.compose(dict(ROW, DPE="G"), FIRM, {"nb_log": 10, "dpe_fg": 1, "dpe_count": 4}, True)
    assert "1 des 4 logements diagnostiqués de cet immeuble de 10 logements est classé F ou G" in m["text"]


def test_order_puts_mostly_fg_buildings_first():
    rows = [dict(ROW, Email="a@x.fr", Email_Statut="Nominatif (dirigeant)", Lien_Dossier="L1"),
            dict(ROW, Email="b@x.fr", Email_Statut="Générique", Lien_Dossier="L2"),
            dict(ROW, Email="c@x.fr", Email_Statut="Nominatif (dirigeant)", Lien_Dossier="L2")]
    by_link = {"L1": {"id": "b1"}, "L2": {"id": "b2"}}
    counts = {"b1": {"nb_log": 6, "dpe_fg": 1, "dpe_count": 6}, "b2": {"nb_log": 6, "dpe_fg": 4, "dpe_count": 6}}
    assert [r["Email"] for r in st.order(rows, by_link, counts)] == ["c@x.fr", "b@x.fr", "a@x.fr"]


def test_architects_and_non_works_firms_left_out():
    assert st.does_works({"Codes_NAF": "43.22B"}) and st.does_works({"Codes_NAF": "41.20A, 71.11Z"})
    assert not st.does_works({"Codes_NAF": "71.11Z"}) and not st.does_works({"Codes_NAF": "46.74B"})
    assert st.does_works(None) and st.does_works({"Codes_NAF": ""})
    rows = [dict(ROW, Email="a@x.fr", Entreprise="ARCHI"), dict(ROW, Email="b@x.fr", Entreprise="BATI")]
    firms = {"ARCHI": {"Codes_NAF": "71.11Z"}, "BATI": {"Codes_NAF": "43.99C"}}
    assert [r["Email"] for r in st.eligible(rows, set(), firms)] == ["b@x.fr"]
