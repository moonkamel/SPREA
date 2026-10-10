import asyncio
import base64
from datetime import date, datetime, timedelta, timezone

from api import claude, copro_docs, copro_docs_pdf
from tests import claude_mock
from tests.test_accounts import ALICE, BOB, env, make_pro  # noqa: F401 (fixture)

PDF = b"%PDF-1.4 fake minutes"
RESULT = {
    "copropriete": {"nom": "Résidence du Beffroi", "adresse": "12 Rue Nationale 59000 Lille", "syndic": "Foncia Lille", "lots": "24"},
    "documents": [{"fichier": "PV_AG_2025.pdf", "nature": "PV d'assemblée générale", "date": "12/05/2025", "lisible": True}],
    "synthese": "Copropriété de 24 lots bien tenue. Ravalement voté pour 180 000 €, appels de fonds en 2026.",
    "niveau_risque": "modéré",
    "travaux_votes": [{"objet": "Ravalement des façades", "montant": 180000, "date_vote": "12/05/2025",
                       "appels_de_fonds": "50 % au 01/01/2026, 50 % au 01/07/2026", "etat": "voté", "source": "PV d'AG du 12/05/2025, p. 4"}],
    "travaux_a_venir": [{"objet": "Remplacement de l'ascenseur", "estimation": "90 000 €", "horizon": "2028", "source": "p. 6"}],
    "procedures": [{"objet": "Recouvrement de charges", "role_syndicat": "demandeur", "montant": 8200, "etat": "assignation délivrée", "source": "p. 5"}],
    "finances": {"budget_previsionnel": 52000, "fonds_travaux": 14000, "impayes_coproprietaires": 8200, "dettes_fournisseurs": None,
                 "commentaire": "Trésorerie tendue.", "source": "p. 2"},
    "obligations": {"plan_pluriannuel": "Projet de PPT voté le 12/05/2025", "dtg": None, "dpe_collectif": "Voté, à réaliser en 2026"},
    "vie_copropriete": ["Changement de syndic en 2024."],
    "vigilance": [{"niveau": "info", "point": "Fonds de travaux de 14 000 €.", "source": "p. 2"},
                  {"niveau": "alerte", "point": "Ravalement de 180 000 € voté : appels de fonds en 2026.", "source": "p. 4"}],
    "questions_syndic": ["Montant de la quote-part du lot pour le ravalement ?"],
    "documents_manquants": ["PV d'AG de 2024"],
}


def add_docs(store):
    store.analyses, store.objects, store.signed = {}, {}, []

    async def create(row):
        full = {"status": "uploading", "result": None, "created_at": datetime.now(timezone.utc).isoformat(), **row}
        store.analyses[row["id"]] = full
        return full

    async def get(aid):
        return store.analyses.get(aid)

    async def update(aid, fields):
        store.analyses[aid].update(fields)

    async def list_(user_id, since=None):
        rows = [dict(r, synthese=(r.get("result") or {}).get("synthese"), niveau_risque=(r.get("result") or {}).get("niveau_risque"))
                for r in store.analyses.values() if r["user_id"] == user_id and (not since or r["created_at"] >= since)]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    async def delete(aid):
        store.analyses.pop(aid, None)

    async def stale(before):
        return [r for r in store.analyses.values() if r["status"] == "uploading" and r["created_at"] < before]

    async def signed(bucket, path):
        store.signed.append(path)
        return f"https://supabase.test/storage/v1/object/upload/sign/{bucket}/{path}?token=t"

    async def download(bucket, path):
        return store.objects.get(path)

    async def delete_objects(bucket, paths):
        for p in paths:
            store.objects.pop(p, None)

    (store.create_doc_analysis, store.get_doc_analysis, store.update_doc_analysis, store.list_doc_analyses,
     store.delete_doc_analysis, store.stale_doc_uploads, store.signed_upload_url, store.download_object,
     store.delete_objects) = create, get, update, list_, delete, stale, signed, download, delete_objects


FILES = {"files": [{"name": "PV AG 2025.pdf", "size": len(PDF), "type": "application/pdf"},
                   {"name": "carnet.jpg", "size": 3, "type": "image/jpeg"}], "address": "12 Rue Nationale 59000 Lille"}


def upload_all(store, res):
    for path in store.signed[-len(res["uploads"]):]:
        store.objects[path] = PDF if path.endswith(".pdf") or "pdf" in path.lower() else b"jpg"


def test_documents_read_by_claude_then_deleted(env, monkeypatch):
    client, store, _, state = env
    add_docs(store)
    mock = claude_mock.install(monkeypatch, lambda body: RESULT)
    assert client.post("/api/copro-docs/uploads", json=FILES).status_code == 402
    make_pro(store)
    res = client.post("/api/copro-docs/uploads", json=FILES).json()
    assert len(res["uploads"]) == 2 and res["uploads"][0]["url"].startswith("https://supabase.test/")
    # Not uploaded yet
    assert client.post(f"/api/copro-docs/{res['id']}/analyze").status_code == 400
    upload_all(store, res)

    out = client.post(f"/api/copro-docs/{res['id']}/analyze").json()
    assert out["status"] == "done" and out["niveau_risque"] == "modéré"
    # Alerts first
    assert out["result"]["vigilance"][0]["niveau"] == "alerte"
    body = mock.requests[0]["body"]
    assert body["model"] == claude.MODEL and body["output_config"]["format"]["type"] == "json_schema"
    blocks = body["messages"][0]["content"]
    assert blocks[0]["type"] == "document" and base64.b64decode(blocks[0]["source"]["data"]) == PDF
    assert any(b["type"] == "image" and b["source"]["media_type"] == "image/jpeg" for b in blocks)
    assert "12 Rue Nationale" in blocks[-1]["text"]
    # Files deleted, paths forgotten, summary kept
    assert not store.objects
    assert "path" not in store.analyses[res["id"]]["files"][0]
    listing = client.get("/api/copro-docs").json()
    assert listing["analyses"][0]["synthese"].startswith("Copropriété de 24 lots") and listing["quota"]["used"] == 1
    # Analysing again returns the stored result, without a new call
    assert client.post(f"/api/copro-docs/{res['id']}/analyze").json()["status"] == "done"
    assert len(mock.requests) == 1
    pdf = client.get(f"/api/copro-docs/{res['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "Synthese_copropriete_12_Rue_Nationale" in pdf.headers["content-disposition"]

    # Someone else's analysis
    state["user"] = BOB
    make_pro(store, BOB)
    assert client.get(f"/api/copro-docs/{res['id']}").status_code == 404
    state["user"] = ALICE
    assert client.delete(f"/api/copro-docs/{res['id']}").json() == {"deleted": True}
    assert not store.analyses


def test_upload_checks_and_quota(env, monkeypatch):
    client, store, _, _ = env
    add_docs(store)
    make_pro(store)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post("/api/copro-docs/uploads", json=FILES).status_code == 503
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    bad = {"files": [{"name": "acte.docx", "size": 10, "type": "application/msword"}]}
    assert "PDF" in client.post("/api/copro-docs/uploads", json=bad).json()["detail"]
    big = {"files": [{"name": f"pv{i}.pdf", "size": 9 * 1024 * 1024, "type": "application/pdf"} for i in range(3)]}
    assert client.post("/api/copro-docs/uploads", json=big).status_code == 400
    monkeypatch.setattr(copro_docs, "MONTHLY_QUOTA", 1)
    assert client.post("/api/copro-docs/uploads", json=FILES).status_code == 200
    assert client.post("/api/copro-docs/uploads", json=FILES).status_code == 429


def test_failed_analysis_deletes_the_files(env, monkeypatch):
    client, store, _, _ = env
    add_docs(store)
    make_pro(store)
    claude_mock.install(monkeypatch, lambda body: RESULT, status=529)
    res = client.post("/api/copro-docs/uploads", json=FILES).json()
    upload_all(store, res)
    assert client.post(f"/api/copro-docs/{res['id']}/analyze").status_code == 502
    assert not store.objects and store.analyses[res["id"]]["status"] == "failed"
    # A failed analysis does not count in the quota
    assert client.get("/api/copro-docs").json()["quota"]["used"] == 0


def test_stale_uploads_are_purged(env):
    _, store, _, _ = env
    add_docs(store)
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    store.analyses["a"] = {"id": "a", "user_id": ALICE.id, "status": "uploading", "created_at": old,
                           "files": [{"name": "x.pdf", "size": 1, "type": "application/pdf", "path": "u/a/0-x.pdf"}]}
    store.objects["u/a/0-x.pdf"] = PDF
    assert asyncio.run(copro_docs.purge_stale_uploads(store)) == 1
    assert not store.objects and store.analyses["a"]["status"] == "failed"


def test_schema_is_strict_and_pdf_renders_sparse_results():
    def closed(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
            for v in s["properties"].values():
                closed(v)
        for v in s.get("anyOf", []):
            closed(v)
        if isinstance(s.get("items"), dict):
            closed(s["items"])
    closed(copro_docs.SCHEMA)
    sparse = {"result": {**{k: [] for k in ("documents", "travaux_votes", "travaux_a_venir", "procedures", "vie_copropriete",
                                            "vigilance", "questions_syndic", "documents_manquants")},
                         "copropriete": {}, "finances": {}, "obligations": {}, "synthese": "Peu d'informations.", "niveau_risque": "faible"}}
    assert copro_docs_pdf.generate(sparse, {}, date(2026, 10, 10))[:4] == b"%PDF"


def test_storage_calls():
    """Live check: Storage answered 400 to an empty JSON body (signed upload URL)."""
    import httpx
    from api.store import SupabaseStore
    seen = []

    def handler(request):
        seen.append(request)
        if "/upload/sign/" in request.url.path:
            if not request.content:
                return httpx.Response(400, json={"error": "Body cannot be empty"})
            return httpx.Response(200, json={"url": "/object/upload/sign/copro-docs/u/a/0-x?token=t"})
        if request.method == "DELETE":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    store = SupabaseStore("https://p.supabase.co", "sb_secret_x", transport=httpx.MockTransport(handler))
    url = asyncio.run(store.signed_upload_url("copro-docs", "u/a/0-x"))
    assert url == "https://p.supabase.co/storage/v1/object/upload/sign/copro-docs/u/a/0-x?token=t"
    assert asyncio.run(store.download_object("copro-docs", "u/a/0-x")) is None
    asyncio.run(store.delete_objects("copro-docs", ["u/a/0-x"]))
    assert seen[-1].method == "DELETE" and b"prefixes" in seen[-1].content
