import pytest
from fastapi.testclient import TestClient

from api import accounts, main
from api.auth import User, current_user


class Store:
    def __init__(self):
        self.profiles = {"boss": {"id": "boss", "is_admin": True}, "agent": {"id": "agent", "email": "a@x.fr"}}
        self.leads = [{"id": "l1", "assigned_user_id": "agent", "status": "new", "city": "Lille"},
                      {"id": "l2", "assigned_user_id": None, "status": "new", "city": "Lillers"}]

    async def get_profile(self, uid):
        return self.profiles.get(uid)

    async def all_estimate_leads(self):
        return [dict(l) for l in self.leads]

    async def profile_emails(self, ids):
        return {i: self.profiles[i].get("email") for i in ids}

    async def admin_update_estimate_lead(self, lead_id, fields):
        hits = [l for l in self.leads if l["id"] == lead_id]
        for l in hits:
            l.update(fields)
        return hits


@pytest.fixture
def client():
    store = Store()
    main.app.dependency_overrides[accounts.store_dep] = lambda: store
    yield TestClient(main.app), store
    main.app.dependency_overrides.clear()


def as_user(uid):
    main.app.dependency_overrides[current_user] = lambda: User(id=uid)


def test_admin_sees_every_request_with_its_advisor(client):
    c, _ = client
    as_user("boss")
    leads = c.get("/api/admin/estimate-leads").json()["leads"]
    assert [(l["id"], l["advisor"]) for l in leads] == [("l1", "a@x.fr"), ("l2", None)]


def test_admin_updates_the_status(client):
    c, store = client
    as_user("boss")
    assert c.patch("/api/admin/estimate-leads/l2", json={"status": "contacted"}).status_code == 200
    assert store.leads[1]["status"] == "contacted"
    assert c.patch("/api/admin/estimate-leads/zz", json={"status": "closed"}).status_code == 404
    assert c.patch("/api/admin/estimate-leads/l2", json={"status": "bogus"}).status_code == 422


def test_other_users_are_refused(client):
    c, _ = client
    as_user("agent")
    assert c.get("/api/admin/estimate-leads").status_code == 403
    assert c.patch("/api/admin/estimate-leads/l1", json={"status": "closed"}).status_code == 403
