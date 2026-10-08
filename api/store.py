"""Persistence of profiles and reports in Supabase Postgres, through its REST API
(PostgREST) with the service role key. Tables: supabase/migrations/001_accounts.sql.

The service role key bypasses row level security: it must only live on the server.
"""
import os
from typing import Any, Dict, List, Optional

import httpx


class SupabaseStore:
    def __init__(self, url: str, service_key: str, timeout: float = 10.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.auth_base = f"{url.rstrip('/')}/auth/v1"
        self.headers = {"apikey": service_key, "Content-Type": "application/json"}
        # Legacy service_role keys are JWTs and also go in Authorization. The new
        # secret keys (sb_secret_...) are not JWTs: they must only be sent as apikey.
        if service_key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {service_key}"
        self.timeout = timeout
        self.transport = transport  # Tests only

    async def _request(self, method: str, table: str, params: Optional[Dict[str, str]] = None,
                       json: Any = None, prefer: Optional[str] = None) -> List[Dict[str, Any]]:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            res = await client.request(method, f"{self.base}/{table}", params=params, json=json, headers=headers)
            res.raise_for_status()
            return res.json() if res.content else []

    async def _one(self, table: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        rows = await self._request("GET", table, params={**params, "select": "*", "limit": "1"})
        return rows[0] if rows else None

    # --- Profiles ---

    async def ensure_profile(self, user_id: str, email: Optional[str]) -> Dict[str, Any]:
        rows = await self._request(
            "POST", "profiles", params={"on_conflict": "id"}, json={"id": user_id, "email": email},
            prefer="resolution=merge-duplicates,return=representation",
        )
        return rows[0]

    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("profiles", {"id": f"eq.{user_id}"})

    async def get_profile_by_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("profiles", {"stripe_customer_id": f"eq.{customer_id}"})

    async def update_profile(self, user_id: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "profiles", params={"id": f"eq.{user_id}"}, json=fields)

    # --- Reports ---

    async def create_report(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "reports", json=row, prefer="return=representation")
        return rows[0]

    async def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("reports", {"id": f"eq.{report_id}"})

    async def update_report(self, report_id: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "reports", params={"id": f"eq.{report_id}"}, json=fields)

    async def list_reports(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "reports", params={
            "user_id": f"eq.{user_id}",
            "status": "in.(paid,included)",
            "select": "id,address,status,created_at",
            "order": "created_at.desc",
            "limit": "50",
        })

    async def paid_reports(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "reports", params={
            "user_id": f"eq.{user_id}",
            "status": "eq.paid",
            "select": "stripe_session_id,terms_version,terms_accepted_at,amount_paid,currency,paid_at",
        })

    # --- Terms acceptances (append-only) ---

    async def add_terms_acceptance(self, user_id: str, scope: str, version: str) -> Dict[str, Any]:
        rows = await self._request("POST", "terms_acceptances", json={
            "user_id": user_id, "scope": scope, "terms_version": version,
        }, prefer="return=representation")
        return rows[0]

    async def latest_terms_acceptance(self, user_id: str, scope: str) -> Optional[Dict[str, Any]]:
        rows = await self._request("GET", "terms_acceptances", params={
            "user_id": f"eq.{user_id}", "scope": f"eq.{scope}", "select": "terms_version,accepted_at",
            "order": "accepted_at.desc", "limit": "1",
        })
        return rows[0] if rows else None

    async def terms_acceptances(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "terms_acceptances", params={
            "user_id": f"eq.{user_id}", "select": "scope,terms_version,accepted_at", "order": "accepted_at.asc",
        })

    # --- Owner contact pages ---

    async def get_agent_page(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("agent_pages", {"user_id": f"eq.{user_id}"})

    async def upsert_agent_page(self, user_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "agent_pages", params={"on_conflict": "user_id"},
                                   json={**fields, "user_id": user_id, "updated_at": "now()"},
                                   prefer="resolution=merge-duplicates,return=representation")
        return rows[0]

    async def get_link(self, code: str) -> Optional[Dict[str, Any]]:
        return await self._one("prospect_links", {"code": f"eq.{code}"})

    async def get_link_for_dpe(self, user_id: str, dpe_number: str) -> Optional[Dict[str, Any]]:
        return await self._one("prospect_links", {"user_id": f"eq.{user_id}", "dpe_number": f"eq.{dpe_number}"})

    async def create_link(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "prospect_links", json=row, prefer="return=representation")
        return rows[0]

    async def update_link(self, code: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "prospect_links", params={"code": f"eq.{code}"}, json=fields)

    async def list_links(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "prospect_links", params={
            "user_id": f"eq.{user_id}", "select": "code,dpe_number,address,label,created_at,visits,last_visit_at",
            "order": "created_at.desc", "limit": "500",
        })

    async def create_lead(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "leads", json=row, prefer="return=representation")
        return rows[0]

    async def list_leads(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "leads", params={
            "user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc", "limit": "500",
        })

    async def update_lead(self, user_id: str, lead_id: str, fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        return await self._request("PATCH", "leads", params={"id": f"eq.{lead_id}", "user_id": f"eq.{user_id}"},
                                   json=fields, prefer="return=representation")

    async def delete_lead(self, user_id: str, lead_id: str) -> List[Dict[str, Any]]:
        return await self._request("DELETE", "leads", params={"id": f"eq.{lead_id}", "user_id": f"eq.{user_id}"},
                                   prefer="return=representation")

    # --- Account deletion ---

    async def archive_purchases(self, rows: List[Dict[str, Any]]) -> None:
        # PostgREST bulk inserts need the same keys in every row
        columns = sorted({k for row in rows for k in row})
        rows = [{k: row.get(k) for k in columns} for row in rows]
        # Idempotent: a retried deletion does not duplicate records
        await self._request("POST", "purchase_archive", params={"on_conflict": "stripe_session_id"}, json=rows,
                            prefer="resolution=ignore-duplicates")

    async def delete_user(self, user_id: str) -> None:
        """Deletes the Supabase Auth user; profile and reports follow (on delete cascade)."""
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            res = await client.delete(f"{self.auth_base}/admin/users/{user_id}", headers=self.headers)
            if res.status_code != 404:  # Already deleted
                res.raise_for_status()


_store: Optional[SupabaseStore] = None


def get_store() -> SupabaseStore:
    """FastAPI dependency (overridden in tests)."""
    global _store
    if _store is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        _store = SupabaseStore(url, key)
    return _store
