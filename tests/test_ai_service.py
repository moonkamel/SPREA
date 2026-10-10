import asyncio
import json


from tests import claude_mock
from api.ai_service import AIService, NARRATIVE_VERSION, parse_stored, validate
from api.report_content import build_report, facts_for_writer
from api.simulation import SimulationInput

PROP = {"surface": 85, "initial_cep": 385, "ges_value": 62, "building_type": "maison", "postcode": "59000",
        "construction_year": 1962, "heating_energy": "Gaz naturel"}

GOOD = {
    "verdict": "Passer de F à C coûte environ 18 000 € après aides.",
    "diagnostic": "Cette maison de 85 m² des années 1960 perd surtout sa chaleur par la toiture et les murs.",
    "strategie": "Commencez par la toiture, puis les murs, avant de remplacer la chaudière au gaz.",
    "financement": "Le reste à charge est estimé entre 17 000 € et 21 000 € avec l'aide de l'Anah.",
    "profil": "Pour vous, la facture baisse d'environ 1 900 € par an et les pièces sont moins froides.",
    "vigilance": ["Dimensionnez la pompe à chaleur après l'isolation.", "Gardez toutes les factures des artisans RGE."],
}


def facts():
    content = build_report({"address": "1 rue de l'Église", "city": "Lille"},
                           SimulationInput(property=PROP, works=["roof", "iti", "pac_air_eau"]))
    return facts_for_writer(content)


def test_facts_never_contain_the_street_address():
    data = json.dumps(facts(), ensure_ascii=False)
    assert "Église" not in data
    assert "Lille" in data


def test_without_key_uses_rules(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = asyncio.run(AIService().write_analysis(facts()))
    assert res["source"] == "rules"
    assert validate(res["sections"])
    assert parse_stored(json.dumps(res)) is None


def test_claude_output_is_used(monkeypatch):
    mock = claude_mock.install(monkeypatch, lambda body: {**GOOD, "diagnostic": "**Gras** " + GOOD["diagnostic"]})
    res = asyncio.run(AIService().write_analysis(facts()))
    assert res["source"] == "claude"
    assert res["sections"]["diagnostic"].startswith("Gras Cette maison")
    req = mock.requests[0]
    assert req["headers"]["x-api-key"] == "sk-ant-test"
    # Structured output, no forced tool (rejected by the current models)
    assert "tool_choice" not in req["body"] and req["body"]["output_config"]["format"]["type"] == "json_schema"
    assert req["body"]["fallbacks"] == "default"
    stored = parse_stored(json.dumps(res))
    assert stored and stored["v"] == NARRATIVE_VERSION


def test_api_error_falls_back_to_rules(monkeypatch):
    claude_mock.install(monkeypatch, lambda body: GOOD, status=529)
    res = asyncio.run(AIService().write_analysis(facts()))
    assert res["source"] == "rules"
    claude_mock.install(monkeypatch, lambda body: GOOD, stop_reason="refusal")
    assert asyncio.run(AIService().write_analysis(facts()))["source"] == "rules"


def test_incomplete_output_is_rejected():
    assert validate({**GOOD, "strategie": ""}) is None
    assert validate({**GOOD, "vigilance": ["court"]}) is None
    # Old plain-text narratives are regenerated
    assert parse_stored("L'analyse personnalisée n'est pas disponible") is None
