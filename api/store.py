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
        self.storage_base = f"{url.rstrip('/')}/storage/v1"
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

    # --- Quote requests (pricing page) ---

    async def create_quote_request(self, row: Dict[str, Any]) -> None:
        await self._request("POST", "quote_requests", json=row, prefer="return=minimal")

    # --- Profiles ---

    async def ensure_profile(self, user_id: str, email: Optional[str]) -> Dict[str, Any]:
        rows = await self._request(
            "POST", "profiles", params={"on_conflict": "id"}, json={"id": user_id, "email": email},
            prefer="resolution=merge-duplicates,return=representation",
        )
        return await self._with_org(rows[0])

    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._with_org(await self._one("profiles", {"id": f"eq.{user_id}"}))

    async def _with_org(self, profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Adds the user's organization (org, org_role) and its network
        (org_parent): their subscriptions also give access."""
        if not profile:
            return profile
        membership = await self.get_membership(profile["id"])
        if membership:
            org = await self.get_org(membership["org_id"])
            profile["org"] = org
            profile["org_role"] = membership["role"]
            profile["org_parent"] = await self.get_org(org["parent_id"]) if org and org.get("parent_id") else None
        return profile

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

    # --- DPE alerts ---

    async def list_zones(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "alert_zones", params={
            "user_id": f"eq.{user_id}", "select": "*", "order": "created_at.asc"})

    async def active_zones(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "alert_zones", params={"active": "eq.true", "select": "*", "limit": "5000"})

    async def create_zone(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "alert_zones", json=row, prefer="return=representation")
        return rows[0]

    async def update_zone(self, zone_id: str, fields: Dict[str, Any], user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"id": f"eq.{zone_id}"}
        if user_id:
            params["user_id"] = f"eq.{user_id}"
        return await self._request("PATCH", "alert_zones", params=params, json=fields, prefer="return=representation")

    async def delete_zone(self, user_id: str, zone_id: str) -> List[Dict[str, Any]]:
        return await self._request("DELETE", "alert_zones", params={"id": f"eq.{zone_id}", "user_id": f"eq.{user_id}"},
                                   prefer="return=representation")

    async def add_hits(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Inserts the hits not already recorded for their zone; returns only the new ones."""
        if not rows:
            return []
        return await self._request("POST", "alert_hits", params={"on_conflict": "zone_id,dpe_number"}, json=rows,
                                   prefer="resolution=ignore-duplicates,return=representation")

    async def list_hits(self, user_id: str, limit: int = 300) -> List[Dict[str, Any]]:
        return await self._request("GET", "alert_hits", params={
            "user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc,received_on.desc", "limit": str(limit)})

    # --- Teams: organizations, memberships, invitations (009_teams.sql) ---

    @staticmethod
    def _in(ids: List[str]) -> str:
        return f"in.({','.join(ids)})"

    async def create_org(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "organizations", json=row, prefer="return=representation")
        return rows[0]

    async def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("organizations", {"id": f"eq.{org_id}"})

    async def update_org(self, org_id: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "organizations", params={"id": f"eq.{org_id}"}, json=fields)

    async def delete_org(self, org_id: str) -> None:
        await self._request("DELETE", "organizations", params={"id": f"eq.{org_id}"})

    async def child_orgs(self, parent_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "organizations", params={
            "parent_id": f"eq.{parent_id}", "select": "*", "order": "name.asc"})

    async def get_membership(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("memberships", {"user_id": f"eq.{user_id}"})

    async def add_member(self, org_id: str, user_id: str, role: str) -> None:
        await self._request("POST", "memberships", json={"org_id": org_id, "user_id": user_id, "role": role})

    async def update_member(self, org_id: str, user_id: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "memberships", params={"org_id": f"eq.{org_id}", "user_id": f"eq.{user_id}"}, json=fields)

    async def remove_member(self, org_id: str, user_id: str) -> None:
        await self._request("DELETE", "memberships", params={"org_id": f"eq.{org_id}", "user_id": f"eq.{user_id}"})

    async def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        """Members with their email, oldest first."""
        members = await self._request("GET", "memberships", params={
            "org_id": f"eq.{org_id}", "select": "user_id,role,created_at", "order": "created_at.asc"})
        if members:
            profiles = await self._request("GET", "profiles", params={
                "id": self._in([m["user_id"] for m in members]), "select": "id,email"})
            emails = {p["id"]: p.get("email") for p in profiles}
            for m in members:
                m["email"] = emails.get(m["user_id"])
        return members

    async def create_invitation(self, row: Dict[str, Any]) -> Dict[str, Any]:
        # A new invitation to the same email replaces the previous one
        rows = await self._request("POST", "invitations", params={"on_conflict": "org_id,email"}, json=row,
                                   prefer="resolution=merge-duplicates,return=representation")
        return rows[0]

    async def get_invitation(self, token_hash: str) -> Optional[Dict[str, Any]]:
        return await self._one("invitations", {"token_hash": f"eq.{token_hash}"})

    async def list_invitations(self, org_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "invitations", params={
            "org_id": f"eq.{org_id}", "accepted_at": "is.null", "select": "id,email,role,expires_at,created_at",
            "order": "created_at.desc"})

    async def accept_invitation(self, invitation_id: str) -> None:
        await self._request("PATCH", "invitations", params={"id": f"eq.{invitation_id}"}, json={"accepted_at": "now()"})

    async def delete_invitation(self, org_id: str, invitation_id: str) -> List[Dict[str, Any]]:
        return await self._request("DELETE", "invitations", params={"id": f"eq.{invitation_id}", "org_id": f"eq.{org_id}"},
                                   prefer="return=representation")

    async def list_links_for_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        return await self._request("GET", "prospect_links", params={
            "user_id": self._in(user_ids), "select": "code,user_id,dpe_number,address,label,created_at,visits,last_visit_at",
            "order": "created_at.desc", "limit": "2000"})

    async def list_leads_for_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        return await self._request("GET", "leads", params={
            "user_id": self._in(user_ids), "select": "*", "order": "created_at.desc", "limit": "1000"})

    async def list_zones_for_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        return await self._request("GET", "alert_zones", params={
            "user_id": self._in(user_ids), "select": "*", "order": "created_at.asc"})

    async def list_hits_for_users(self, user_ids: List[str], limit: int = 500) -> List[Dict[str, Any]]:
        return await self._request("GET", "alert_hits", params={
            "user_id": self._in(user_ids), "select": "*", "order": "created_at.desc,received_on.desc", "limit": str(limit)})

    async def transfer_contacts(self, from_user: str, to_user: str) -> None:
        """An agent leaves the agency: their letters' links and the requests
        received go to the agency owner (the agency is the controller)."""
        links = await self._request("GET", "prospect_links", params={"user_id": f"eq.{from_user}", "select": "code,dpe_number"})
        for link in links:
            existing = await self.get_link_for_dpe(to_user, link["dpe_number"])
            if existing:
                # The owner already has a link for this dwelling: requests move to it
                await self._request("PATCH", "leads", params={"code": f"eq.{link['code']}"}, json={"code": existing["code"]})
                await self._request("DELETE", "prospect_links", params={"code": f"eq.{link['code']}"})
            else:
                await self.update_link(link["code"], {"user_id": to_user})
        await self._request("PATCH", "leads", params={"user_id": f"eq.{from_user}"}, json={"user_id": to_user})

    # --- Copropriétés: national registry (010_coproprietes.sql) ---

    async def get_copro(self, immat: str) -> Optional[Dict[str, Any]]:
        return await self._one("coproprietes", {"immat": f"eq.{immat}"})

    async def copros_near(self, lat: float, lon: float, delta: float = 0.0006) -> List[Dict[str, Any]]:
        """Registered copropriétés whose reference point is within about 60 m."""
        return await self._request("GET", "coproprietes", params={
            "and": f"(lat.gte.{lat - delta},lat.lte.{lat + delta},lon.gte.{lon - delta},lon.lte.{lon + delta})",
            "select": "*", "limit": "20"})

    # --- Monopropriétés: whole buildings with a single owner (011_monopro.sql) ---

    async def monopro_in_bbox(self, west: float, south: float, east: float, north: float,
                              company_only: bool, min_log: int, limit: int, poor_dpe: bool = False,
                              min_signal: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"and": f"(lat.gte.{south},lat.lte.{north},lon.gte.{west},lon.lte.{east})",
                  "nb_log": f"gte.{min_log}", "select": "*", "order": "signal_score.desc.nullslast,nb_log.desc",
                  "limit": str(limit)}
        if min_signal is not None:
            params["signal_score"] = f"gte.{min_signal}"
        if company_only:
            params["owner_siren"] = "not.is.null"
        if poor_dpe:
            # Representative DPE in F or G, or at least one dwelling in F or G
            params["or"] = "(dpe_label.in.(F,G),dpe_fg.gt.0)"
        return await self._request("GET", "monopro_buildings", params=params)

    async def get_monopro(self, building_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("monopro_buildings", {"id": f"eq.{building_id}"})

    async def monopro_by_owner(self, siren: str, limit: int) -> List[Dict[str, Any]]:
        return await self._request("GET", "monopro_buildings", params={
            "owner_siren": f"eq.{siren}", "select": "id,address,nb_log,dpe_label,lat,lon", "order": "nb_log.desc",
            "limit": str(limit)})

    async def monopro_owners(self, sirens: List[str]) -> List[Dict[str, Any]]:
        return await self._request("GET", "monopro_owners", params={"siren": self._in(sirens), "select": "*"})

    async def monopro_signal(self, siren: str) -> Optional[Dict[str, Any]]:
        return await self._one("monopro_signals", {"siren": f"eq.{siren}"})

    async def save_signal_summary(self, siren: str, summary: Dict[str, Any], key: str) -> None:
        await self._request("PATCH", "monopro_signals", params={"siren": f"eq.{siren}"},
                            json={"summary": summary, "summary_key": key}, prefer="return=minimal")

    # --- Account deletion ---

    async def archive_purchases(self, rows: List[Dict[str, Any]]) -> None:
        # PostgREST bulk inserts need the same keys in every row
        columns = sorted({k for row in rows for k in row})
        rows = [{k: row.get(k) for k in columns} for row in rows]
        # Idempotent: a retried deletion does not duplicate records
        await self._request("POST", "purchase_archive", params={"on_conflict": "stripe_session_id"}, json=rows,
                            prefer="resolution=ignore-duplicates")

    # --- Copropriété documents read by Claude (013_copro_docs.sql) ---

    async def create_doc_analysis(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._request("POST", "copro_doc_analyses", json=row, prefer="return=representation")
        return rows[0]

    async def get_doc_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return await self._one("copro_doc_analyses", {"id": f"eq.{analysis_id}"})

    async def update_doc_analysis(self, analysis_id: str, fields: Dict[str, Any]) -> None:
        await self._request("PATCH", "copro_doc_analyses", params={"id": f"eq.{analysis_id}"}, json=fields,
                            prefer="return=minimal")

    async def list_doc_analyses(self, user_id: str, since: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"user_id": f"eq.{user_id}", "select": "id,address,status,files,created_at,result->synthese,result->niveau_risque",
                  "order": "created_at.desc", "limit": "100"}
        if since:
            params["created_at"] = f"gte.{since}"
        return await self._request("GET", "copro_doc_analyses", params=params)

    async def delete_doc_analysis(self, analysis_id: str) -> None:
        await self._request("DELETE", "copro_doc_analyses", params={"id": f"eq.{analysis_id}"})

    async def stale_doc_uploads(self, before: str) -> List[Dict[str, Any]]:
        return await self._request("GET", "copro_doc_analyses", params={
            "status": "eq.uploading", "created_at": f"lt.{before}", "select": "id,files", "limit": "200"})

    # --- Storage (private bucket copro-docs) ---

    async def signed_upload_url(self, bucket: str, path: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            # Storage rejects an empty body sent as JSON
            res = await client.post(f"{self.storage_base}/object/upload/sign/{bucket}/{path}", headers=self.headers, json={})
            res.raise_for_status()
        return f"{self.storage_base}{res.json()['url']}"

    async def download_object(self, bucket: str, path: str) -> Optional[bytes]:
        async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
            res = await client.get(f"{self.storage_base}/object/{bucket}/{path}", headers=self.headers)
            if res.status_code in (400, 404):  # Never uploaded
                return None
            res.raise_for_status()
            return res.content

    async def delete_objects(self, bucket: str, paths: List[str]) -> None:
        if not paths:
            return
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            res = await client.request("DELETE", f"{self.storage_base}/object/{bucket}", headers=self.headers,
                                       json={"prefixes": paths})
            res.raise_for_status()

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
