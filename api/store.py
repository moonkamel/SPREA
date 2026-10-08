"""Persistence of profiles and reports in Supabase Postgres, through its REST API
(PostgREST) with the service role key. Tables: supabase/migrations/001_accounts.sql.

The service role key bypasses row level security: it must only live on the server.
"""
import os
from typing import Any, Dict, List, Optional

import httpx


class SupabaseStore:
    def __init__(self, url: str, service_key: str, timeout: float = 10.0):
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    async def _request(self, method: str, table: str, params: Optional[Dict[str, str]] = None,
                       json: Any = None, prefer: Optional[str] = None) -> List[Dict[str, Any]]:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
