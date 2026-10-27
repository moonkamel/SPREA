import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api import accounts, cadastre, main

PARCEL = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[3.0601, 50.6301], [3.0603, 50.6301], [3.0603, 50.6303], [3.0601, 50.6301]]]},
          "properties": {"idu": "593500000AB0123", "numero": "0123", "section": "AB", "code_dep": "59", "code_com": "350",
                         "nom_com": "Lille", "com_abs": "000", "contenance": 245}}
FAR = {**PARCEL, "geometry": {"type": "Polygon", "coordinates": [[[3.0700, 50.6400], [3.0702, 50.6400], [3.0702, 50.6402], [3.0700, 50.6400]]]},
       "properties": {**PARCEL["properties"], "numero": "0999", "idu": "593500000AB0999"}}


@pytest.fixture
def client(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        geom = json.loads(request.url.params["geom"])
        calls.append(geom["type"])
        # The address point is on the street: only the search around it finds parcels
        if geom["type"] == "Point":
            return httpx.Response(200, json={"type": "FeatureCollection", "features": []})
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [FAR, PARCEL]})

    monkeypatch.setattr(cadastre, "TRANSPORT", httpx.MockTransport(handler))
    cadastre._cache.clear()
    main.app.dependency_overrides[accounts.subscriber_access] = lambda: None
    c = TestClient(main.app)
    c.calls = calls
    yield c
    main.app.dependency_overrides.clear()


def test_parcel_around_a_street_point_is_the_closest(client):
    r = client.get("/api/parcel", params={"lat": 50.6302, "lon": 3.0602})
    assert r.status_code == 200
    assert r.json() == {"insee": "59350", "commune": "Lille", "section": "AB", "numero": "0123", "prefixe": None,
                        "idu": "593500000AB0123", "contenance": 245}
    assert client.calls == ["Point", "Polygon"]
    # Cached
    client.get("/api/parcel", params={"lat": 50.6302, "lon": 3.0602})
    assert client.calls == ["Point", "Polygon"]


def test_parcel_needs_coordinates(client):
    assert client.get("/api/parcel", params={"lat": 200, "lon": 3}).status_code == 422
