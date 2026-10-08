import os
import time
from collections import defaultdict, deque
from typing import Dict

from fastapi import HTTPException, Request

# --- Rate limiting ---
# In-memory sliding window per client IP. Protects the paid endpoints (LLM calls)
# from abuse. On serverless platforms memory is per instance, so this is a
# best-effort guard, not a hard quota.

class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: Dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request):
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        window = self.calls[ip]
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
