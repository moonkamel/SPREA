import json

import httpx
import pytest

from api.store import SupabaseStore


def make_store(handler):
    return SupabaseStore("https://proj.supabase.co", "service-key", transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_archive_rows_share_the_same_columns():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["prefer"] = request.headers["prefer"]
        seen["rows"] = json.loads(request.content)
        return httpx.Response(201)

    await make_store(handler).archive_purchases([
        {"kind": "report", "stripe_session_id": "cs_1", "amount_paid": 3900},
        {"kind": "subscription", "subscription_id": "sub_1"},
    ])
    assert seen["url"].startswith("https://proj.supabase.co/rest/v1/purchase_archive")
    assert "on_conflict=stripe_session_id" in seen["url"]
    assert seen["prefer"] == "resolution=ignore-duplicates"
    assert {tuple(sorted(r)) for r in seen["rows"]} == {("amount_paid", "kind", "stripe_session_id", "subscription_id")}


@pytest.mark.anyio
async def test_delete_user_calls_auth_admin_api():
    seen = {}

    def handler(request):
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={})

    await make_store(handler).delete_user("uid-1")
    assert seen == {"method": "DELETE", "url": "https://proj.supabase.co/auth/v1/admin/users/uid-1",
                    "auth": "Bearer service-key"}


@pytest.mark.anyio
async def test_delete_user_tolerates_already_deleted_but_not_errors():
    await make_store(lambda r: httpx.Response(404)).delete_user("uid")
    with pytest.raises(httpx.HTTPStatusError):
        await make_store(lambda r: httpx.Response(500)).delete_user("uid")


@pytest.fixture
def anyio_backend():
    return "asyncio"
