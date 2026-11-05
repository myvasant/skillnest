"""A human-approved refund workflow: explicit steps, an approval gate, an audit log and checkpoints.

A support agent asks for a refund; the system must check the request against policy, draft a
confirmation email, get a **person** to approve (and possibly edit) it, then issue the refund and send
the email — exactly once, even if the process crashes half-way.

This is deliberately a **workflow, not an agent**. The path is known in advance, so the code — not a
model — decides what happens next:

```text
 validate ─► check_policy ─► draft ─► [approval gate] ─► issue_refund ─► send_email ─► done
     │             │                       │    ▲
     └─ rejected ◄─┘            reject ◄───┘    └─ approve (optionally editing the draft)
```

The ideas you will see in the code:

* **Explicit state** (:class:`WorkflowState`): every fact the workflow knows lives in one serialisable
  object — ``status`` and ``next_step`` say exactly where it is. Nothing important hides in local
  variables or in a model's context window.
* **An approval gate**: :meth:`RefundWorkflow.run` stops at ``approval`` and returns. Only
  :meth:`~RefundWorkflow.approve` or :meth:`~RefundWorkflow.reject` can move it on, and the side-effect
  steps refuse to run unless the draft they are about to send is the one that was approved
  (compared by a SHA-256 fingerprint).
* **Idempotency**: the refund and the email carry idempotency keys derived from the workflow id, so a
  resumed or repeated step cannot pay or email twice.
* **An append-only, hash-chained audit log** (:class:`AuditEntry`): who did what, when. Each entry
  includes the hash of the previous one, so editing history breaks the chain.
* **Checkpoints**: after every step the state is written atomically to JSON; :meth:`RefundWorkflow.resume`
  continues from the file in a brand-new process.

The "model" that drafts emails is :class:`TemplateDrafter` (deterministic). :class:`OllamaDrafter` is an
optional adapter for a local model; its drafts are validated exactly like a person's edits.

PROVIDED: the data classes, the fake payment gateway and mailer, :class:`FakeClock`, :class:`Services`,
the workflow's constructor and small helpers (``_audit``, ``_save``, ``_finish_rejected``,
``_draft_or_fail``), the optional Ollama drafter and the demo. Everything that raises
``NotImplementedError("TODO")`` is yours; the docstrings say exactly what the tests expect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

SCHEMA_VERSION = 1


class WorkflowError(Exception):
    """An operation that is not allowed in the workflow's current state."""


class CheckpointError(WorkflowError):
    """A checkpoint file is missing, unreadable, from another version, or has been tampered with."""


class StepFailedError(WorkflowError):
    """A step raised an exception. The state was saved; fix the cause and resume."""


# ==================================================================================================
# Milestone 1: the request, the policy and validation
# ==================================================================================================


@dataclass(frozen=True)
class RefundRequest:
    """What the support agent submits. Money is in integer cents to avoid float rounding."""

    request_id: str
    order_id: str
    customer_name: str
    customer_email: str
    amount_cents: int
    reason: str


@dataclass(frozen=True)
class Order:
    """What the order system knows about an order (looked up, never taken from the request)."""

    order_id: str
    customer_email: str
    total_cents: int
    days_since_purchase: int


@dataclass(frozen=True)
class RefundPolicy:
    """Business rules: refunds above the cap or outside the window are refused."""

    max_refund_cents: int = 50_000
    refund_window_days: int = 30


ORDER_ID_PATTERN = re.compile(r"ORD-\d{4,10}")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")
MAX_NAME_LENGTH = 100
MAX_REASON_LENGTH = 500


def format_money(cents: int) -> str:
    """``1250 -> '12.50'`` — exact, because cents are integers."""
    raise NotImplementedError("TODO")


def validate_request(request: RefundRequest) -> list[str]:
    """Problems with the request's *shape* (empty list = valid). Policy comes later.

    One message per bad field, each naming the field: ``order_id`` (must match ``ORD-`` + 4-10 digits),
    ``customer_name`` (one line, 1-100 characters after stripping), ``customer_email``,
    ``amount_cents`` (a positive ``int``, not a bool or float) and ``reason`` (1-500 characters).
    """
    raise NotImplementedError("TODO")


def check_refund_policy(request: RefundRequest, order: Order | None, policy: RefundPolicy) -> list[str]:
    """Problems with the refund under the business rules (empty list = allowed).

    Messages, in this order: ``"order ORD-1 does not exist"`` (only this one if the order is missing),
    ``"the order belongs to a different customer"`` (emails compared case-insensitively),
    ``"refund 60.00 is more than the order total 49.99"``,
    ``"the order is 45 days old; the refund window is 30 days"``,
    ``"refunds above 500.00 need the manual process"``.
    """
    raise NotImplementedError("TODO")


# ==================================================================================================
# Milestone 2: drafts, the audit log, state, and running to the approval gate
# ==================================================================================================

MAX_SUBJECT_LENGTH = 120
MAX_BODY_LENGTH = 2000


@dataclass(frozen=True)
class Draft:
    """An email draft."""

    subject: str
    body: str

    def fingerprint(self) -> str:
        """SHA-256 of the exact text: proves later that what is sent is what was approved."""
        raise NotImplementedError("TODO")


class Drafter(Protocol):
    """Anything that writes a draft for a request (a template, or a language model)."""

    def draft(self, request: RefundRequest) -> Draft: ...


class TemplateDrafter:
    """A deterministic drafter — the stand-in for a language model in tests."""

    def draft(self, request: RefundRequest) -> Draft:
        """Fill in the confirmation template."""
        raise NotImplementedError("TODO")


def validate_draft(draft: Draft, request: RefundRequest) -> list[str]:
    """Problems with a draft — applied to model drafts *and* to a person's edits alike.

    The subject must be 1-120 characters and a single line (a message mentioning "header injection"
    if it contains ``\\r`` or ``\\n``); the body 1-2000 characters, stating the amount exactly as
    :func:`format_money` writes it and mentioning the order id.
    """
    raise NotImplementedError("TODO")


GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    """One line of the audit log: who (``actor``) did what (``event``), when (``at``), with details.

    ``prev_hash`` is the previous entry's ``hash`` and ``hash`` covers this entry's fields plus
    ``prev_hash`` — a hash chain, so changing or deleting any earlier entry is detectable.
    """

    seq: int
    at: str
    actor: str
    event: str
    details: dict[str, Any]
    prev_hash: str
    hash: str


def audit_hash(seq: int, at: str, actor: str, event: str, details: Mapping[str, Any], prev_hash: str) -> str:
    """The SHA-256 of an entry's content, in a canonical JSON form."""
    raise NotImplementedError("TODO")


def append_audit(
    log: list[AuditEntry], at: str, actor: str, event: str, details: Mapping[str, Any] | None = None
) -> AuditEntry:
    """Append a new entry chained to the last one, and return it."""
    raise NotImplementedError("TODO")


def verify_audit(log: list[AuditEntry]) -> list[str]:
    """Problems with the chain (empty list = intact).

    For entry number ``i`` (from 1): ``"entry {i} has sequence number {seq}"`` if ``seq != i``;
    ``"entry {i} does not follow entry {i-1}"`` if its ``prev_hash`` is not the previous entry's stored
    ``hash`` (:data:`GENESIS_HASH` for the first); ``"entry {i} ({event}) was modified"`` if its hash
    does not match its content.
    """
    raise NotImplementedError("TODO")


Status = Literal["in_progress", "awaiting_approval", "completed", "rejected"]
STATUSES: tuple[str, ...] = ("in_progress", "awaiting_approval", "completed", "rejected")
STEPS: tuple[str, ...] = (
    "validate",
    "check_policy",
    "draft",
    "approval",
    "issue_refund",
    "send_email",
    "done",
)


@dataclass(frozen=True)
class Approval:
    """A recorded human decision to approve, with the fingerprint of exactly what was approved."""

    approver: str
    at: str
    note: str
    edited_fields: tuple[str, ...]
    fingerprint: str


@dataclass
class WorkflowState:
    """Everything the workflow knows. ``status`` + ``next_step`` say where it is; it all fits in JSON."""

    workflow_id: str
    request: RefundRequest
    status: Status = "in_progress"
    next_step: str = "validate"
    draft: Draft | None = None
    approval: Approval | None = None
    refund_id: str | None = None
    message_id: str | None = None
    rejection_reason: str | None = None
    last_error: str | None = None
    audit: list[AuditEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON-compatible data."""
        raise NotImplementedError("TODO")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowState:
        """Rebuild a state from :meth:`to_dict` output, raising :class:`CheckpointError` on a bad shape."""
        raise NotImplementedError("TODO")


# ==================================================================================================
# Milestone 4: side-effect services (fakes provided) — and the clock
# ==================================================================================================


class PaymentGateway(Protocol):
    """Issues refunds. Must honour idempotency keys: the same key returns the same refund."""

    def refund(self, order_id: str, amount_cents: int, idempotency_key: str) -> str: ...


class Mailer(Protocol):
    """Sends emails. Must honour idempotency keys: the same key never sends twice."""

    def send(self, to: str, subject: str, body: str, idempotency_key: str) -> str: ...


class FakePaymentGateway:
    """An in-memory payment service that dedupes by idempotency key, and can fail on demand."""

    def __init__(self, fail_times: int = 0) -> None:
        self.refunds: list[dict[str, Any]] = []
        self.calls = 0
        self.fail_times = fail_times
        self._by_key: dict[str, str] = {}

    def refund(self, order_id: str, amount_cents: int, idempotency_key: str) -> str:
        """Refund once per key; raise ``ConnectionError`` while ``fail_times`` remain."""
        self.calls += 1
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("payment service unavailable")
        refund_id = f"re_{len(self.refunds) + 1:04d}"
        self.refunds.append({"id": refund_id, "order_id": order_id, "amount_cents": amount_cents})
        self._by_key[idempotency_key] = refund_id
        return refund_id


class FakeMailer:
    """An in-memory outbox that dedupes by idempotency key.

    ``fail_times`` makes the next sends fail *before* sending. ``fail_after_send`` makes the next send
    deliver the message and then time out — the nasty case where the caller cannot know it worked.
    """

    def __init__(self, fail_times: int = 0, fail_after_send: bool = False) -> None:
        self.outbox: list[dict[str, str]] = []
        self.calls = 0
        self.fail_times = fail_times
        self.fail_after_send = fail_after_send
        self._by_key: dict[str, str] = {}

    def send(self, to: str, subject: str, body: str, idempotency_key: str) -> str:
        """Send once per key."""
        self.calls += 1
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("mail server unavailable")
        message_id = f"msg_{len(self.outbox) + 1:04d}"
        self.outbox.append({"id": message_id, "to": to, "subject": subject, "body": body})
        self._by_key[idempotency_key] = message_id
        if self.fail_after_send:
            self.fail_after_send = False
            raise TimeoutError("no reply from the mail server (the message was in fact sent)")
        return message_id


def utc_now() -> str:
    """The real clock, as an ISO 8601 string (tests use :class:`FakeClock` instead)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class FakeClock:
    """A deterministic clock: each call returns a time ``step_seconds`` later than the previous one."""

    def __init__(self, start: str = "2026-10-22T09:00:00+00:00", step_seconds: int = 60) -> None:
        self._next = datetime.fromisoformat(start)
        self._step = timedelta(seconds=step_seconds)

    def __call__(self) -> str:
        now = self._next
        self._next += self._step
        return now.isoformat(timespec="seconds")


@dataclass
class Services:
    """Everything the workflow talks to, injected so tests can use fakes."""

    orders: Mapping[str, Order]
    payments: PaymentGateway
    mailer: Mailer
    approvers: frozenset[str]
    drafter: Drafter = field(default_factory=TemplateDrafter)
    clock: Callable[[], str] = utc_now
    policy: RefundPolicy = field(default_factory=RefundPolicy)


# ==================================================================================================
# Milestone 5: checkpoints
# ==================================================================================================


def save_checkpoint(state: WorkflowState, path: Path) -> None:
    """Write the state atomically: a temporary file in the same folder, then ``os.replace``.

    A crash mid-write leaves the previous checkpoint intact instead of a half-written file.
    """
    raise NotImplementedError("TODO")


def check_consistency(state: WorkflowState) -> list[str]:
    """Cross-check the state against its (hash-chained) audit log.

    The request and the approval fingerprint must match what the log recorded, so editing the amount
    or swapping the approved draft in the JSON file is caught on load. Problems: those of
    :func:`verify_audit`, plus ``"the request does not match the audit log"`` (compare the ``received``
    entry's order_id, amount_cents and customer_email) and ``"the approval does not match the audit
    log"`` (the last ``approved`` entry's fingerprint must equal ``state.approval.fingerprint``).
    """
    raise NotImplementedError("TODO")


def load_checkpoint(path: Path) -> WorkflowState:
    """Read and verify a checkpoint; raise :class:`CheckpointError` if anything is wrong.

    Messages: ``"no checkpoint at ..."``, ``"the checkpoint cannot be read (...)"`` (invalid JSON),
    ``"unsupported checkpoint version ..."``, the shape error from :meth:`WorkflowState.from_dict`, and
    ``"the checkpoint failed verification: ..."`` listing :func:`check_consistency` problems.
    """
    raise NotImplementedError("TODO")


# ==================================================================================================
# The workflow (milestones 2-5)
# ==================================================================================================


class RefundWorkflow:
    """Runs one refund through its steps, stopping at the approval gate.

    Create one with :meth:`start` or :meth:`resume`; then :meth:`run`, and at the gate
    :meth:`approve` or :meth:`reject` followed by :meth:`run` again. With ``checkpoint_path`` the state
    is saved after every step and every decision.
    """

    def __init__(self, state: WorkflowState, services: Services, checkpoint_path: Path | None = None) -> None:
        self.state = state
        self.services = services
        self.checkpoint_path = checkpoint_path
        self._steps: Mapping[str, Callable[[], None]] = {
            "validate": self._validate,
            "check_policy": self._check_policy,
            "draft": self._draft,
            "issue_refund": self._issue_refund,
            "send_email": self._send_email,
        }

    @classmethod
    def start(
        cls, request: RefundRequest, workflow_id: str, services: Services, checkpoint_path: Path | None = None
    ) -> RefundWorkflow:
        """Begin a new workflow: audit ``received`` with details ``order_id``, ``amount_cents``,
        ``customer_email`` and ``request_id`` (later used to detect tampering), then save."""
        raise NotImplementedError("TODO")

    @classmethod
    def resume(cls, checkpoint_path: Path, services: Services) -> RefundWorkflow:
        """Continue a workflow from its checkpoint (for example in a new process after a crash).

        Loads and verifies the file, audits ``resumed`` {next_step} and saves.
        """
        raise NotImplementedError("TODO")

    # ------------------------------------------------------------------ driving the workflow
    def run(self) -> WorkflowState:
        """Run steps until the workflow finishes or must wait for a person.

        Running a completed or rejected workflow raises :class:`WorkflowError` ("already ..."). Reaching
        ``approval`` sets status ``awaiting_approval``, audits ``approval_requested`` {fingerprint} and
        returns; calling ``run`` again while waiting changes nothing.

        Every step is checkpointed. If a step raises, ``last_error`` becomes ``"{step}: {Type}: {message}"``,
        ``step_failed`` {step, error: Type} is audited, the state is saved with ``next_step`` unchanged, and
        :class:`StepFailedError` (naming the step, chained ``from`` the original) is raised — resuming
        retries that step. A step that succeeds clears ``last_error``.
        """
        raise NotImplementedError("TODO")

    def approve(
        self, approver: str, *, subject: str | None = None, body: str | None = None, note: str = ""
    ) -> WorkflowState:
        """Approve the draft at the gate, optionally editing its subject and/or body first.

        Edits are validated like any draft; an invalid edit raises :class:`WorkflowError` and changes
        nothing. A real change audits ``draft_edited`` {fields, fingerprint}; then ``approved``
        {note, fingerprint} is audited and the :class:`Approval` records the approver, that entry's time,
        the note, the edited fields and the fingerprint of the final text. Status becomes ``in_progress``
        with next step ``issue_refund`` — nothing is refunded or sent until :meth:`run`.
        """
        raise NotImplementedError("TODO")

    def reject(self, approver: str, reason: str) -> WorkflowState:
        """Reject at the gate. A (stripped, non-empty) reason is required; nothing is refunded or sent."""
        raise NotImplementedError("TODO")

    # ------------------------------------------------------------------ steps
    def _validate(self) -> None:
        """Step ``validate``: reject (``"invalid request: ..."``) or audit ``validated``.

        Next step: ``check_policy``.
        """
        raise NotImplementedError("TODO")

    def _check_policy(self) -> None:
        """Step ``check_policy``: look the order up; reject (``"policy: ..."``) or audit ``policy_passed``."""
        raise NotImplementedError("TODO")

    def _draft(self) -> None:
        """Step ``draft``: ask the drafter; an invalid draft is audited (``draft_replaced``) and replaced
        by the template. Audit ``drafted`` {fingerprint} -> ``approval``."""
        raise NotImplementedError("TODO")

    def _issue_refund(self) -> None:
        """Step ``issue_refund`` (a side effect): only for the approved draft; skipped if a refund id is
        already recorded; idempotency key ``"{workflow_id}:refund"``. Audit ``refund_issued``.
        Next step: ``send_email``."""
        raise NotImplementedError("TODO")

    def _send_email(self) -> None:
        """Step ``send_email`` (a side effect): send the approved draft with key ``"{workflow_id}:email"``,
        audit ``email_sent`` then ``completed``; status ``completed``, next step ``done``."""
        raise NotImplementedError("TODO")

    # ------------------------------------------------------------------ guards and helpers
    def _require_gate(self, approver: str) -> None:
        """Decisions need status ``awaiting_approval`` ("nothing to decide: ...") and a listed approver
        ("... is not allowed to approve refunds")."""
        raise NotImplementedError("TODO")

    def _require_approved_draft(self) -> Draft:
        """Side effects need an approval for exactly the current draft."""
        raise NotImplementedError("TODO")

    def _draft_or_fail(self) -> Draft:
        if self.state.draft is None:
            raise WorkflowError("there is no draft yet")
        return self.state.draft

    def _finish_rejected(self, actor: str, reason: str) -> None:
        self.state.status, self.state.next_step, self.state.rejection_reason = "rejected", "done", reason
        self._audit(actor, "rejected", {"reason": reason})

    def _audit(self, actor: str, event: str, details: Mapping[str, Any]) -> AuditEntry:
        return append_audit(self.state.audit, self.services.clock(), actor, event, details)

    def _save(self) -> None:
        if self.checkpoint_path is not None:
            save_checkpoint(self.state, self.checkpoint_path)


# ==================================================================================================
# Optional: drafting with a free local model through Ollama (never used by the tests)
# ==================================================================================================

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class OllamaDrafter:
    """Drafts with a local model via Ollama's ``/api/chat`` (``ollama pull llama3.2``; ~8 GB RAM).

    The customer's details never leave the machine (localhost only). The workflow validates the draft
    like any other and falls back to the template if it is unusable — the model can only *suggest* text.
    """

    def __init__(
        self, model: str = "llama3.2", base_url: str = "http://localhost:11434", timeout: float = 120.0
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
            raise ValueError("OllamaDrafter only talks to a local server, e.g. http://localhost:11434")
        self.model, self.url, self.timeout = model, base_url.rstrip("/") + "/api/chat", timeout

    def draft(self, request: RefundRequest) -> Draft:
        """Ask the model for ``{"subject": ..., "body": ...}``."""
        prompt = (
            "Write a short, polite email confirming a refund. Reply with JSON: "
            '{"subject": "...", "body": "..."}. The body must contain the amount and the order id exactly. '
            f"Customer: {request.customer_name}. Order: {request.order_id}. "
            f"Amount: {format_money(request.amount_cents)}. Reason: {request.reason}."
        )
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "format": "json", "options": {"temperature": 0}}  # fmt: skip
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        http_request = urllib.request.Request(self.url, data=data, headers=headers)  # noqa: S310 (localhost only)
        with urllib.request.urlopen(http_request, timeout=self.timeout) as response:  # noqa: S310 (localhost only)
            content = json.loads(response.read().decode("utf-8"))["message"]["content"]
        reply = json.loads(content)
        return Draft(str(reply.get("subject", "")), str(reply.get("body", "")))


# ==================================================================================================
# Command line demo
# ==================================================================================================


def demo(folder: Path, drafter: Drafter | None = None) -> RefundWorkflow:
    """Run one refund end to end with fake services, approving with an edit. Returns the workflow."""
    services = Services(
        orders={"ORD-1001": Order("ORD-1001", "sam@example.com", 4_999, 3)},
        payments=FakePaymentGateway(),
        mailer=FakeMailer(),
        approvers=frozenset({"maria"}),
        drafter=drafter or TemplateDrafter(),
    )
    request = RefundRequest("REQ-1", "ORD-1001", "Sam Lee", "sam@example.com", 1_250, "Arrived damaged")
    path = folder / "wf-1.json"
    workflow = RefundWorkflow.start(request, "wf-1", services, path)
    workflow.run()
    body = workflow.state.draft.body if workflow.state.draft else ""
    print(f"status: {workflow.state.status}\n--- draft ---\n{body}")
    resumed = RefundWorkflow.resume(path, services)  # as if a new process picked it up
    draft = resumed.state.draft
    assert draft is not None
    resumed.approve("maria", body=draft.body + "\n\nSorry again for the trouble.", note="added apology")
    resumed.run()
    print(
        f"status: {resumed.state.status}, refund {resumed.state.refund_id}, email {resumed.state.message_id}"
    )
    for entry in resumed.state.audit:
        print(f"{entry.seq:>2} {entry.at} {entry.actor:<7} {entry.event}")
    return resumed


def main(argv: list[str] | None = None) -> int:
    """``python approval_workflow.py [--ollama MODEL] [--folder DIR]``"""
    parser = argparse.ArgumentParser(description="Run the refund workflow demo.")
    parser.add_argument("--ollama", metavar="MODEL", help="draft with a local Ollama model")
    parser.add_argument("--folder", type=Path, help="where to write the checkpoint (default: a temp folder)")
    args = parser.parse_args(argv)
    drafter = OllamaDrafter(args.ollama) if args.ollama else None
    if args.folder:
        demo(args.folder, drafter)
    else:
        with tempfile.TemporaryDirectory() as folder:
            demo(Path(folder), drafter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
