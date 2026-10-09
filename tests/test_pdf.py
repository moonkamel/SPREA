import io

import pdfplumber

from api.ai_service import fallback_analysis
from api.pdf_service import pdf_service
from api.report_content import build_report, display_address, facts_for_writer
from api.simulation import SimulationInput

PROP = {"surface": 85, "initial_cep": 385, "ges_value": 62, "building_type": "maison", "postcode": "59000",
        "construction_year": 1962, "heating_energy": "Gaz naturel"}
META = {"address": "1 rue de l'Église", "city": "Lille", "postcode": "59000", "dpe_date": "2024-11-03",
        "details": {"ventilation": "Ventilation par ouverture des fenêtres"}}


def pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def render(meta=None, analysis=None, **sim):
    content = build_report(meta or META, SimulationInput(property=PROP, **sim))
    analysis = analysis or fallback_analysis(facts_for_writer(content))
    return pdf_text(pdf_service.generate(content, analysis))


def test_report_contains_key_figures_with_french_characters():
    text = render(works=["roof", "iti", "pac_air_eau"], income_level="modeste")
    assert "1 rue de l'Église" in text and "59000 Lille" in text
    assert "Reste à charge" in text and "€" in text
    assert "DPE du 03/11/2024" in text
    for title in ("Notre analyse", "Où part la chaleur", "Votre facture par usage", "Cadre réglementaire",
                  "Le programme de travaux", "Le plan de financement", "Calendrier et prochaines étapes",
                  "Méthode et hypothèses"):
        assert title in text
    assert "Ventilation par ouverture des fenêtres" in text
    assert "barème MaPrimeRénov' en vigueur au 1er septembre 2026" in text
    # Estimates are shown as ranges
    assert "entre" in text and " à " in text


def test_rental_wording():
    text = render(works=["roof", "iti", "pac_air_eau"])
    assert "Louable sans limite de date" in text
    assert "de nouveau louable" not in text


def test_markup_in_external_text_is_escaped():
    meta = {**META, "address": "<b>12 & 14</b> rue <script>"}
    analysis = {k: "Texte <i>non fermé & gras" for k in ("verdict", "diagnostic", "strategie", "financement", "profil")}
    analysis["vigilance"] = ["Point <b> & suivant", "Autre point à vérifier"]
    text = render(meta, analysis)
    assert "<b>12 & 14</b> rue <script>" in text
    assert "Texte <i>non fermé & gras" in text


def test_report_without_works():
    content = build_report(META, SimulationInput(property=PROP))
    pdf = pdf_service.generate(content, fallback_analysis(facts_for_writer(content)))
    assert pdf.startswith(b"%PDF")


def test_investor_section_only_for_investors():
    owner = render(works=["roof"])
    investor = render(works=["roof"], is_investor=True, monthly_rent=900, purchase_price=150000)
    assert "rentabilité locative" not in owner
    assert "rentabilité locative" in investor
    assert "Pour un bailleur" in investor


def test_uppercase_ademe_address_is_prettified():
    a = display_address("43 RUE BRULE MAISON", "59000", "Lille")
    assert a["full"] == "43 Rue Brule Maison, 59000 Lille"
    assert display_address("12 AVENUE DE L'EGLISE", None, None)["full"] == "12 Avenue de l'Eglise"
    # Postcode already in the raw address
    assert display_address("3 rue X 59000 Lille", "59000", "Lille")["full"] == "3 rue X 59000 Lille"


def test_rge_companies_section():
    content = build_report(META, SimulationInput(property=PROP, works=["roof", "pac_air_eau"]))
    company = {"name": "Isol'Nord <SAS>", "city": "Lille", "distance_km": 2.4, "phone": "03 20 00 00 00", "website": None}
    content["rge"] = {"works": {"roof": [company], "pac_air_eau": []}, "global": [], "audit": [dict(company, name="Audit Plus")]}
    text = pdf_text(pdf_service.generate(content, fallback_analysis(facts_for_writer(content))))
    assert "annuaire public" in text and "Isol'Nord <SAS>" in text and "2,4" in text and "Audit Plus" in text
    # No companies found: no section
    content["rge"] = None
    assert "annuaire public" not in pdf_text(pdf_service.generate(content, fallback_analysis(facts_for_writer(content))))


def test_building_sheet_section():
    from api.immeuble import build_sheet
    from tests.test_immeuble import APT, BUILDING, COPRO, TODAY, flat
    content = build_report(META, SimulationInput(property=PROP, works=["roof"]))
    content["immeuble"] = build_sheet(APT, [BUILDING, flat(1, "E", 1)], COPRO, "immat", TODAY)
    out = pdf_text(pdf_service.generate(content, fallback_analysis(facts_for_writer(content))))
    assert "L'immeuble et ses travaux" in out and "Résidence Meurein" in out and "Syndic du Nord" in out
    assert "Quote-part" in out and "plan pluriannuel" in out
    content["immeuble"] = None
    assert "Quote-part" not in pdf_text(pdf_service.generate(content, fallback_analysis(facts_for_writer(content))))
