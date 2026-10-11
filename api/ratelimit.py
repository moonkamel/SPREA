import os
import time
from collections import defaultdict, deque
from typing import Dict

from fastapi import Depends, HTTPException, Request

try:
    from api.auth import User, current_user
except ImportError:
    from auth import User, current_user

# --- Rate limiting ---
# In-memory sliding window per client IP, or per user (per_user). Protects the
# paid endpoints (LLM calls) from abuse. On serverless platforms memory is per
# instance, so this is a best-effort guard, not a hard quota.

class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: Dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request):
        forwarded = request.headers.get("x-forwarded-for", "")
        self.hit(forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown"))

    def per_user(self, user: User = Depends(current_user)):
        """Same limit, counted per signed-in user rather than per IP (agents of
        one agency often share an address)."""
        self.hit(f"user:{user.id}")

    def hit(self, key: str):
        now = time.monotonic()
        window = self.calls[key]
        while window and now - window[0] > self.period:
            window.popleft()
        if len(window) >= self.max_calls:
            raise HTTPException(status_code=429, detail="Trop de requêtes, veuillez réessayer plus tard.")
        window.append(now)

search_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_SEARCH_PER_MIN", "30")), period_seconds=60)
# The UI re-simulates on every change (debounced), so this one is looser
simulate_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_SIMULATE_PER_MIN", "120")), period_seconds=60)
ai_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_AI_PER_HOUR", "10")), period_seconds=3600)
# Callback requests left on the public owner pages
lead_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_LEADS_PER_HOUR", "5")), period_seconds=3600)
# Team invitations (each one sends an email)
invite_limiter = RateLimiter(max_calls=int(os.getenv("RATE_LIMIT_INVITES_PER_HOUR", "20")), period_seconds=3600)
