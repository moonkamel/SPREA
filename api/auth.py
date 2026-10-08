"""Supabase authentication: the frontend signs users in with Supabase Auth and
sends the access token as a Bearer token; the backend verifies it locally.

Supports both Supabase signing modes:
- legacy shared secret (HS256): set SUPABASE_JWT_SECRET
- asymmetric signing keys (RS256/ES256): public keys fetched from the JWKS endpoint
"""
import logging
import os
from typing import Optional

import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

AUDIENCE = "authenticated"


class User(BaseModel):
    id: str
    email: Optional[str] = None


_jwks_client: Optional[jwt.PyJWKClient] = None


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
        _jwks_client = jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)
    return _jwks_client


def verify_token(token: str) -> User:
    alg = jwt.get_unverified_header(token).get("alg")
    if alg == "HS256":
        secret = os.getenv("SUPABASE_JWT_SECRET")
        if not secret:
            raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not set")
        claims = jwt.decode(token, secret, algorithms=["HS256"], audience=AUDIENCE)
    elif alg in ("RS256", "ES256"):
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=[alg], audience=AUDIENCE)
    else:
        raise jwt.InvalidTokenError(f"Unsupported algorithm: {alg}")
    return User(id=claims["sub"], email=claims.get("email"))


async def current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Connexion requise.")
    try:
        return verify_token(authorization.split(" ", 1)[1].strip())
    except (jwt.PyJWTError, KeyError) as e:
        logger.info(f"Rejected token: {type(e).__name__}")
        raise HTTPException(status_code=401, detail="Session invalide ou expirée, veuillez vous reconnecter.")
