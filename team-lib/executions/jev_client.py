#!/usr/bin/env python3
# ---
# template: execution
# version: 0.3.1
# summary: "Client CLI for Jev, TypeSafe's typed decision model: ask fixed-answer questions (noul yes/no, choice, score) about a state and get probabilities back, or calibrate a question's threshold with eval over labelled cases. Python port of the do-shit harness's jev.mjs: pinned endpoint, real-time PHI pseudonymisation and credential redaction before send, one retry, degraded result instead of raising. Callable from any language via the CLI."
# created: 2026-11-05
# last_updated: 2026-11-06
# maintainer: pvragon
# ---
"""
Jev (TypeSafe System One) client. Ported from the do-shit agent harness's client
(<project>/.agents/skills/do-shit/scripts/lib/jev.mjs + redact.jq).

Contract re-checked against https://docs.typesafe.ai/api.md on 2026-11-05:
  POST https://api.typesafe.ai/v1/systemone   Authorization: Bearer <key>
  body  { state, model: "jev-latest", questions: { id: Question } }
  noul   -> { type:"noul",   noul: 0..1 }
  choice -> { type:"choice", choice, probabilities:{opt:p}, confidence }
  score  -> { type:"score",  score: 0..levels-1, legend, probabilities, confidence }
  usage  -> { input_tokens (billed), output_tokens (free) }
  errors: 400 bad request, 401 bad key, 422 validation, 429 rate limit, 5xx/529 overloaded
  (the image-only "box" type is not supported here)

Usage:
  jev_client.py ask --state FILE|- --questions FILE
  jev_client.py ask --state FILE|- --noul "Is this a vendor invoice?" --yes "..." --no "..." [--threshold 0.6]
  jev_client.py ask --state FILE|- --choice "Which team owns it?" --option billing="..." --option ops="..."
  jev_client.py ask --state FILE|- --score "How urgent?" --level "not" --level "soon" --level "now"
  jev_client.py eval --cases FILE --questions FILE [--cache FILE] [--no-cache]
  jev_client.py --self-check        # offline test suite, fake transport, no network

  --state takes a JSON file, or plain text (sent as a string). "-" reads stdin.

Question file (JSON), the do-shit house shape. A list, or {"questions": [...]}:
  {"id": "needs_reply", "type": "noul", "instructions": "...",
   "criteria": {"true": "...", "false": "..."}, "threshold": 0.6}
  choice criteria: {"option": "description", ...}; score criteria: ["level 0", "level 1", ...]
  "id" and "threshold" never reach Jev. The threshold is applied HERE, in code.

Cases file for eval (JSON list or JSONL):
  {"id": "c1", "state": <anything>, "expected": {"needs_reply": true}}
  noul/score expect true|false; choice expects the option name.

PHI: TypeSafe signs no BAA, so every request is pseudonymised first (SSN, email, phone, ICD-10,
labelled DOB/MRN/member/Medicaid IDs, patient names, diagnoses, PHI-named fields -> [KIND_n],
consistent within a request). The result reports counts by kind in "phi_redacted", never values.
Bare names or street addresses in unlabelled free text are NOT detected.

Every outcome is a dict: {"status": "ok"|"error", "degraded": bool, "answers": {...}, ...}.
Nothing raises. A caller treats degraded as "Jev said nothing" and applies its own fallback.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Pinned, never env-overridable: the TypeSafe key can only ever go to TypeSafe.
API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
TIMEOUT_S = 8
# The do-shit harness's name first (so its env works unchanged), then the workspace .env name.
KEY_NAMES = ("TYPESAFE_API_KEY", "TYPESAFE_JEV_API_KEY")
ENV_FILE = Path.home() / "ai-workspace/personal/secrets/.env"
USAGE_LOG = Path.home() / "ai-workspace/my-lib/runtime/.tmp/jev-usage.log"
TYPES = ("noul", "choice", "score")

# ---------------------------------------------------------------- redaction
# Port of redact.jq (credential shapes only, NOT PHI). Keep in sync with the do-shit harness's redact.jq;
# the self-check compares the two when jq and his file are present.
_CRED = r"[A-Za-z0-9_\-\.]{16,}"
REDACT_RULES = [
    (r"(?P<p>sk-ant-)[A-Za-z0-9_\-]{16,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>sk-(?:proj-)?)[A-Za-z0-9_\-]{24,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>gh[pousr]_)[A-Za-z0-9]{20,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>github_pat_)[A-Za-z0-9_]{30,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>glpat-)[A-Za-z0-9_\-]{16,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>xox[baprs]-)[A-Za-z0-9\-]{10,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>A(?:KIA|SIA))[0-9A-Z]{16}", r"\g<p>[REDACTED]"),
    (r"(?P<p>sbp_|sb_secret_)[A-Za-z0-9_]{20,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>rnd_)[A-Za-z0-9]{20,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>npm_)[A-Za-z0-9]{30,}", r"\g<p>[REDACTED]"),
    (r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}", "[REDACTED_JWT]"),
    (r"(?P<p>[Bb]earer\s+)[A-Za-z0-9._\-]{20,}", r"\g<p>[REDACTED]"),
    (r"(?P<p>(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:@/\s]+:)[^@\s]+(?P<s>@)",
     r"\g<p>[REDACTED]\g<s>"),
    (r"(?P<p>(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|access[_-]?token)\"?\s*[:=]\s*\"?)"
     + _CRED, r"\g<p>[REDACTED]"),
]
REDACT_RULES = [(re.compile(p), r) for p, r in REDACT_RULES]
# Addition over the original redact_strings: a secret held as a dict VALUE under a secret-named KEY
# ({"password": "..."}) has no "password=" in the string itself, so the string rules miss it.
_SECRET_KEY = re.compile(r"(api[_-]?key|apikey|token|secret|password|passwd|pwd)", re.I)
_CRED_ONLY = re.compile(r"^" + _CRED + r"$")


def redact(text: str) -> str:
    for rx, rep in REDACT_RULES:
        text = rx.sub(rep, text)
    return text


def redact_strings(obj):
    """Redact every string value in a JSON document. Keys are left alone."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        return [redact_strings(v) for v in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"non-string key {k!r}")
            if isinstance(v, str) and _SECRET_KEY.search(k) and _CRED_ONLY.match(v):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_strings(v)
        return out
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def redact_body(body: dict) -> dict:
    """Redact, then prove it: the serialised result must match no rule. Raises on any doubt."""
    out = redact_strings(body)
    text = json.dumps(out)
    for rx, _ in REDACT_RULES:
        m = rx.search(text)
        if m and "[REDACTED" not in text[m.start():m.end() + 12]:
            raise ValueError("credential shape survived redaction")
    return out


# ---------------------------------------------------------------- PHI redaction
# TypeSafe signs no BAA and offers no self-hosting (enterprise FAQ, read 2026-11-05), so PHI
# must never reach Jev. Every request is PSEUDONYMISED in real time before it is sent: each
# identifier becomes a placeholder like [EMAIL_1], the same value always gets the same
# placeholder within a request (so Jev can still tell "same person" from "different person"),
# and the same input always yields the same request (so eval caching still works). The
# placeholder-to-value map never leaves this process and is never logged or returned.
# After redaction the output is re-scanned; if any rule still matches, nothing is sent.
# Limit: a bare name or street address in free text, with no label and no PHI field name,
# is not detected. Callers still reduce records to non-identifying fields first.
PHI_VALUE_RULES = [  # (kind, pattern): the whole match is replaced
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]*\w\b")),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\w-])")),
    ("ICD10", re.compile(r"\b[A-TV-Z]\d{2}\.\d{1,4}[A-Z]?\b")),
]
_NOT_TOKEN = r"(?!\[[A-Z0-9_]+_\d+\])"
# Label + an ID-like value (one token containing a digit): the value is replaced.
_LABEL_ID = re.compile(
    r"(?i)(?P<label>\b(?:dob|d\.o\.b\.?|date of birth|birth ?date|ssn|social security(?: number)?|mrn"
    r"|medical record(?: number| #)?|member ?(?:id|number|#)|medicaid ?(?:id|number|#)"
    r"|subscriber ?(?:id|number)|policy ?(?:id|number)|patient ?(?:id|number|#))\b)"
    r"(?P<sep>\.?\s*(?:[:#=]|\bis\b|\bof\b)?\s*)" + _NOT_TOKEN + r"(?P<val>[^\s,;]*\d[^\s,;]*)")
# Label + a phrase (patient name, diagnosis): the phrase up to the next , ; or line end is replaced.
_LABEL_PHRASE = re.compile(
    r"(?i)(?P<label>\b(?:patient ?name|diagnos[ie]s|dx)\b)(?P<sep>\s*[:=-]\s*)" + _NOT_TOKEN
    + r"(?P<val>[^,;\n]{1,80}?)(?=\s*(?:[,;\n]|$))")
_LABEL_KIND = [("dob", "DOB"), ("birth", "DOB"), ("ssn", "SSN"), ("social", "SSN"), ("mrn", "MRN"),
               ("medical", "MRN"), ("member", "MEMBER_ID"), ("medicaid", "MEDICAID_ID"),
               ("subscriber", "SUBSCRIBER_ID"), ("policy", "POLICY_NUMBER"), ("patient ?name", "PATIENT_NAME"),
               ("patient", "PATIENT_ID"), (r"d\.o\.b", "DOB"), ("diagnos", "DIAGNOSIS"), ("dx", "DIAGNOSIS")]
_PHI_KEY_ANY = {"patient", "ssn", "dob", "mrn", "medicaid", "subscriber", "diagnosis", "diagnoses",
                "birthdate", "birth", "icd", "icd10"}
_PHI_KEY_LAST = {"email", "phone", "address", "street", "zip", "zipcode", "postcode", "addr"}
_PHI_NAME_OWNER = {"first", "last", "full", "rider", "patient", "member", "client", "given", "family"}


def _phi_key(key: str) -> bool:
    """A key names a patient-record field, judged by its words (snake, kebab or camelCase)."""
    words = [w.lower() for w in re.split(r"[_\-\s.]+|(?<=[a-z])(?=[A-Z])", key) if w]
    if not words:
        return False
    if _PHI_KEY_ANY & set(words) or words[-1] in _PHI_KEY_LAST:
        return True
    if words[-1] == "name" and len(words) > 1 and words[-2] in _PHI_NAME_OWNER:
        return True
    return any(a == "member" and b in ("id", "number") for a, b in zip(words, words[1:]))


class Pseudonymizer:
    """Consistent placeholders within one request: same (kind, value) -> same [KIND_n]."""

    def __init__(self):
        self._map, self._n = {}, {}

    def token(self, kind: str, value) -> str:
        norm = re.sub(r"\s+", " ", str(value)).strip().lower()
        if kind in ("PHONE", "SSN"):
            norm = re.sub(r"\D", "", norm)[-10:]  # (405) 555-0142 == 405.555.0142
        k = (kind, norm)
        if k not in self._map:
            self._n[kind] = self._n.get(kind, 0) + 1
            self._map[k] = f"[{kind}_{self._n[kind]}]"
        return self._map[k]

    def counts(self) -> dict:
        return dict(self._n)

    def text(self, s: str) -> str:
        for kind, rx in PHI_VALUE_RULES:
            s = rx.sub(lambda m: self.token(kind, m.group(0)), s)

        def lab(m):
            label = m.group("label").lower()
            kind = next((kd for pat, kd in _LABEL_KIND if re.search(pat, label)), "PHI")
            return m.group("label") + m.group("sep") + self.token(kind, m.group("val"))
        s = _LABEL_ID.sub(lab, s)
        return _LABEL_PHRASE.sub(lab, s)

    def _field_kind(self, key: str, value) -> str:
        if isinstance(value, str):
            for kind, rx in PHI_VALUE_RULES:
                if rx.fullmatch(value.strip()):
                    return kind
        words = [w.upper() for w in re.split(r"[_\-\s.]+|(?<=[a-z])(?=[A-Z])", key) if w]
        return "_".join(words) or "FIELD"

    def walk(self, obj, redact_fields=True):
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, list):
            return [self.walk(v, redact_fields) for v in obj]
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                k2 = self.text(k) if isinstance(k, str) else k
                if redact_fields and isinstance(k, str) and _phi_key(k) and v is not None and not isinstance(v, bool):
                    out[k2] = self.token(self._field_kind(k, v), json.dumps(v, sort_keys=True)
                                         if isinstance(v, (dict, list)) else v)
                else:
                    out[k2] = self.walk(v, redact_fields)
            return out
        return obj


def phi_redact(state, questions=None):
    """Return (state, questions, counts) with PHI replaced by consistent placeholders.

    Field-name rules apply to the state only (question dicts are code-authored structure);
    value and label rules apply to every string in both. Raises if anything survives.
    """
    p = Pseudonymizer()
    s2 = p.walk(state)
    q2 = p.walk(questions, redact_fields=False) if questions is not None else None
    text = json.dumps([s2, q2])
    for kind, rx in PHI_VALUE_RULES:
        if rx.search(text):
            raise ValueError(f"{kind} survived PHI redaction")
    return s2, q2, p.counts()


# ---------------------------------------------------------------- key
def resolve_key(env=None, env_file=ENV_FILE) -> str:
    env = os.environ if env is None else env
    for name in KEY_NAMES:
        if env.get(name):
            return env[name]
    try:
        lines = Path(env_file).read_text().splitlines()
    except OSError:
        return ""
    found = {}
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, val = line.partition("=")
        if sep and name.strip() in KEY_NAMES:
            found[name.strip()] = val.strip().strip("'\"")
    for name in KEY_NAMES:
        if found.get(name):
            return found[name]
    return ""


# ---------------------------------------------------------------- transport
def http_transport(body: dict, key: str) -> tuple:
    """POST to the pinned endpoint. Returns (status, json). status 0 = no response."""
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "pvragon-jev-client/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:  # timeout, DNS, TLS, reset: all are "no response"
        return 0, {"_error": "timeout" if "timed out" in str(e).lower() else type(e).__name__}
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def _retryable(status: int) -> bool:
    return status == 0 or status == 429 or status >= 500


def check_answers(questions: dict, answers) -> str:
    """Return an error string, or "" when every answer has the right type and shape."""
    if not isinstance(answers, dict):
        return "no answers in response"
    for qid, q in questions.items():
        a = answers.get(qid)
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            return f"missing answer for {qid}"
        t = q["type"]
        v = a.get(t)
        if t in ("noul", "score") and (isinstance(v, bool) or not isinstance(v, (int, float))):
            return f"bad {t} for {qid}"
        if t == "noul" and not 0 <= v <= 1:
            return f"noul out of range for {qid}"
        if t == "choice" and (not isinstance(v, str) or v not in q.get("criteria", {})):
            return f"bad choice for {qid}"
    return ""


def _log_usage(log_path, qids, usage, degraded):
    if not log_path:
        return
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')}\t{','.join(qids)}\t"
                    f"{(usage or {}).get('input_tokens', '')}\t{'degraded' if degraded else 'ok'}\n")
    except OSError:
        pass  # a cost log must never break a decision


def _fail(error, answers=None):
    return {"status": "error", "degraded": True, "error": error, "answers": answers or {}}


def ask(state, questions: dict, key=None, transport=None, retry_delay=1.0, log_path=USAGE_LOG) -> dict:
    """One Jev request. questions = {id: {type, instructions, criteria}} in API shape.

    Returns {status, degraded, answers, model?, usage?, error?}. Never raises.
    """
    try:
        try:  # TypeSafe has no BAA: pseudonymise PHI before anything else touches the request
            state, safe_questions, phi_counts = phi_redact(state, questions)
        except Exception as e:  # never send what could not be redacted
            return _fail(f"PHI redaction failed: {e}")
        key = resolve_key() if key is None else key
        if not key:
            return _fail("no TypeSafe API key (" + " / ".join(KEY_NAMES) + ")")
        transport = transport or http_transport
        try:
            body = redact_body({"state": state, "model": MODEL, "questions": safe_questions})
        except Exception as e:  # never send unredacted content
            return _fail(f"redaction failed: {e}")
        last = ""
        for attempt in range(2):
            try:
                status, js = transport(body, key)
            except Exception as e:
                status, js = 0, {"_error": type(e).__name__}
            js = js if isinstance(js, dict) else {}
            if status == 200:
                usage = js.get("usage")
                err = check_answers(questions, js.get("answers"))
                _log_usage(log_path, list(questions), usage, bool(err))
                if err:
                    return {**_fail(err, js.get("answers") if isinstance(js.get("answers"), dict) else {}),
                            "usage": usage}
                return {"status": "ok", "degraded": False, "answers": js["answers"],
                        "model": js.get("model"), "usage": usage, "phi_redacted": phi_counts}
            detail = js.get("_error") or js.get("detail")
            last = f"HTTP {status}" + (f" ({str(detail)[:200]})" if detail else "")
            if not _retryable(status) or attempt == 1:
                break
            time.sleep(retry_delay)
        _log_usage(log_path, list(questions), None, True)
        return _fail(last)
    except Exception as e:  # belt and braces: the contract is "never raises"
        return _fail(f"client error: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- question files
def load_questions(src) -> list:
    """Return [{id, type, instructions, criteria?, threshold?}] from a path, JSON text or list."""
    data = src
    if isinstance(src, (str, Path)):
        data = json.loads(Path(src).read_text())
    if isinstance(data, dict):
        data = data.get("questions", data)
    if isinstance(data, dict):  # {id: {...}}
        data = [{"id": k, **v} for k, v in data.items()]
    out = []
    for q in data:
        if q.get("type") not in TYPES:
            raise ValueError(f"question {q.get('id')!r}: type must be one of {TYPES}")
        if not q.get("id") or not q.get("instructions"):
            raise ValueError("every question needs an id and instructions")
        if q["type"] in ("choice", "score") and not q.get("criteria"):
            raise ValueError(f"question {q['id']!r}: {q['type']} needs criteria")
        out.append(q)
    return out


def api_questions(qs: list) -> dict:
    """Strip code-only fields (id, threshold) into Jev's {id: question} shape."""
    return {q["id"]: {k: v for k, v in q.items() if k in ("type", "instructions", "criteria")} for q in qs}


def probability(q: dict, answer: dict):
    """0..1 for noul and score (score normalised by levels); None for choice."""
    if q["type"] == "noul":
        return answer["noul"]
    if q["type"] == "score":
        levels = len(q["criteria"])
        return answer["score"] / (levels - 1) if levels > 1 else 0.0
    return None


def decisions(qs: list, result: dict) -> dict:
    """Apply each question's threshold in code. choice -> its top option."""
    out = {}
    if result.get("degraded"):
        return out
    for q in qs:
        a = result["answers"].get(q["id"])
        if q["type"] == "choice":
            out[q["id"]] = a["choice"]
        elif q.get("threshold") is not None:
            out[q["id"]] = probability(q, a) >= q["threshold"]
    return out


def run(state, questions, key=None, transport=None, log_path=USAGE_LOG) -> dict:
    """Importable entry point: ask questions (list in house shape, or a file path) about state."""
    try:
        qs = load_questions(questions)
    except Exception as e:
        return _fail(f"bad questions: {e}")
    res = ask(state, api_questions(qs), key=key, transport=transport, log_path=log_path)
    res["decisions"] = decisions(qs, res)
    return res


# ---------------------------------------------------------------- eval
def sweep(points: list) -> dict:
    """points [{p, y}] -> best-F1 threshold (then accuracy), middle of the tie plateau. Port of the do-shit eval sweep."""
    rows = []
    for i in range(1, 20):
        t = round(i * 0.05, 2)
        tp = fp = fn = ok = 0
        for pt in points:
            yhat = pt["p"] >= t
            tp += yhat and pt["y"]
            fp += yhat and not pt["y"]
            fn += (not yhat) and pt["y"]
            ok += yhat == pt["y"]
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        rows.append({"threshold": t, "f1": round(f1, 3), "accuracy": round(ok / len(points), 3)})
    top = max(rows, key=lambda r: (r["f1"], r["accuracy"]))
    plateau = [r for r in rows if r["f1"] == top["f1"] and r["accuracy"] == top["accuracy"]]
    best = dict(plateau[(len(plateau) - 1) // 2])
    best["plateau"] = [plateau[0]["threshold"], plateau[-1]["threshold"]]
    return best


def confidence_sweep(points: list) -> list:
    """Choice questions: trust Jev only at confidence >= t, fall back otherwise.
    Per t: coverage (share answered by Jev) and accuracy among those answered."""
    rows = []
    for t in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        kept = [p for p in points if p["conf"] >= t]
        rows.append({"min_confidence": t, "coverage": round(len(kept) / len(points), 3),
                     "accuracy": round(sum(p["p"] for p in kept) / len(kept), 3) if kept else None})
    return rows


def load_cases(path) -> list:
    text = Path(path).read_text().strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run_eval(cases, questions, cache_path=None, key=None, transport=None, log_path=USAGE_LOG) -> dict:
    """Ask every case once (cached by request hash), then score each question against labels."""
    qs = load_questions(questions)
    aq = api_questions(qs)
    cases = load_cases(cases) if isinstance(cases, (str, Path)) else cases
    cache = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text())
    points = {q["id"]: [] for q in qs}
    errors, calls, tokens = [], 0, 0
    for c in cases:
        h = hashlib.sha256(json.dumps({"s": c["state"], "q": aq}, sort_keys=True).encode()).hexdigest()
        answers = cache.get(h)
        if answers is None:
            r = ask(c["state"], aq, key=key, transport=transport, log_path=log_path)
            calls += 1
            tokens += (r.get("usage") or {}).get("input_tokens") or 0
            if r["degraded"]:
                errors.append({"id": c.get("id"), "error": r["error"]})
                continue
            answers = cache[h] = r["answers"]
        for q in qs:
            if q["id"] not in c.get("expected", {}):
                continue
            exp, a = c["expected"][q["id"]], answers[q["id"]]
            if q["type"] == "choice":
                points[q["id"]].append({"p": 1.0 if a["choice"] == exp else 0.0, "y": True,
                                        "conf": a.get("confidence") or 0.0,
                                        "case": c.get("id"), "got": a["choice"], "exp": exp})
            else:
                points[q["id"]].append({"p": probability(q, a), "y": bool(exp), "case": c.get("id")})
    if cache_path:
        Path(cache_path).write_text(json.dumps(cache, indent=1))
    report = {}
    for q in qs:
        pts = points[q["id"]]
        if not pts:
            continue
        if q["type"] == "choice":
            acc = sum(p["p"] for p in pts) / len(pts)
            report[q["id"]] = {"n": len(pts), "accuracy": round(acc, 3),
                               "by_confidence": confidence_sweep(pts),
                               "misses": [f"{p['case']}: got {p['got']}, expected {p['exp']} (conf {p['conf']:.2f})"
                                          for p in pts if not p["p"]]}
            continue
        cur = q.get("threshold", 0.5)
        best = sweep(pts)
        report[q["id"]] = {
            "n": len(pts), "positives": sum(p["y"] for p in pts), "threshold_in_file": cur,
            "accuracy_at_file_threshold": round(sum((p["p"] >= cur) == p["y"] for p in pts) / len(pts), 3),
            "best": best,
            "misses_at_best": [f"{p['case']} p={p['p']:.2f} expected={p['y']}" for p in pts
                               if (p["p"] >= best["threshold"]) != p["y"]],
            "flag": "accuracy < 0.7: reword before trusting" if best["accuracy"] < 0.7 else None,
        }
    return {"status": "ok" if not errors else "error", "cases": len(cases), "api_calls": calls,
            "input_tokens": tokens, "errors": errors, "report": report}


# ---------------------------------------------------------------- CLI
def _read_state(arg):
    text = sys.stdin.read() if arg == "-" else Path(arg).read_text()
    try:
        return json.loads(text)
    except ValueError:
        return text  # plain text is a valid state


def _inline_question(a):
    if a.noul:
        crit = {"true": a.yes, "false": a.no} if (a.yes or a.no) else None
        q = {"id": "q", "type": "noul", "instructions": a.noul, "threshold": a.threshold}
        if crit:
            q["criteria"] = {k: v for k, v in crit.items() if v}
        return [q]
    if a.choice:
        opts = dict(o.split("=", 1) if "=" in o else (o, o) for o in a.option)
        return [{"id": "q", "type": "choice", "instructions": a.choice, "criteria": opts}]
    if a.score:
        return [{"id": "q", "type": "score", "instructions": a.score, "criteria": a.level,
                 "threshold": a.threshold}]
    return None


def main():
    if "--self-check" in sys.argv:
        sys.exit(self_check())
    ap = argparse.ArgumentParser(description="Jev decision-model client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ask", help="ask questions about a state")
    p.add_argument("--state", required=True, help="JSON or text file, or - for stdin")
    p.add_argument("--questions", help="question file (JSON)")
    p.add_argument("--noul", help="inline yes/no question")
    p.add_argument("--yes", help="what counts as yes")
    p.add_argument("--no", help="what counts as no")
    p.add_argument("--choice", help="inline choice question")
    p.add_argument("--option", action="append", default=[], help="name=description (repeat)")
    p.add_argument("--score", help="inline score question")
    p.add_argument("--level", action="append", default=[], help="score level, lowest first (repeat)")
    p.add_argument("--threshold", type=float, default=None)
    e = sub.add_parser("eval", help="calibrate questions against labelled cases")
    e.add_argument("--cases", required=True)
    e.add_argument("--questions", required=True)
    e.add_argument("--cache", help="answer cache (default: <cases>.jev-cache.json)")
    e.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    if a.cmd == "ask":
        qs = _inline_question(a) or a.questions
        if not qs:
            ap.error("give --questions FILE or one inline --noul / --choice / --score")
        try:
            state = _read_state(a.state)
        except OSError as ex:
            res = _fail(f"cannot read state: {ex}")
        else:
            res = run(state, qs)
    else:
        cache = None if a.no_cache else (a.cache or f"{a.cases}.jev-cache.json")
        try:
            res = run_eval(a.cases, a.questions, cache_path=cache)
        except Exception as ex:
            res = _fail(f"eval failed: {type(ex).__name__}: {ex}")
    print(json.dumps(res, indent=1))
    sys.exit(0 if res["status"] == "ok" else 1)


# ---------------------------------------------------------------- self-check (offline tests)
def self_check() -> int:
    import subprocess
    import tempfile
    import unittest

    Q = {
        "a": {"type": "noul", "instructions": "x"},
        "b": {"type": "choice", "instructions": "y", "criteria": {"ship": "s", "fix": "f"}},
        "c": {"type": "score", "instructions": "z", "criteria": ["lo", "mid", "hi"]},
    }
    GOOD = {"model": "jev-1.14.0", "usage": {"input_tokens": 42, "output_tokens": 3}, "answers": {
        "a": {"type": "noul", "noul": 0.9},
        "b": {"type": "choice", "choice": "fix", "probabilities": {"ship": 0.2, "fix": 0.8}, "confidence": 0.6},
        "c": {"type": "score", "score": 1.5, "legend": {}, "probabilities": {}, "confidence": 0.7}}}
    tmp = Path(tempfile.mkdtemp(prefix="jev-selfcheck-", dir=USAGE_LOG.parent if USAGE_LOG.parent.exists() else None))
    LOG = tmp / "usage.log"

    def fake(*responses):
        calls = []

        def t(body, key):
            calls.append(body)
            r = responses[min(len(calls), len(responses)) - 1]
            if isinstance(r, Exception):
                raise r
            return r
        t.calls = calls
        return t

    def ask_(t, questions=Q, state=None, **kw):
        return ask(state or {"t": 1}, questions, key=kw.pop("key", "k"), transport=t,
                   retry_delay=0, log_path=kw.pop("log_path", LOG), **kw)

    class T(unittest.TestCase):
        def test_success_parses_all_types(self):
            r = ask_(fake((200, GOOD)))
            self.assertFalse(r["degraded"])
            self.assertEqual(r["status"], "ok")
            self.assertEqual(r["answers"]["a"]["noul"], 0.9)
            self.assertEqual(r["answers"]["b"]["choice"], "fix")
            self.assertEqual(r["answers"]["c"]["score"], 1.5)
            self.assertEqual(r["model"], "jev-1.14.0")
            self.assertEqual(r["usage"]["input_tokens"], 42)

        def test_401_degrades_without_retry(self):
            t = fake((401, {"detail": "bad key"}))
            r = ask_(t)
            self.assertEqual(len(t.calls), 1)
            self.assertTrue(r["degraded"])
            self.assertIn("401", r["error"])

        def test_422_degrades_without_retry(self):
            t = fake((422, {"detail": [{"loc": ["body"], "msg": "bad"}]}))
            r = ask_(t)
            self.assertEqual(len(t.calls), 1)
            self.assertIn("422", r["error"])

        def test_429_then_success_retries_once(self):
            t = fake((429, {}), (200, GOOD))
            r = ask_(t)
            self.assertEqual(len(t.calls), 2)
            self.assertFalse(r["degraded"])

        def test_5xx_twice_degrades_after_one_retry(self):
            t = fake((529, {}), (529, {}), (200, GOOD))
            r = ask_(t)
            self.assertEqual(len(t.calls), 2)
            self.assertTrue(r["degraded"])
            self.assertIn("529", r["error"])

        def test_timeout_retries_then_degrades(self):
            t = fake((0, {"_error": "timeout"}), (0, {"_error": "timeout"}))
            r = ask_(t)
            self.assertEqual(len(t.calls), 2)
            self.assertIn("timeout", r["error"])

        def test_transport_exception_never_raises(self):
            t = fake(ConnectionResetError(), ConnectionResetError())
            r = ask_(t)
            self.assertTrue(r["degraded"])
            self.assertEqual(len(t.calls), 2)

        def test_wrong_answer_type_degrades(self):
            bad = json.loads(json.dumps(GOOD))
            bad["answers"]["a"] = {"type": "noul", "noul": "0.9"}
            self.assertIn("bad noul", ask_(fake((200, bad)))["error"])
            bad["answers"]["a"] = {"type": "choice", "choice": "x"}
            self.assertIn("missing answer", ask_(fake((200, bad)))["error"])
            ok = json.loads(json.dumps(GOOD))
            ok["answers"]["b"]["choice"] = "unlisted"
            self.assertIn("bad choice", ask_(fake((200, ok)))["error"])
            ok = json.loads(json.dumps(GOOD))
            ok["answers"]["c"]["score"] = True
            self.assertIn("bad score", ask_(fake((200, ok)))["error"])

        def test_missing_answer_degrades(self):
            r = ask_(fake((200, {"answers": {"a": {"type": "noul", "noul": 0.1}}})))
            self.assertTrue(r["degraded"])
            self.assertIn("missing answer", r["error"])

        def test_missing_key_never_calls(self):
            t = fake((200, GOOD))
            r = ask_(t, key="")
            self.assertEqual(len(t.calls), 0)
            self.assertIn("no TypeSafe API key", r["error"])

        def test_redaction_failure_never_sends(self):
            t = fake((200, GOOD))
            r = ask_(t, state={"bad": {1, 2}})
            self.assertEqual(len(t.calls), 0)
            self.assertIn("redaction failed", r["error"])

        def test_body_is_redacted_and_model_pinned(self):
            t = fake((200, {"answers": {"a": {"type": "noul", "noul": 0.5}}}))
            ask_(t, questions={"a": Q["a"]},
                 state={"item": {"body": "token ghp_abcdefghijklmnopqrstuvwxyz0123 in ticket",
                                 "password": "abcdefghijklmnop1234"}})
            text = json.dumps(t.calls[0])
            self.assertNotIn("ghp_abcdef", text)
            self.assertIn("ghp_[REDACTED]", text)
            self.assertNotIn("abcdefghijklmnop1234", text)
            self.assertEqual(t.calls[0]["model"], "jev-latest")

        def test_redaction_rules(self):
            cases = [
                ("key sk-ant-abcdefghijklmnopqrstuv", "sk-ant-[REDACTED]"),
                ("tok ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_[REDACTED]"),
                ("jwt eyJhbGciOiJI.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "[REDACTED_JWT]"),
                ("db postgres://user:hunter2secret@db.example.com/x", "postgres://user:[REDACTED]@"),
                ("password=abcdefghijklmnop1234", "password=[REDACTED]"),  # fake credential
                ("AKIAABCDEFGHIJKLMNOP", "AKIA[REDACTED]"),
                ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz", "Bearer [REDACTED]"),
                ("xoxb-1234567890-abc", "xoxb-[REDACTED]"),
            ]
            for inp, exp in cases:
                self.assertIn(exp, redact(inp), inp)
            plain = 'Fix drawer route in apps/web\nsecond line with "quotes"'
            self.assertEqual(redact(plain), plain)
            out = redact_strings({"t": "Rotate key", "n": [{"x": "Bearer abcdefghijklmnopqrstuvwxyz", "line": 12}]})
            self.assertEqual(out["t"], "Rotate key")
            self.assertEqual(out["n"][0]["line"], 12)
            self.assertEqual(out["n"][0]["x"], "Bearer [REDACTED]")

        def test_redaction_parity_with_jp_jq(self):
            found = sorted(Path.home().glob("ai-workspace/projects/*/.agents/skills/do-shit/scripts/lib/redact.jq"))
            if not found:
                self.skipTest("do-shit redact.jq not present")
            jq_dir = found[0].parent
            samples = ["key sk-ant-abcdefghijklmnopqrstuv x", "sk-proj-abcdefghijklmnopqrstuvwxyz12",
                       "github_pat_abcdefghijklmnopqrstuvwxyz0123456789", "glpat-abcdefghijklmnop",
                       "ASIAABCDEFGHIJKLMNOP", "sb_secret_abcdefghijklmnopqrstu", "rnd_abcdefghijklmnopqrstu",
                       "npm_abcdefghijklmnopqrstuvwxyz012345", "mongodb+srv://u:p4ss@h/x",
                       'api_key: "abcdefghijklmnopqr"', "nothing secret here", "bearer   abcdefghijklmnopqrstuv"]
            for s in samples:
                jq = subprocess.run(["jq", "-Rjs", "-L", str(jq_dir), 'include "redact"; redact'],
                                    input=s, capture_output=True, text=True, check=True).stdout
                self.assertEqual(redact(s), jq, s)

        def test_phi_redacted_before_send(self):
            cases = [  # (state, raw values that must never be sent, placeholder that must be)
                ("rider 123-45-6789 called", ["123-45-6789"], "[SSN_1]"),
                ({"note": "from jane.doe@example.com"}, ["jane.doe"], "[EMAIL_1]"),
                ("call back at (405) 555-0142", ["555-0142"], "[PHONE_1]"),
                ("DOB 1/2/1980, needs pickup", ["1/2/1980"], "DOB [DOB_1]"),
                ("date of birth: 01/02/1980", ["1980"], "[DOB_1]"),
                ("d.o.b. 1980-01-02", ["1980"], "[DOB_1]"),
                ({"t": "Medicaid ID: OK123456789 on file"}, ["OK123456789"], "[MEDICAID_ID_1]"),
                ("member id is W2X88812", ["W2X88812"], "[MEMBER_ID_1]"),
                ("MRN# 00412233", ["00412233"], "[MRN_1]"),
                ("diagnosis: major depressive disorder; ride at 9", ["depressive"], "[DIAGNOSIS_1]"),
                ("coded F32.9 at intake", ["F32.9"], "[ICD10_1]"),
                ("Patient name: Jane Doe, wheelchair", ["Jane Doe"], "[PATIENT_NAME_1]"),
                ({"rider_name": "Jane Doe"}, ["Jane Doe"], "[RIDER_NAME_1]"),
                ({"ride": {"patient": {"id": 98765, "name": "Jane Doe"}}}, ["98765", "Jane Doe"], "[PATIENT_1]"),
                ([{"pickup_address": "12 Elm St"}], ["Elm"], "[PICKUP_ADDRESS_1]"),
                ({"riderEmail": "j@x.org"}, ["j@x.org"], "[EMAIL_1]"),
                ({"memberId": "W2X88812"}, ["W2X88812"], "[MEMBER_ID_1]"),
                ({"dob": "1980-01-02"}, ["1980"], "[DOB_1]"),
            ]
            for st, raw, tok in cases:
                t = fake((200, GOOD))
                r = ask_(t, state=st)
                self.assertFalse(r["degraded"], (st, r.get("error")))
                self.assertEqual(len(t.calls), 1)
                sent = json.dumps(t.calls[0])
                for v in raw:
                    self.assertNotIn(v, sent, st)
                self.assertIn(tok, sent, st)
                self.assertTrue(r["phi_redacted"], st)
                self.assertNotIn(raw[0], json.dumps(r))  # the result never carries the value either

        def test_phi_placeholders_are_consistent(self):
            st = {"a": "call (405) 555-0142 or 405.555.0142", "b": "jane@x.org wrote; cc jane@x.org and bob@x.org",
                  "notes": ["Member ID: W1 then member id W1"]}
            s2, _, counts = phi_redact(st)
            self.assertEqual(s2["a"], "call [PHONE_1] or [PHONE_1]")
            self.assertEqual(s2["b"], "[EMAIL_1] wrote; cc [EMAIL_1] and [EMAIL_2]")
            self.assertEqual(s2["notes"][0], "Member ID: [MEMBER_ID_1] then member id [MEMBER_ID_1]")
            self.assertEqual(counts, {"PHONE": 1, "EMAIL": 2, "MEMBER_ID": 1})
            self.assertEqual(phi_redact(st)[0], s2)  # deterministic: same input, same request

        def test_phi_redaction_in_questions_and_keys(self):
            q = {"a": {"type": "noul", "instructions": "Did jane@x.org confirm? Does it contain a date of birth?"}}
            s2, q2, _ = phi_redact({"jane@x.org": 1}, q)
            self.assertEqual(list(s2), ["[EMAIL_1]"])
            self.assertEqual(q2["a"]["instructions"], "Did [EMAIL_1] confirm? Does it contain a date of birth?")
            self.assertEqual(q2["a"]["type"], "noul")

        def test_ordinary_state_passes_unchanged(self):
            ok = ["Your invoice from Acme Hosting is ready", {"commit_summary": "split harness.py into a package"},
                  {"ride_type": "crisis", "payer_class": "medicaid_mco", "miles_band": "10-30"},
                  "version 1.14.0 shipped 2026-11-05", "order #1234567890 total $41,048.50",
                  {"email_subject": "Re: Q3 numbers", "sender_domain": "example.com"},
                  {"file_name": "a.py", "phone_type": "mobile", "address_count": 2, "payer_name": "Aetna"},
                  "Medicaid ID on file is wrong", "Does this record contain a diagnosis?", {"dob": None}]
            for st in ok:
                s2, _, counts = phi_redact(st)
                self.assertEqual(s2, st, st)
                self.assertEqual(counts, {}, st)
            r = ask_(fake((200, GOOD)), state=ok[0])
            self.assertEqual((r["degraded"], r["phi_redacted"]), (False, {}))

        def test_resolve_key_from_env_file_both_names(self):
            f = tmp / "env"
            f.write_text("OTHER=1\nexport TYPESAFE_JEV_API_KEY='abc123'\n")
            self.assertEqual(resolve_key(env={}, env_file=f), "abc123")
            self.assertEqual(resolve_key(env={"TYPESAFE_API_KEY": "zz"}, env_file=f), "zz")
            self.assertEqual(resolve_key(env={}, env_file=tmp / "missing"), "")

        def test_usage_log_has_no_state(self):
            log = tmp / "u2.log"
            ask_(fake((200, GOOD)), state={"note": "Jane Example"}, log_path=log)
            line = log.read_text()
            self.assertIn("a,b,c", line)
            self.assertIn("\t42\tok", line)
            self.assertNotIn("Jane", line)

        def test_run_applies_threshold_in_code(self):
            qs = [{"id": "a", "type": "noul", "instructions": "x", "threshold": 0.95},
                  {"id": "c", "type": "score", "instructions": "z", "criteria": ["lo", "mid", "hi"], "threshold": 0.7},
                  {"id": "b", "type": "choice", "instructions": "y", "criteria": {"ship": "s", "fix": "f"}}]
            t = fake((200, GOOD))
            r = run({"t": 1}, qs, key="k", transport=t, log_path=LOG)
            self.assertEqual(r["decisions"], {"a": False, "c": True, "b": "fix"})
            self.assertNotIn("threshold", json.dumps(t.calls[0]["questions"]))
            self.assertNotIn('"id"', json.dumps(t.calls[0]["questions"]))

        def test_bad_question_file_degrades(self):
            r = run({}, [{"id": "a", "type": "bogus", "instructions": "x"}], key="k", transport=fake((200, GOOD)))
            self.assertTrue(r["degraded"])

        def test_sweep_matches_known_answer(self):
            pts = [{"p": 0.9, "y": True}, {"p": 0.7, "y": True}, {"p": 0.4, "y": False}, {"p": 0.2, "y": False}]
            b = sweep(pts)
            self.assertEqual((b["f1"], b["accuracy"]), (1.0, 1.0))
            self.assertEqual(b["plateau"], [0.45, 0.7])
            self.assertEqual(b["threshold"], 0.55)

        def test_eval_scores_and_caches(self):
            qs = [{"id": "a", "type": "noul", "instructions": "x", "threshold": 0.5}]
            cases = [{"id": f"c{i}", "state": f"s{i}", "expected": {"a": i % 2 == 0}} for i in range(4)]

            def t(body, key):
                t.n += 1
                p = 0.8 if body["state"] in ("s0", "s2") else 0.3
                return 200, {"answers": {"a": {"type": "noul", "noul": p}}, "usage": {"input_tokens": 10}}
            t.n = 0
            cache = tmp / "cache.json"
            r = run_eval(cases, qs, cache_path=cache, key="k", transport=t, log_path=LOG)
            self.assertEqual(r["report"]["a"]["accuracy_at_file_threshold"], 1.0)
            self.assertEqual((r["api_calls"], r["input_tokens"]), (4, 40))
            r2 = run_eval(cases, qs, cache_path=cache, key="k", transport=t, log_path=LOG)
            self.assertEqual((t.n, r2["api_calls"]), (4, 0))

        def test_confidence_sweep_known_answer(self):
            pts = [{"p": 1.0, "conf": 0.9}, {"p": 1.0, "conf": 0.75}, {"p": 0.0, "conf": 0.55}, {"p": 0.0, "conf": 0.3}]
            rows = {r["min_confidence"]: r for r in confidence_sweep(pts)}
            self.assertEqual((rows[0.0]["coverage"], rows[0.0]["accuracy"]), (1.0, 0.5))
            self.assertEqual((rows[0.7]["coverage"], rows[0.7]["accuracy"]), (0.5, 1.0))
            self.assertEqual(rows[0.9]["coverage"], 0.25)

        def test_endpoint_not_env_overridable(self):
            src = Path(__file__).read_text()
            self.assertIn('API_URL = "https://api.typesafe.ai/v1/systemone"', src)
            self.assertNotRegex(src, r"API_URL\s*=\s*os\.")

    try:
        res = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print("self-check OK" if res.wasSuccessful() else "self-check FAILED", file=sys.stderr)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    main()
