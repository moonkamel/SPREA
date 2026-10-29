import asyncio
from datetime import date

import httpx

from api import listings

TODAY = date(2026, 10, 30)


def prop(uuid, created, lat=50.63, lon=3.06, publishers=(0,), desc="Maison lumineuse", events=(), price=200000):
    return {"uuid": uuid, "createdAt": created, "locations": {"lat": lat, "lon": lon}, "price": price, "surface": 90,
            "pricePerMeter": price / 90, "propertyType": 1, "room": 4, "publisherTypes": list(publishers),
            "title": "Maison 4 pièces", "description": desc, "pictures": ["https://x/1.jpg"],
            "city": {"name": "Lille", "zipcode": "59000", "insee": "59350"},
            "adverts": [{"createdAt": created, "updatedAt": "2026-10-20T10:00:00+02:00", "url": "https://portail/annonce",
                         "publisher": {"name": "Portail", "type": publishers[0]}, "energy": {"category": "F"},
                         "events": list(events), "contact": {"phone": "0600000000"}}]}


def test_stale_listings(monkeypatch):
    monkeypatch.setenv("STREAM_ESTATE_API_KEY", "test")
    listings._cache.clear()
    seen = {}
    members = [
        prop("a", "2026-05-01T10:00:00+02:00", events=[{"fieldName": "price", "percentVariation": -5, "fieldOldValue": "210000",
                                                         "createdAt": "2026-08-01T10:00:00+02:00"}]),
        prop("b", "2026-07-15T10:00:00+02:00", publishers=(1,)),
        prop("c", "2026-04-01T10:00:00+02:00", desc="Vente directe, agences s'abstenir"),
        prop("d", "2026-03-01T10:00:00+02:00", lat=51.5),
    ]

    def handler(request):
        seen["params"] = request.url.params
        seen["key"] = request.headers.get("X-API-KEY")
        return httpx.Response(200, json={"hydra:member": members, "hydra:totalItems": len(members)})
    res = asyncio.run(listings.stale_listings("3.05,50.62,3.07,50.64", 60, "anciennes", False, TODAY, httpx.MockTransport(handler)))
    assert seen["key"] == "test" and seen["params"]["toDate"] == "2026-08-31" and seen["params"]["transactionType"] == "0"
    ids = [i["id"] for i in res["items"]]
    assert ids == ["a", "b"] and res["hidden_no_agency"] == 1
    a = res["items"][0]
    assert a["days_online"] == 182 and a["drops"] == 1 and a["drop_pct"] == -4.8 and a["private"] and a["energy"] == "F"
    assert "contact" not in a and "phone" not in str(a)
    assert not res["items"][1]["private"]
