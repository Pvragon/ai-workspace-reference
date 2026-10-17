"""Minimal Gemini REST client (free tier) — stdlib only.

Uses the v1beta ``:generateContent`` endpoint in JSON response mode. No SDK
dependency, matching the consumer-deals stdlib-first convention. The API key
(GEMINI_FREE_API_KEY) is read via config.load_secret and never logged.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Optional

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


class GeminiError(RuntimeError):
    rate_limited = False   # set True when the failure was an HTTP 429


def generate_json(
    prompt: str,
    *,
    model: str,
    api_key: str,
    temperature: float = 0.0,
    max_retries: int = 4,
    timeout: int = 90,
    max_output_tokens: Optional[int] = None,
    thinking_budget: Optional[int] = None,
) -> dict:
    """Call Gemini in JSON mode and return the parsed object.

    Retries on 429/5xx with exponential backoff (free tier is rate-limited).
    Raises GeminiError on persistent failure or unparseable output.

    ``max_output_tokens`` matters more than it looks: gemini-2.5-flash runs
    thinking by default and thinking tokens draw down the SAME output budget, so
    a long generation can come back truncated — which surfaces here as an
    unparseable-JSON error rather than as an obvious limit error. Set it
    explicitly for anything generating more than a few hundred tokens.

    ``thinking_budget=0`` disables thinking outright. MEASURED 2026-07-29: with
    thinking on and maxOutputTokens=4096, structured-extraction calls burned the
    whole budget on thinking and returned empty text -> JSONDecodeError. For
    mechanical JSON extraction, pass thinking_budget=0 and a generous
    max_output_tokens; both are needed, since a low cap alone is the trap.
    """
    url = _ENDPOINT.format(model=model, key=api_key)
    gen_cfg = {
        "temperature": temperature,
        "responseMimeType": "application/json",
    }
    if max_output_tokens:
        gen_cfg["maxOutputTokens"] = int(max_output_tokens)
    if thinking_budget is not None:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": int(thinking_budget)}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }
    data = json.dumps(body).encode()
    last = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
            txt = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 503) and attempt < max_retries - 1:
                # honor Retry-After when present (Gemini sends it on quota limits)
                ra = 0
                try:
                    ra = int(e.headers.get("Retry-After", "0") or 0)
                except (ValueError, TypeError):
                    ra = 0
                time.sleep(min(max(ra, 2 ** attempt + 1), 60))
                continue
            err = GeminiError(f"Gemini {model}: {last}")
            err.rate_limited = (e.code == 429)   # let callers detect a hard rate-limit
            raise err from e
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"parse: {type(e).__name__}"
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)
                continue
            raise GeminiError(f"Gemini {model}: unparseable response ({last})") from e
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
            # includes read timeouts (socket.timeout / TimeoutError) that are NOT
            # wrapped in URLError — these previously crashed the whole poll.
            last = f"{type(e).__name__}: {e}"
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + 1)
                continue
            raise GeminiError(f"Gemini {model}: {last}") from e
    raise GeminiError(f"Gemini {model}: exhausted retries ({last})")
