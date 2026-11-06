---
name: decision-model
description: "Use when code asks one closed question many times (classify, route, triage, tag), before regex or an LLM."
template: skill-definition
version: 0.4.1
summary: "When and how to use a lightweight decision model (Jev, TypeSafe) instead of an LLM call or hand judgment: fixed-answer questions asked many times or inside a script. Calls go through team-lib/executions/jev_client.py (ask, inline ask, eval to calibrate thresholds). Covers question writing, calibration on 20+ labelled cases, degraded fallback, the no-PHI data rule, cost and speed."
created: 2026-11-05
last_updated: 2026-11-06
maintainer: pvragon
listing: on
category: ai-tooling
dependencies: [executions/jev_client.py]
---

# Decision model: when to use Jev, and how to call it

Jev is TypeSafe's typed decision model. It reads a state (text or JSON) plus typed questions with fixed answers and returns a probability for each answer. A call takes about 70 to 500 ms; the smoke test measured about 0.2 s end to end. Input costs about $0.042 per million tokens (a third-party figure, not confirmed on TypeSafe's own page) and output is free. A typical question uses 300 to 500 input tokens. The workspace owner's view (2026-11-04): decision models are critical, and we should use more of them.

Code owns every decision. Jev answers with a probability, and the caller's code compares it to a threshold, applies vetoes and handles failure. This is the pattern a teammate built into the `/do-shit` agent harness (`<project>/.agents/skills/do-shit/`), and this skill and the client copy it.

## Use one for

- A fixed-answer question asked many times, or asked inside a script or loop: classification, routing, triage, tagging, email sorting.
- Guardrails: "does this text ask for a destructive action?", "does this diff touch auth?".
- The leftovers of a deterministic parser: the cases regex or rules could not settle, for example card-text rules that a regex parser and a reference engine disagree on.
- Cheap pre-filtering before an expensive step (an LLM call, a human review, an API with a quota).

## Do not use one for

- Open-ended judgment, writing, or anything without a short fixed set of answers.
- A fact the data already holds deterministically. Query the data instead.
- A one-off decision I can make in-session. Reading it myself is cheaper than writing the question.
- Anything where a wrong answer costs money or reaches a payer, a client or production data, until a calibration run (below) shows the accuracy. Even then, code keeps the veto.

## How to call it

The client is `~/ai-workspace/team-lib/executions/jev_client.py`. It can be called from any language through the CLI, or from Python with `from executions.jev_client import run`.

```bash
J=~/ai-workspace/team-lib/executions/jev_client.py
# ad hoc, one question; state from a file or stdin (JSON, or plain text)
echo "Your invoice from Acme is ready" | python3 $J ask --state - \
  --noul "Is this email a vendor invoice?" --yes "It delivers a bill or invoice." --no "Anything else." --threshold 0.6
python3 $J ask --state s.json --choice "Which team owns this?" --option billing="money, invoices" --option ops="rides, drivers"
python3 $J ask --state s.json --score "How urgent?" --level "no action" --level "this week" --level "today"
# a question file (house shape, below)
python3 $J ask --state s.json --questions q.json
# calibrate before trusting a threshold
python3 $J eval --cases cases.jsonl --questions q.json
```

The output is JSON: `status`, `degraded`, `answers` (Jev's raw answers), `decisions` (each threshold applied in code; for a choice, the top option), `model`, `usage.input_tokens`. Exit code 0 means ok, and 1 means degraded. Each call appends one line to `my-lib/runtime/.tmp/jev-usage.log` (your personal layer): time, question ids, input tokens and ok or degraded. The log holds no state content.

The key comes from `TYPESAFE_API_KEY` or `TYPESAFE_JEV_API_KEY`, read from the environment or `~/ai-workspace/personal/secrets/.env`. It is never printed. The endpoint and model are pinned in code and cannot be changed from the environment.

## Writing a question

Use the `/do-shit` house shape. One JSON object per question, in a list:

```json
{"id": "needs_reply", "type": "noul", "threshold": 0.5,
 "instructions": "Judging only from `email_subject`, does this email need a personal reply?",
 "criteria": {"true": "A person asks something, wants a decision, or expects an answer.",
              "false": "An automated notice, receipt, report, newsletter or FYI."}}
```

- **Types:** `noul` (yes/no; the answer is a probability from 0 to 1), `choice` (`criteria` maps option names to descriptions; the answer is the top option plus a confidence), `score` (`criteria` is an ordered list of up to 10 levels; the answer is the expected level, which the client divides by the number of levels minus one to get 0 to 1).
- **Write the criteria for every answer.** A yes with no written no is the most common cause of a poor question.
- **The instructions must carry the whole meaning.** The `id` and `threshold` never reach Jev. Name the state fields in backticks, as in `` `email_subject` ``.
- **One request can carry many questions.** Batch every question about the same state into one call.

## Calibrate before trusting a threshold

Run `eval` on at least 20 labelled cases before any code acts on a threshold. Labels should come from an outside source of truth, such as what a person actually did, never from my own guess at the answer. A cases file is JSONL: `{"id": "c1", "state": ..., "expected": {"needs_reply": true}}`.

`eval` reports, for each question:
- yes/no and score questions: the accuracy at the file's threshold, and the best threshold by F1 (the middle of any tie), with the misses listed.
- choice questions: the top-choice accuracy, plus the coverage and accuracy at each confidence floor. The usual pattern is to trust Jev above a confidence floor and fall back to code below it.

Answers are cached beside the cases file, so a rerun costs nothing. Reword any question whose best accuracy is under 0.7, then rerun.

The first calibration (2026-11-05) used 30 real commit summaries with a five-way commit-type choice. Top-choice accuracy was 0.70. With a confidence floor of 0.5, Jev answered 70% of cases at 0.86 accuracy.

## How this skill gets noticed

- **The listing:** the description opens with the moment of use, and `listing: on` shows it every session.
- **A lens (optional, per agent):** an agent with a lens layer can add one that fires once per session on the first Write or Edit of classifier-shaped code: a classify, triage, route or categorize function taking text, an `is_*(text)` test, three chained keyword or regex tests, or an LLM or `claude -p` call inside a loop. Measured 2026-11-05: 11 of 11 positive snippets fire, 10 of 10 ordinary snippets stay quiet, and 23 of 3,154 real code files (0.7%) fire as whole-file writes.
- **Trigger test (2026-11-05):** 20 prompts, each run in a fresh read-only `claude -p` session. 9 of 10 fitting tasks reached for this skill (one more only globbed for it), and 0 of 10 non-fitting tasks did.

## Fallback

Every caller handles `degraded: true` with a conservative rule in code. Treat it as "Jev said nothing", never as a no. Degraded comes back for: no key, failed PHI or credential redaction (nothing sent), a timeout after one retry, a 4xx, a 5xx or 429 after one retry, or an answer of the wrong type. The client never raises.

## Data rule

- **Never send PHI or patient identifiers.** TypeSafe does not sign BAAs or support HIPAA, and Jev runs only on their hosted API, with no VPC or on-premises option (their enterprise FAQ, https://typesafe.ai/enterprise, read 2026-11-05).
- **The client pseudonymises PHI in real time.** Before anything is sent, `jev_client.py` replaces identifiers with placeholders: SSNs, email addresses, phone numbers and ICD-10 codes anywhere; the value after a DOB, MRN, member ID, Medicaid ID, subscriber ID or policy number label; the phrase after a patient-name or diagnosis label; and the whole value of a patient-record field (`patient`, `dob`, `rider_name`, `first_name`, `pickup_address`, `riderEmail` and the like). The same value always gets the same placeholder within a request (`[EMAIL_1]` twice means the same address), so Jev can still tell people apart. The map back to real values never leaves the process. The result reports counts by kind in `phi_redacted`, never the values. If anything survives the redaction, nothing is sent.
- **It cannot see everything.** A bare name or street address in unlabelled free text gets through, so reduce healthcare client records to non-identifying fields before calling (ride type, payer class, mileage band). The redaction is the backstop, not the method.
- **Credential redaction is separate.** It strips API keys, tokens, JWTs and database passwords from whatever is sent.
- **Sending a person's private data needs their say.** On 2026-11-05 the auto-mode classifier blocked an eval that sent the owner's inbox subject lines to TypeSafe as data exfiltration. A use on someone's mail, documents or messages needs that person's explicit go-ahead, plus a permission rule if it runs unattended.

## Alternatives: local models, for PHI

Jev has no BAA, so a decision on PHI needs a model running on our own hardware. None is built. Figures below come from the model cards and vendor docs (2026-11-06), not our own tests.

- **Laya** (Convai, Apache-2.0, about 0.4B parameters): runs on CPU, 4 to 5 GB of RAM, well under a second per call after a 10 to 20 s load. Unsloth serves it on the same `/v1/systemone` API as Jev. Jev thresholds do not carry over: recalibrate with `eval`.
- **Kev-9B** (Apache-2.0, a LoRA adapter plus a pointer head on Qwen3.5-9B): needs about 22 GB of GPU memory in bf16 on CUDA (one L40S or H100), and implements the same API. On its own card it trails Jev on held-out tests (0.698 vs 0.757). The card lists no quantized build. Smaller Kev checkpoints (0.8B, 4B) exist.
- **Clef** (Cloudflare): open, multimodal, same request format. Its hardware needs are unverified.

The client's endpoint is pinned to TypeSafe on purpose. A local model would get its own pinned local endpoint; never make the URL configurable from the environment.
