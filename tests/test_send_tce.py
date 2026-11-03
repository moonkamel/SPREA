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
    m = st.compose(ROW, FIRM, {"nb_log": 16, "dpe_fg": 2}, True)
    assert m["subject"] == "Opportunité : Immeuble de 792 m² classé F à Roubaix"
    t = m["text"]
    assert t.startswith("Bonjour François,") and "NORD BATI" not in t and "Nord Bati Construction" in t
    assert "secteur de Roubaix" in t and "2 km de votre entreprise" in t
    assert "classé F au DPE de septembre 2025, et 2 de ses 16 logements sont classés F ou G" in t
    assert "Les 16 logements" not in t and "(la SCI Lebon)" in t
    assert "décote actuelle du bien et sa valeur après rénovation" in t and "99 € HT" in t
    assert "https://x/d?t=1" in m["html"] and "STOP" in m["html"]


def test_all_dwellings_and_no_value_in_pdf():
    m = st.compose(dict(ROW, DPE="G", SCI_Nom="JOLETA"), FIRM, {"nb_log": 16, "dpe_fg": 16}, False)
    assert "Les 16 logements de cet immeuble sont classés G" in m["text"]
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
