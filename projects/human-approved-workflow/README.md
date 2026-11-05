# Human-approved workflow: refunds with an approval gate

A support agent asks for a refund. The system must check the request against policy, draft a
confirmation email, get a **person** to approve it (and perhaps edit it), then issue the refund and
send the email — exactly once, with a record of who decided what, and able to pick up where it left
off after a crash.

You will build that as a deterministic **workflow**: explicit steps over explicit, serialisable
state, an approval gate before anything irreversible happens, idempotent side effects, a
hash-chained audit log and JSON checkpoints. Standard library only.

```text
 validate ─► check_policy ─► draft ─► [approval gate] ─► issue_refund ─► send_email ─► done
     │             │                       │    ▲
     └─ rejected ◄─┘            reject ◄───┘    └─ approve (optionally editing the draft)

 after every step:  state ──► checkpoint.json (atomic)      every event: audit log (hash chain)
```

## Why a workflow and not an agent?

An agent lets a model decide which action to take next. That is valuable when the path cannot be
known in advance — open-ended research, debugging, exploring an unfamiliar system. A refund is the
opposite: the steps are known, their order is fixed, and two of them move money and send messages
to a customer. Here a workflow wins on every axis that matters:

| | workflow (this project) | agent with refund and email tools |
|---|---|---|
| **Control flow** | Code decides; the approval gate cannot be skipped | The model decides; a prompt injection or a bad plan could call `refund` before (or without) approval |
| **Side effects** | Run once, only for the approved text, with idempotency keys | Depend on the model calling tools in the right order with the right arguments, every time |
| **Auditability** | Every transition is an audit entry with actor and time | You can log tool calls, but *why* the model chose them is not inspectable |
| **Testability** | Deterministic: the same input gives the same steps; 48 fast tests | Non-deterministic; needs evaluation suites and still surprises you |
| **Cost and latency** | One model call at most (drafting), or none | A model call per step, plus retries |
| **Resumability** | State is a small JSON document | State is a conversation transcript; replaying it is fragile |

The language model still has a job — **drafting** the email text — but it is confined to a step
whose output is validated (amount, order id, no header injection) and then reviewed by a person. That
is the general pattern: *use models inside steps, not to choose the steps*, unless the steps genuinely
cannot be known in advance. If refunds needed open-ended investigation (reading order histories,
chatting with the customer), you might give an agent *read-only* tools for that part and still keep the
approval gate and the side effects in a workflow. See the
[tool-using assistant](../tool-using-assistant/README.md) project for the agent side.

## What you will learn

* Modelling a process as explicit state (`status`, `next_step`) and small step functions.
* Human-in-the-loop design: a gate that pauses the workflow, approvals that can edit, rejections with
  reasons, and authorised approvers only.
* "What was approved is what gets sent": fingerprints (SHA-256) bind the approval to the exact text.
* Idempotency keys so retries and resumes never refund or email twice — including the nasty case where
  the email left but the call timed out.
* Append-only, hash-chained audit logs, and atomic checkpoints that are verified on load.

## Setup

Python 3.11 or newer; only `pytest` is needed.

Windows (PowerShell):

```powershell
cd projects\human-approved-workflow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pytest
```

macOS / Linux:

```bash
cd projects/human-approved-workflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pytest
```

## Running the tests

```powershell
python -m pytest                    # your code in starter/
python -m pytest -k Milestone2      # one milestone
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # the reference solution
```

```bash
GW_TARGET=solution python -m pytest
```

Run the demo: `python solution/approval_workflow.py` (add `--folder out` to keep the checkpoint file
and inspect it).

## Milestones

Work in `starter/approval_workflow.py`; each milestone has a test class.

1. **Validation and policy** — `format_money`, `validate_request` (shape), `check_refund_policy`
   (order exists, same customer, not more than paid, inside the window, under the cap).
2. **State and the gate** — `Draft.fingerprint`, `TemplateDrafter`, `validate_draft`, the audit log
   (`audit_hash`, `append_audit`, `verify_audit`), `WorkflowState.to_dict/from_dict`,
   `RefundWorkflow.start` and `run` up to the approval gate, rejecting invalid or out-of-policy requests
   and replacing unusable drafts.
3. **The approval gate** — `approve` (optional edits, re-validated; fingerprint recorded) and
   `reject` (reason required); only at the gate, only by listed approvers.
4. **Side effects** — `issue_refund` and `send_email`: only for the approved fingerprint, with
   idempotency keys `"{workflow_id}:refund"` / `"{workflow_id}:email"`; a failing step raises
   `StepFailedError`, records the error and can simply be run again.
5. **Checkpoints and resume** — `save_checkpoint` (temp file + `os.replace`), `load_checkpoint`
   (version, shape, audit chain, consistency checks), `RefundWorkflow.resume`. The tests tamper with
   the JSON (amount, audit entries, the draft, the approval) and simulate a crash after the email left.

## The state, as JSON

```json
{
  "schema_version": 1,
  "state": {
    "workflow_id": "wf-1",
    "status": "awaiting_approval",
    "next_step": "approval",
    "request": {"order_id": "ORD-1001", "amount_cents": 1250, "customer_email": "sam@example.com", "...": "..."},
    "draft": {"subject": "Your refund for order ORD-1001", "body": "Dear Sam Lee, ..."},
    "approval": null, "refund_id": null, "message_id": null,
    "audit": [{"seq": 1, "at": "2026-10-22T09:00:00+00:00", "actor": "system", "event": "received",
               "details": {"...": "..."}, "prev_hash": "000...", "hash": "4f1c..."}]
  }
}
```

## Optional: drafting with a local model

`OllamaDrafter` asks a local model (via Ollama's HTTP API, `urllib`, localhost only) for
`{"subject", "body"}` JSON. Install Ollama, run `ollama pull llama3.2` (about 2 GB; 8 GB RAM is
comfortable), then `python solution/approval_workflow.py --ollama llama3.2`. Drafts that fail
validation are replaced by the template and the replacement is audited. Tests never need it.

## Design notes

* **The gate is structural.** `run()` stops at `approval`; side-effect steps re-check the approval
  fingerprint themselves, so even a bug elsewhere cannot send unapproved text.
* **Failures leave the state resumable.** `next_step` only moves forward after a step succeeds, so
  "run it again" is always the recovery action — and idempotency keys make that safe.
* **Time is injected.** `Services.clock` is a function; tests use `FakeClock`, so audit timestamps are
  predictable.

## Security notes

* Approvals are bound to content by a SHA-256 fingerprint, and the checkpoint is cross-checked against
  the hash-chained audit log on load. A plain hash chain detects edits but not an attacker who rewrites
  the whole chain; in production, sign entries (HMAC with a server-side key) or ship them to append-only
  storage.
* Email subjects are single-line (CR/LF would allow header injection), and drafts must contain the exact
  amount and order id, so neither a model nor a tired human can silently change what the customer is told.
* The refund amount and customer come from the request and the order system, never from the model.
* Checkpoints contain personal data (names, emails): keep them out of version control and restrict access.
