"""Behaviour tests for the human-approved refund workflow, one class per milestone.

Run everything with ``python -m pytest`` or one milestone with ``-k Milestone3``. Services are fakes,
the clock is a :class:`FakeClock`, and checkpoints live in ``tmp_path`` — nothing depends on the
network or the real time.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from approval_workflow import (
    AuditEntry,
    CheckpointError,
    Draft,
    FakeClock,
    FakeMailer,
    FakePaymentGateway,
    OllamaDrafter,
    Order,
    RefundPolicy,
    RefundRequest,
    RefundWorkflow,
    Services,
    StepFailedError,
    TemplateDrafter,
    WorkflowError,
    WorkflowState,
    append_audit,
    check_refund_policy,
    format_money,
    load_checkpoint,
    main,
    save_checkpoint,
    validate_draft,
    validate_request,
    verify_audit,
)

REQUEST = RefundRequest("REQ-7", "ORD-1001", "Sam Lee", "sam@example.com", 1_250, "Arrived damaged")
ORDER = Order("ORD-1001", "sam@example.com", 4_999, 3)


def make_services(**overrides) -> Services:
    """Fake services with one order and one approver ("maria")."""
    defaults = {
        "orders": {ORDER.order_id: ORDER},
        "payments": FakePaymentGateway(),
        "mailer": FakeMailer(),
        "approvers": frozenset({"maria"}),
        "clock": FakeClock(),
    }
    return Services(**{**defaults, **overrides})


def events(state: WorkflowState) -> list[str]:
    return [entry.event for entry in state.audit]


@pytest.fixture
def services() -> Services:
    return make_services()


@pytest.fixture
def waiting(services: Services) -> RefundWorkflow:
    """A workflow that has run up to the approval gate."""
    workflow = RefundWorkflow.start(REQUEST, "wf-1", services)
    workflow.run()
    return workflow


class TestMilestone1ValidationAndPolicy:
    """Milestone 1: validate the request's shape, then apply the refund policy."""

    def test_format_money(self) -> None:
        assert [format_money(c) for c in (0, 5, 1250, 4999, 100000)] == [
            "0.00",
            "0.05",
            "12.50",
            "49.99",
            "1000.00",
        ]
        with pytest.raises(ValueError):
            format_money(-1)

    def test_valid_request(self) -> None:
        assert validate_request(REQUEST) == []

    @pytest.mark.parametrize(
        ("changes", "fragment"),
        [
            ({"order_id": "1001"}, "order_id"),
            ({"order_id": "ORD-12"}, "order_id"),
            ({"customer_name": "  "}, "customer_name"),
            ({"customer_name": "Sam\nBcc: everyone@example.com"}, "customer_name"),
            ({"customer_email": "sam.example.com"}, "customer_email"),
            ({"customer_email": "sam@example"}, "customer_email"),
            ({"amount_cents": 0}, "amount_cents"),
            ({"amount_cents": -100}, "amount_cents"),
            ({"amount_cents": 12.5}, "amount_cents"),
            ({"amount_cents": True}, "amount_cents"),
            ({"reason": ""}, "reason"),
            ({"reason": "x" * 501}, "reason"),
        ],
    )
    def test_invalid_requests(self, changes: dict, fragment: str) -> None:
        problems = validate_request(replace(REQUEST, **changes))
        assert len(problems) == 1 and fragment in problems[0], problems

    def test_policy_allows_a_normal_refund(self) -> None:
        assert check_refund_policy(REQUEST, ORDER, RefundPolicy()) == []
        assert (
            check_refund_policy(replace(REQUEST, customer_email="SAM@example.com"), ORDER, RefundPolicy())
            == []
        )

    def test_policy_problems(self) -> None:
        policy = RefundPolicy(max_refund_cents=2_000, refund_window_days=30)
        assert check_refund_policy(REQUEST, None, policy) == ["order ORD-1001 does not exist"]
        other = replace(ORDER, customer_email="eve@example.com")
        assert check_refund_policy(REQUEST, other, policy) == ["the order belongs to a different customer"]
        too_much = replace(REQUEST, amount_cents=6_000)
        problems = check_refund_policy(too_much, ORDER, policy)
        assert problems == [
            "refund 60.00 is more than the order total 49.99",
            "refunds above 20.00 need the manual process",
        ]
        old = replace(ORDER, days_since_purchase=45)
        assert check_refund_policy(REQUEST, old, policy) == [
            "the order is 45 days old; the refund window is 30 days"
        ]


class TestMilestone2StateAndGate:
    """Milestone 2: drafts, the hash-chained audit log, serialisable state, and running to the gate."""

    def test_template_draft_is_valid(self) -> None:
        draft = TemplateDrafter().draft(REQUEST)
        assert draft.subject == "Your refund for order ORD-1001"
        assert "Dear Sam Lee," in draft.body and "12.50" in draft.body and "ORD-1001" in draft.body
        assert validate_draft(draft, REQUEST) == []

    def test_draft_validation(self) -> None:
        good = TemplateDrafter().draft(REQUEST)
        assert any(
            "header injection" in p for p in validate_draft(replace(good, subject="Hi\nBcc: x@y.z"), REQUEST)
        )
        assert any(
            "12.50" in p
            for p in validate_draft(replace(good, body="Your refund is on its way. ORD-1001"), REQUEST)
        )
        assert any(
            "ORD-1001" in p for p in validate_draft(replace(good, body="Refund of 12.50 approved."), REQUEST)
        )
        assert validate_draft(replace(good, subject=""), REQUEST) and validate_draft(
            replace(good, body="12.50 ORD-1001" + "x" * 2000), REQUEST
        )

    def test_fingerprint_changes_with_any_edit(self) -> None:
        draft = Draft("Subject", "Body")
        assert (
            draft.fingerprint() == Draft("Subject", "Body").fingerprint() and len(draft.fingerprint()) == 64
        )
        assert draft.fingerprint() != Draft("Subject", "Body.").fingerprint()
        assert Draft("ab", "c").fingerprint() != Draft("a", "bc").fingerprint()

    def test_audit_log_is_a_hash_chain(self) -> None:
        log: list[AuditEntry] = []
        first = append_audit(log, "t1", "system", "received", {"amount": 1})
        second = append_audit(log, "t2", "maria", "approved")
        assert (first.seq, second.seq, second.prev_hash, second.details) == (1, 2, first.hash, {})
        assert first.prev_hash == "0" * 64 and verify_audit(log) == []
        tampered = [replace(first, details={"amount": 1000}), second]
        assert verify_audit(tampered) == ["entry 1 (received) was modified"]
        assert verify_audit([second]) == ["entry 1 has sequence number 2", "entry 1 does not follow entry 0"]
        reordered = [first, replace(second, seq=3)]
        assert "entry 2 has sequence number 3" in verify_audit(reordered)

    def test_runs_to_the_approval_gate(self, waiting: RefundWorkflow, services: Services) -> None:
        state = waiting.state
        assert (state.status, state.next_step) == ("awaiting_approval", "approval")
        assert events(state) == ["received", "validated", "policy_passed", "drafted", "approval_requested"]
        assert [entry.at for entry in state.audit][:2] == [
            "2026-10-22T09:00:00+00:00",
            "2026-10-22T09:01:00+00:00",
        ]
        assert state.draft == TemplateDrafter().draft(REQUEST)
        assert state.audit[-1].details == {"fingerprint": state.draft.fingerprint()}
        assert services.payments.refunds == [] and services.mailer.outbox == [], (
            "nothing happens before approval"
        )

    def test_running_again_at_the_gate_changes_nothing(self, waiting: RefundWorkflow) -> None:
        before = list(waiting.state.audit)
        assert waiting.run().status == "awaiting_approval"
        assert waiting.state.audit == before

    def test_invalid_request_is_rejected_without_a_draft(self, services: Services) -> None:
        workflow = RefundWorkflow.start(replace(REQUEST, amount_cents=0), "wf-2", services)
        state = workflow.run()
        assert state.status == "rejected" and state.draft is None
        assert state.rejection_reason.startswith("invalid request: amount_cents")
        assert events(state) == ["received", "rejected"]

    def test_policy_violation_is_rejected(self) -> None:
        workflow = RefundWorkflow.start(replace(REQUEST, order_id="ORD-9999"), "wf-3", make_services())
        state = workflow.run()
        assert (
            state.status == "rejected" and state.rejection_reason == "policy: order ORD-9999 does not exist"
        )
        assert events(state) == ["received", "validated", "rejected"]

    def test_unusable_model_drafts_are_replaced(self) -> None:
        class SloppyDrafter:
            def draft(self, request: RefundRequest) -> Draft:
                return Draft("Refund!\nBcc: everyone@example.com", "We refunded you.")

        workflow = RefundWorkflow.start(REQUEST, "wf-4", make_services(drafter=SloppyDrafter()))
        state = workflow.run()
        assert state.draft == TemplateDrafter().draft(REQUEST)
        assert "draft_replaced" in events(state)

    def test_state_round_trips_through_json(self, waiting: RefundWorkflow) -> None:
        data = json.loads(json.dumps(waiting.state.to_dict()))
        assert WorkflowState.from_dict(data) == waiting.state
        with pytest.raises(CheckpointError):
            WorkflowState.from_dict({"workflow_id": "x"})
        with pytest.raises(CheckpointError):
            WorkflowState.from_dict({**data, "status": "teleported"})


class TestMilestone3ApprovalGate:
    """Milestone 3: approve (with optional edits) or reject — only at the gate, only by approvers."""

    def test_approve_records_the_decision_but_does_not_act(
        self, waiting: RefundWorkflow, services: Services
    ) -> None:
        state = waiting.approve("maria", note="looks fine")
        assert (state.status, state.next_step) == ("in_progress", "issue_refund")
        assert state.approval.approver == "maria" and state.approval.note == "looks fine"
        assert state.approval.edited_fields == () and state.approval.fingerprint == state.draft.fingerprint()
        assert state.approval.at == state.audit[-1].at and events(state)[-1] == "approved"
        assert services.payments.refunds == [] and services.mailer.outbox == []

    def test_approver_can_edit_the_draft(self, waiting: RefundWorkflow) -> None:
        original = waiting.state.draft
        body = original.body.replace("Kind regards", "Sorry for the trouble. Kind regards")
        state = waiting.approve("maria", body=body)
        assert state.draft == Draft(original.subject, body)
        assert (
            state.approval.edited_fields == ("body",)
            and state.approval.fingerprint == Draft(original.subject, body).fingerprint()
        )
        assert events(state)[-2:] == ["draft_edited", "approved"]
        assert state.audit[-2].details["fields"] == ["body"] and state.audit[-2].actor == "maria"

    def test_unchanged_edits_are_not_edits(self, waiting: RefundWorkflow) -> None:
        state = waiting.approve("maria", subject=waiting.state.draft.subject)
        assert state.approval.edited_fields == () and "draft_edited" not in events(state)

    @pytest.mark.parametrize(
        ("edit", "fragment"),
        [
            ({"body": "Your money is on its way."}, "12.50"),
            ({"subject": "Refund\r\nBcc: everyone@example.com"}, "header injection"),
            ({"subject": ""}, "subject"),
        ],
    )
    def test_invalid_edits_change_nothing(self, waiting: RefundWorkflow, edit: dict, fragment: str) -> None:
        before = waiting.state.draft
        with pytest.raises(WorkflowError, match=fragment):
            waiting.approve("maria", **edit)
        assert (
            waiting.state.status == "awaiting_approval"
            and waiting.state.draft == before
            and waiting.state.approval is None
        )

    def test_only_authorised_approvers(self, waiting: RefundWorkflow) -> None:
        for person in ["mallory", "", "Maria"]:
            with pytest.raises(WorkflowError, match="not allowed"):
                waiting.approve(person)
        assert waiting.state.status == "awaiting_approval"

    def test_reject(self, waiting: RefundWorkflow, services: Services) -> None:
        with pytest.raises(WorkflowError, match="reason"):
            waiting.reject("maria", "   ")
        state = waiting.reject("maria", "  Customer already refunded by phone ")
        assert (state.status, state.rejection_reason) == ("rejected", "Customer already refunded by phone")
        assert state.audit[-1].actor == "maria" and events(state)[-1] == "rejected"
        with pytest.raises(WorkflowError, match="already rejected"):
            waiting.run()
        assert services.payments.calls == 0 and services.mailer.calls == 0

    def test_decisions_only_at_the_gate(self, services: Services) -> None:
        workflow = RefundWorkflow.start(REQUEST, "wf-5", services)
        with pytest.raises(WorkflowError, match="nothing to decide"):
            workflow.approve("maria")
        workflow.run()
        workflow.approve("maria")
        with pytest.raises(WorkflowError, match="nothing to decide"):
            workflow.approve("maria")
        with pytest.raises(WorkflowError, match="nothing to decide"):
            workflow.reject("maria", "changed my mind")


class TestMilestone4SideEffects:
    """Milestone 4: refund and email exactly once, only for the approved text, surviving failures."""

    def test_happy_path_sends_exactly_the_approved_text(
        self, waiting: RefundWorkflow, services: Services
    ) -> None:
        body = waiting.state.draft.body + "\n\nP.S. Sorry!"
        waiting.approve("maria", body=body)
        state = waiting.run()
        assert (state.status, state.next_step, state.refund_id, state.message_id) == (
            "completed",
            "done",
            "re_0001",
            "msg_0001",
        )
        assert services.payments.refunds == [{"id": "re_0001", "order_id": "ORD-1001", "amount_cents": 1250}]
        assert services.mailer.outbox == [
            {
                "id": "msg_0001",
                "to": "sam@example.com",
                "subject": "Your refund for order ORD-1001",
                "body": body,
            }
        ]
        assert events(state)[-4:] == ["approved", "refund_issued", "email_sent", "completed"]
        with pytest.raises(WorkflowError, match="already completed"):
            waiting.run()

    def test_a_failed_step_can_be_retried_without_repeating_side_effects(self) -> None:
        services = make_services(mailer=FakeMailer(fail_times=1))
        workflow = RefundWorkflow.start(REQUEST, "wf-6", services)
        workflow.run()
        workflow.approve("maria")
        with pytest.raises(StepFailedError, match="send_email"):
            workflow.run()
        state = workflow.state
        assert (state.status, state.next_step, state.refund_id) == ("in_progress", "send_email", "re_0001")
        assert state.last_error == "send_email: ConnectionError: mail server unavailable"
        assert state.audit[-1].event == "step_failed" and state.audit[-1].details == {
            "step": "send_email",
            "error": "ConnectionError",
        }
        assert workflow.run().status == "completed" and state.last_error is None
        assert len(services.payments.refunds) == 1 and services.payments.calls == 1, (
            "the refund is not issued again"
        )
        assert len(services.mailer.outbox) == 1

    def test_payment_failure_sends_nothing(self) -> None:
        services = make_services(payments=FakePaymentGateway(fail_times=1))
        workflow = RefundWorkflow.start(REQUEST, "wf-7", services)
        workflow.run()
        workflow.approve("maria")
        with pytest.raises(StepFailedError, match="issue_refund"):
            workflow.run()
        assert workflow.state.refund_id is None and services.mailer.calls == 0
        assert workflow.run().status == "completed" and len(services.payments.refunds) == 1

    def test_idempotency_keys_prevent_double_sends(self, waiting: RefundWorkflow, services: Services) -> None:
        waiting.approve("maria")
        waiting.run()
        assert services.payments.refund("ORD-1001", 1250, "wf-1:refund") == "re_0001"
        assert services.mailer.send("sam@example.com", "s", "b", "wf-1:email") == "msg_0001"
        assert len(services.payments.refunds) == 1 and len(services.mailer.outbox) == 1

    def test_no_side_effects_if_the_draft_changes_after_approval(
        self, waiting: RefundWorkflow, services: Services
    ) -> None:
        waiting.approve("maria")
        waiting.state.draft = replace(
            waiting.state.draft, body=waiting.state.draft.body + " Also, here is a gift card."
        )
        with pytest.raises(StepFailedError) as caught:
            waiting.run()
        assert "changed after it was approved" in str(caught.value.__cause__)
        assert services.payments.calls == 0 and services.mailer.calls == 0


class TestMilestone5Checkpoints:
    """Milestone 5: atomic JSON checkpoints, verification on load, and resuming in a new process."""

    def test_save_and_load_round_trip(self, waiting: RefundWorkflow, tmp_path: Path) -> None:
        path = tmp_path / "state" / "wf-1.json"
        save_checkpoint(waiting.state, path)
        assert load_checkpoint(path) == waiting.state
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1 and data["state"]["status"] == "awaiting_approval"
        assert sorted(p.name for p in path.parent.iterdir()) == ["wf-1.json"], (
            "no temporary files are left behind"
        )

    def test_checkpoint_after_every_step(self, services: Services, tmp_path: Path) -> None:
        path = tmp_path / "wf-1.json"
        workflow = RefundWorkflow.start(REQUEST, "wf-1", services, path)
        assert load_checkpoint(path).next_step == "validate"
        workflow.run()
        assert load_checkpoint(path).status == "awaiting_approval"
        workflow.approve("maria")
        assert load_checkpoint(path).next_step == "issue_refund"
        workflow.run()
        assert load_checkpoint(path) == workflow.state and workflow.state.status == "completed"

    def test_unreadable_checkpoints(self, waiting: RefundWorkflow, tmp_path: Path) -> None:
        with pytest.raises(CheckpointError, match="no checkpoint"):
            load_checkpoint(tmp_path / "missing.json")
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with pytest.raises(CheckpointError, match="cannot be read"):
            load_checkpoint(broken)
        path = tmp_path / "wf.json"
        save_checkpoint(waiting.state, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "schema_version": 99}), encoding="utf-8")
        with pytest.raises(CheckpointError, match="version"):
            load_checkpoint(path)
        path.write_text(json.dumps({"schema_version": 1, "state": {"workflow_id": "x"}}), encoding="utf-8")
        with pytest.raises(CheckpointError, match="shape"):
            load_checkpoint(path)

    def tamper(self, workflow: RefundWorkflow, path: Path, change) -> None:
        save_checkpoint(workflow.state, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data["state"])
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_tampering_is_detected(self, waiting: RefundWorkflow, tmp_path: Path) -> None:
        path = tmp_path / "wf.json"
        self.tamper(waiting, path, lambda s: s["request"].update(amount_cents=99_999))
        with pytest.raises(CheckpointError, match="request does not match"):
            load_checkpoint(path)
        self.tamper(waiting, path, lambda s: s["audit"][1].update(actor="maria"))
        with pytest.raises(CheckpointError, match="modified"):
            load_checkpoint(path)
        waiting.approve("maria")

        def swap_draft_and_approval(state: dict) -> None:
            state["draft"]["body"] += " Bonus: 500.00 credit."
            state["approval"]["fingerprint"] = Draft(
                state["draft"]["subject"], state["draft"]["body"]
            ).fingerprint()

        self.tamper(waiting, path, swap_draft_and_approval)
        with pytest.raises(CheckpointError, match="approval does not match"):
            load_checkpoint(path)

    def test_edited_draft_in_the_file_is_never_sent(
        self, waiting: RefundWorkflow, services: Services, tmp_path: Path
    ) -> None:
        waiting.approve("maria")
        path = tmp_path / "wf.json"
        self.tamper(waiting, path, lambda s: s["draft"].update(body=s["draft"]["body"] + " Bonus credit!"))
        resumed = RefundWorkflow.resume(path, services)
        with pytest.raises(StepFailedError):
            resumed.run()
        assert services.payments.calls == 0 and services.mailer.calls == 0

    def test_resume_in_a_new_process(self, tmp_path: Path) -> None:
        path = tmp_path / "wf-9.json"
        first = RefundWorkflow.start(REQUEST, "wf-9", make_services(), path)
        first.run()
        del first  # "the process ends"; only the checkpoint survives
        later = make_services(clock=FakeClock("2026-10-23T08:00:00+00:00"))
        resumed = RefundWorkflow.resume(path, later)
        assert resumed.state.status == "awaiting_approval"
        assert (
            resumed.state.audit[-1].event == "resumed"
            and resumed.state.audit[-1].at == "2026-10-23T08:00:00+00:00"
        )
        resumed.approve("maria")
        assert resumed.run().status == "completed" and len(later.mailer.outbox) == 1
        assert verify_audit(load_checkpoint(path).audit) == []

    def test_crash_after_the_email_left_does_not_send_it_twice(self, tmp_path: Path) -> None:
        services = make_services(mailer=FakeMailer(fail_after_send=True))
        path = tmp_path / "wf-10.json"
        workflow = RefundWorkflow.start(REQUEST, "wf-10", services, path)
        workflow.run()
        workflow.approve("maria")
        with pytest.raises(StepFailedError):
            workflow.run()
        saved = load_checkpoint(path)
        assert (saved.next_step, saved.message_id) == ("send_email", None)
        assert len(services.mailer.outbox) == 1, "the message left even though the call failed"
        resumed = RefundWorkflow.resume(path, services)
        assert resumed.run().status == "completed"
        assert len(services.mailer.outbox) == 1 and resumed.state.message_id == "msg_0001"

    def test_demo_and_optional_adapter(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--folder", str(tmp_path)]) == 0
        output = capsys.readouterr().out
        assert "status: awaiting_approval" in output and "status: completed" in output
        assert load_checkpoint(tmp_path / "wf-1.json").status == "completed"
        assert OllamaDrafter(base_url="http://127.0.0.1:11434").url.endswith("/api/chat")
        with pytest.raises(ValueError):
            OllamaDrafter(base_url="https://api.example.com")
