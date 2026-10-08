import asyncio

import httpx
import pytest

from api import prospection
from api.prospection import AreaTooLarge, group_by_address, parse_bbox


def dpe(number, label, date, surface=40.0, ban="59350_1143_00001", detail="RDC", kind="appartement"):
    return {"numero_dpe": number, "etiquette_dpe": label, "date_etablissement_dpe": date, "type_batiment": kind,
            "surface_habitable_logement": surface, "adresse_ban": "1 Rue des Brigittines 59800 Lille",
            "identifiant_ban": ban, "code_insee_ban": "59350", "_geopoint": "50.6333,3.0692",
            "periode_construction": "avant 1948", "complement_adresse_logement": detail}


def test_bbox_limits():
    assert parse_bbox("3.05,50.63,3.07,50.64") == (3.05, 50.63, 3.07, 50.64)
    with pytest.raises(AreaTooLarge):
        parse_bbox("2.9,50.5,3.2,50.7")
    with pytest.raises(ValueError):
        parse_bbox("abc")


def test_group_by_address_keeps_latest_dpe_per_dwelling():
    rows = [
        dpe("A1", "G", "2023-01-01"),
        dpe("A2", "F", "2025-05-01"),                       # same flat, newer DPE
        dpe("B1", "G", "2024-02-01", surface=65, detail="2e étage"),
        dpe("C1", "F", "2024-02-01", ban="59350_2778_00012"),
    ]
    out = group_by_address(rows, {"F", "G"})
    assert len(out) == 2
    first = out[0]
    assert first["worst"] == "G" and [d["number"] for d in first["dpe"]] == ["B1", "A2"]
    assert out[1]["worst"] == "F"


def test_search_queries_ademe_with_area_and_labels():
    prospection._cache.clear()
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"total": 1, "results": [dpe("A1", "G", "2024-01-01")]})

    res = asyncio.run(prospection.search("3.05,50.63,3.07,50.64", ["G", "X"], "maison", 2023, transport=httpx.MockTransport(handler)))
    assert seen["bbox"] == "3.05,50.63,3.07,50.64"
    assert seen["qs"] == "etiquette_dpe:(G) AND type_batiment:maison AND date_etablissement_dpe:[2023-01-01 TO *]"
    assert res["dwellings"] == 1 and not res["truncated"]


def test_real_ademe_types_numeric_floor_and_missing_fields():
    # As returned by the ADEME API: floor as a number, no complement, building DPE without surface
    rows = [
        {**dpe("A1", "F", "2026-01-12", detail=None), "numero_etage_appartement": 2},
        {**dpe("A2", "G", "2026-01-12", detail=None), "numero_etage_appartement": 0},
        {**dpe("B1", "G", "2026-01-06", ban="59350_7189_00020", detail=None, kind="immeuble"),
         "surface_habitable_logement": None, "numero_etage_appartement": 0},
    ]
    out = group_by_address(rows, {"F", "G"})
    details = sorted(str(d["detail"]) for a in out for d in a["dpe"])
    assert details == ["2e étage", "None", "RDC"]
