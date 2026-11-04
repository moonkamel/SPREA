import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "apify"))
import tce_free as tf  # noqa: E402


def test_trades_from_rge_domains_and_tce():
    assert tf.trade_of("Isolation des murs par l'extérieur") == "Isolation"
    assert tf.trade_of("Fenêtres, volets, portes donnant sur l'extérieur") == "Menuiserie"
    assert tf.trade_of("Pompe à chaleur : chauffage") == "Chauffage"
    assert tf.trade_of("Panneaux solaires photovoltaïques") == "Photovoltaïque"
    assert tf.trade_of("Chauffage et/ou eau chaude solaire") == "Eau chaude sanitaire"
    assert tf.trade_of("Projet complet de rénovation") == tf.GLOBAL
    assert tf.trade_of("Audit énergétique") is None
    lines = [{"siret": "12345678900011", "nom_entreprise": "BATI X", "code_postal": "80000", "commune": "Amiens",
              "domaine": d, "email": "contact@batix.fr", "site_internet": "batix.fr"}
             for d in ("Isolation des combles perdus", "Fenêtres de toit", "Ventilation mécanique")]
    lines.append({"siret": "99999999900011", "nom_entreprise": "PAC Y", "code_postal": "60000", "domaine": "Pompe à chaleur : chauffage"})
    firms = tf.firms_from_rge(lines)
    assert set(firms) == {"123456789", "999999999"}
    assert tf.is_tce(firms["123456789"]) and not tf.is_tce(firms["999999999"])
    assert firms["123456789"]["emails"] == ["contact@batix.fr"]


def test_works_naf():
    assert tf.does_works("43.22B") and tf.does_works("41.20A") and tf.does_works("")
    assert not tf.does_works("71.11Z")
