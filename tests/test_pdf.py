import io

import pdfplumber

from api.accounts import build_report_data
from api.pdf_service import format_narrative, pdf_service
from api.simulation import SimulationInput

PROP = {"surface": 85, "initial_cep": 385, "ges_value": 62, "building_type": "maison", "postcode": "59000",
        "construction_year": 1962, "heating_energy": "Gaz naturel"}


def pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def report(meta=None, narrative=None, **sim):
    data = build_report_data(meta or {"address": "1 rue de l'Église, Lille", "dpe_date": "2024-11-03"},
                             SimulationInput(property=PROP, **sim))
    if narrative is not None:
        data["ai_narrative"] = narrative
    return data


def test_report_contains_key_figures_with_french_characters():
    data = report(works=["roof", "iti", "pac_air_eau"], income_level="modeste",
                  narrative="## L'analyse\nUn logement économe & confortable.")
    text = pdf_text(pdf_service.generate(data))
    assert "1 rue de l'Église, Lille" in text
    assert "Reste à charge" in text and "€" in text
    assert "Prochaines étapes" in text
    assert "DPE du 03/11/2024" in text
    assert "économe & confortable" in text


def test_markup_in_external_text_is_escaped():
    data = report({"address": "<b>12 & 14</b> rue <script>"}, narrative="Texte <i>non fermé & **gras**")
    text = pdf_text(pdf_service.generate(data))
    assert "<b>12 & 14</b> rue <script>" in text


def test_report_without_works_or_narrative():
    pdf = pdf_service.generate(report())
    assert pdf.startswith(b"%PDF")


def test_investor_section_only_for_investors():
    owner = pdf_text(pdf_service.generate(report(works=["roof"])))
    investor = pdf_text(pdf_service.generate(report(works=["roof"], is_investor=True, monthly_rent=900, purchase_price=150000)))
    assert "rentabilité locative" not in owner
    assert "rentabilité locative" in investor


def test_narrative_headings_are_detected():
    paragraphs = format_narrative("**La stratégie**\nCommencez par la toiture.\n\n# Analyse\nTexte suivi.")
    assert [p.style.name for p in paragraphs] == ["narrative_h", "narrative", "narrative_h", "narrative"]
