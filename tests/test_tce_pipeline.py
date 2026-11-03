import csv
import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "tce", os.path.join(os.path.dirname(__file__), "..", "scripts", "apify", "tce_pipeline.py"))
tce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tce)

# Rows in the shape of each Actor's dataset (fields of their dataset schemas)
RGE = [
    {"siren": "111111111", "siret": "11111111100011", "companyName": "Bâti Global", "postalCode": "59000",
     "fullAddress": "1 rue A 59000 Lille", "email": "a@bati.fr", "phone": "0320000000",
     "workCategories": ["Rénovation globale"], "workDomains": ["Projet complet de rénovation"],
     "qualifications": [{"certificate": "QUALIBAT-RGE"}]},
    {"siren": "222222222", "siret": "22222222200022", "companyName": "Multi Lots", "postalCode": "62000",
     "workDomains": ["Isolation des combles perdus", "Pompe à chaleur : chauffage", "Fenêtres de toit", "Ventilation mécanique"]},
    {"siren": "333333333", "siret": "33333333300033", "companyName": "Mono PAC", "postalCode": "80000",
     "workDomains": ["Pompe à chaleur : chauffage", "Chaudière bois"]},
]
NAF = [{"siren": "444444444", "name": "Gros Oeuvre Nord", "nafCode": "41.20B", "headquarters": {"postalCode": "59100"},
        "employees": {"code": "21", "label": "20 à 49 salariés"}, "latestFinances": {"revenue": 3200000}}]
SIRENS = [{"siren": "111111111", "nafCode": "43.99C", "employees": {"code": "12", "label": "20 à 49 salariés"},
           "latestFinances": {"revenue": 800000}}]
DIRECTORS = [{"siret": "11111111100011", "directorFirstName": "Marie", "directorLastName": "Durand", "email": "m@bati.fr"}]
CAPEB = [{"siret": "22222222200022", "labels": ["Éco-Artisan"], "contactName": "Paul"}]


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    runs, datasets = [], {}
    outputs = {"scrapersdelight~rge-installers-fr-scraper": RGE, "corent1robert~rge-siren-enrich": DIRECTORS,
               "corent1robert~capeb-scraper": CAPEB}

    def http(method, url, token=None, body=None, timeout=120):
        """Apify and ADEME answers, without network."""
        if "data.ademe.fr" in url:
            return {"total": 640 if "59000" in url else 60}
        if method == "POST":
            actor = url.split("/acts/")[1].split("/")[0]
            runs.append((actor, body, url))
            dataset = f"d{len(runs)}"
            datasets[dataset] = NAF if "nafCodes" in body else SIRENS if "sirens" in body else outputs[actor]
            return {"data": {"id": f"r{len(runs)}", "status": "SUCCEEDED", "defaultDatasetId": dataset}}
        if "/datasets/" in url:
            return datasets[url.split("/datasets/")[1].split("/")[0]]
        raise AssertionError(url)
    monkeypatch.setattr(tce, "http", http)
    monkeypatch.setenv("APIFY_TOKEN", "test")
    tce.main(["--out", str(tmp_path)])

    # Inputs sent to the Actors
    first = runs[0][1]
    assert first["postalPrefixes"] == ["02", "59", "60", "62", "80"] and first["oneRowPerCompany"]
    assert "maxTotalChargeUsd=5.4" in runs[0][2]
    assert runs[1][1]["labels"] == ["rge"] and runs[1][1]["nafCodes"][0] == "41.20A"
    enrich = next(b for a, b, u in runs if a == "corent1robert~rge-siren-enrich")
    assert enrich["mode"] == "sirets" and enrich["rowDepth"] == "directors" and "11111111100011" in enrich["sirets"]

    rows = list(csv.DictReader(open(tmp_path / "prospection_tce_hauts_de_france.csv", encoding="utf-8-sig"), delimiter=";"))
    by = {r["SIRET"][:9]: r for r in rows}
    # Mono-trade heat pump installer is not TCE
    assert "333333333" not in by
    g, m, e = by["111111111"], by["222222222"], by["444444444"]
    assert g["Dirigeant_Nom"] == "Marie Durand" and g["Score_Multi_Competence"] == "1" and g["Score_Proximite"] == "5"
    assert g["Score_Capacite_Chantier"] == "2"  # 20-49 employees, revenue under 1 M EUR
    assert m["Nb_Corps_Metier"] == "4" and m["Score_Multi_Competence"] == "4" and m["Eco_Artisan_CAPEB"] == "oui"
    assert e["Entreprise_Type"] == "Entreprise Générale" and e["Score_Capacite_Chantier"] == "5"
    assert [r["Score_Final"] for r in rows] == sorted([r["Score_Final"] for r in rows], key=int, reverse=True)
    # Intermediate JSON kept, and a second run reuses them without paying again
    assert (tmp_path / "1a_rge_registre.json").exists() and (tmp_path / "3_densite_fg.json").exists()
    runs.clear()
    tce.main(["--out", str(tmp_path)])
    assert runs == []


def test_budget_never_exceeded():
    b = tce.Budget(15.0)
    b.spent = 14.0
    assert b.cap_for(10000, 0.004) == 1.0
    b.spent = 14.999
    try:
        b.cap_for(10, 0.004)
        assert False
    except RuntimeError:
        pass


def test_email_status():
    st = tce.email_status
    assert st("fredericdescamps@live.fr", "Frédéric Descamps", "HOMZA SERVICES") == "Nominatif (dirigeant)"
    assert st("nadegeguiot@courtinsas.fr", "Bernard Filleur", "COURTIN") == "Nominatif"
    assert st("contact@nordbaticonstruction.com", "", "NORD BATI CONSTRUCTION") == "Générique"
    assert st("servais.compta2@groupe-sfd.com", "", "ETABLISSEMENT SERVAIS") == "À éviter (service interne)"
    assert st("rh@lepretre-energies.fr", "", "LEPRETRE ENERGIES") == "À éviter (service interne)"
    assert st("rhone.dupont@bati.fr", "", "BATI") == "Nominatif"
    assert st("maxime.leveaux@spiebatignolles.fr", "", "FARASSE FLUIDES") == "Domaine à vérifier"
    assert st("hdf-chauffage@orange.fr", "", "HDF CHAUFFAGE") == "Messagerie perso"
    # The best address wins over the first one found
    assert tce.best_email(["comptabilite@carobat.fr", "julien.guillet@carobat.fr"], "Julien Guillet", "CARO BAT", "")[0] \
        == "julien.guillet@carobat.fr"
