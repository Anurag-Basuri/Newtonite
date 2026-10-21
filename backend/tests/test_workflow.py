"""
Exhaustive tests for the workflow state machine.

Tests every legal transition, every illegal transition, role guards,
assignee guards, reason/resolution requirements, and approval-only gating.
"""

import unittest

from app.domain.enums import ItemStatus, ItemResolution, TeamRole
from app.domain.workflow import (
    TRANSITIONS,
    Transition,
    WorkflowError,
    validate_transition,
    allowed_transitions,
    get_transition,
    CANCEL_RESOLUTIONS,
)


class TestTransitionTableCompleteness(unittest.TestCase):
    """Verify the transition table itself is well-formed."""

    def test_no_duplicate_edges(self):
        edges = [(t.from_status, t.to_status) for t in TRANSITIONS]
        self.assertEqual(len(edges), len(set(edges)), "Duplicate transition edges found")

    def test_no_self_transitions(self):
        for t in TRANSITIONS:
            self.assertNotEqual(t.from_status, t.to_status, f"Self-transition: {t.action}")

    def test_all_active_states_have_at_least_one_outgoing(self):
        for status in ItemStatus.active_states():
            outgoing = allowed_transitions(status, include_approval_only=True)
            self.assertGreater(len(outgoing), 0, f"No transitions from {status}")

    def test_closed_has_only_reopen(self):
        outgoing = allowed_transitions(ItemStatus.CLOSED, include_approval_only=True)
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0].action, "reopen")
        self.assertEqual(outgoing[0].to_status, ItemStatus.OPEN)


class TestLegalTransitions(unittest.TestCase):
    """Verify every legal transition succeeds with the right inputs."""

    def test_triage_by_lead(self):
        t = validate_transition(
            ItemStatus.OPEN, ItemStatus.TRIAGED,
            actor_role=TeamRole.LEAD, is_assignee=False,
        )
        self.assertEqual(t.action, "triage")

    def test_start_from_open_by_assignee(self):
        t = validate_transition(
            ItemStatus.OPEN, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.MEMBER, is_assignee=True,
        )
        self.assertEqual(t.action, "start")

    def test_start_from_triaged_by_assignee(self):
        t = validate_transition(
            ItemStatus.TRIAGED, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.MEMBER, is_assignee=True,
        )
        self.assertEqual(t.action, "start")

    def test_block_with_reason(self):
        t = validate_transition(
            ItemStatus.IN_PROGRESS, ItemStatus.BLOCKED,
            actor_role=TeamRole.MEMBER, is_assignee=True,
            reason="Waiting on third-party API response",
        )
        self.assertEqual(t.action, "block")

    def test_unblock(self):
        t = validate_transition(
            ItemStatus.BLOCKED, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.MEMBER, is_assignee=True,
        )
        self.assertEqual(t.action, "unblock")

    def test_resolve(self):
        t = validate_transition(
            ItemStatus.IN_PROGRESS, ItemStatus.RESOLVED,
            actor_role=TeamRole.MEMBER, is_assignee=True,
        )
        self.assertEqual(t.action, "resolve")

    def test_close_by_lead_with_resolution(self):
        t = validate_transition(
            ItemStatus.RESOLVED, ItemStatus.CLOSED,
            actor_role=TeamRole.LEAD, is_assignee=False,
            resolution=ItemResolution.COMPLETED,
        )
        self.assertEqual(t.action, "close")

    def test_reopen_from_resolved(self):
        t = validate_transition(
            ItemStatus.RESOLVED, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.MEMBER, is_assignee=False,
            reason="Fix was incomplete",
        )
        self.assertEqual(t.action, "reopen")

    def test_reopen_from_closed_by_lead(self):
        t = validate_transition(
            ItemStatus.CLOSED, ItemStatus.OPEN,
            actor_role=TeamRole.LEAD, is_assignee=False,
            reason="Customer escalation",
        )
        self.assertEqual(t.action, "reopen")

    def test_cancel_with_wont_do(self):
        t = validate_transition(
            ItemStatus.OPEN, ItemStatus.CLOSED,
            actor_role=TeamRole.LEAD, is_assignee=False,
            resolution=ItemResolution.WONT_DO,
        )
        self.assertEqual(t.action, "cancel")

    def test_cancel_with_duplicate(self):
        t = validate_transition(
            ItemStatus.IN_PROGRESS, ItemStatus.CLOSED,
            actor_role=TeamRole.LEAD, is_assignee=False,
            resolution=ItemResolution.DUPLICATE,
            duplicate_of="OPS-42",
        )
        self.assertEqual(t.action, "cancel")

    def test_request_approval(self):
        t = validate_transition(
            ItemStatus.IN_PROGRESS, ItemStatus.PENDING_APPROVAL,
            actor_role=TeamRole.MEMBER, is_assignee=True,
        )
        self.assertEqual(t.action, "request_approval")

    def test_approve_via_approval_endpoint(self):
        t = validate_transition(
            ItemStatus.PENDING_APPROVAL, ItemStatus.RESOLVED,
            actor_role=TeamRole.LEAD, is_assignee=False,
            via_approval_endpoint=True,
        )
        self.assertEqual(t.action, "approve")

    def test_reject_via_approval_endpoint(self):
        t = validate_transition(
            ItemStatus.PENDING_APPROVAL, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.LEAD, is_assignee=False,
            reason="Needs more investigation",
            via_approval_endpoint=True,
        )
        self.assertEqual(t.action, "reject")

    def test_lead_can_start_without_being_assignee(self):
        """Leads bypass the requires_assignee check."""
        t = validate_transition(
            ItemStatus.OPEN, ItemStatus.IN_PROGRESS,
            actor_role=TeamRole.LEAD, is_assignee=False,
        )
        self.assertEqual(t.action, "start")


class TestIllegalTransitions(unittest.TestCase):
    """Verify illegal transitions are rejected with the correct error code."""

    def test_nonexistent_edge(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.RESOLVED,
                actor_role=TeamRole.LEAD, is_assignee=False,
            )
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")

    def test_triage_by_member_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.TRIAGED,
                actor_role=TeamRole.MEMBER, is_assignee=False,
            )
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_triage_by_viewer_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.TRIAGED,
                actor_role=TeamRole.VIEWER, is_assignee=False,
            )
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_start_by_non_assignee_member_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.IN_PROGRESS,
                actor_role=TeamRole.MEMBER, is_assignee=False,
            )
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_block_without_reason_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.IN_PROGRESS, ItemStatus.BLOCKED,
                actor_role=TeamRole.MEMBER, is_assignee=True,
                reason=None,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_close_without_resolution_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.RESOLVED, ItemStatus.CLOSED,
                actor_role=TeamRole.LEAD, is_assignee=False,
                resolution=None,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_cancel_with_completed_resolution_denied(self):
        """Cancel doesn't accept 'completed' — only wont_do/duplicate/cancelled."""
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.CLOSED,
                actor_role=TeamRole.LEAD, is_assignee=False,
                resolution=ItemResolution.COMPLETED,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_duplicate_resolution_without_duplicate_of_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.CLOSED,
                actor_role=TeamRole.LEAD, is_assignee=False,
                resolution=ItemResolution.DUPLICATE,
                duplicate_of=None,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_reopen_from_resolved_without_reason_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.RESOLVED, ItemStatus.IN_PROGRESS,
                actor_role=TeamRole.MEMBER, is_assignee=False,
                reason=None,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_reopen_from_closed_by_member_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.CLOSED, ItemStatus.OPEN,
                actor_role=TeamRole.MEMBER, is_assignee=False,
                reason="Reopen please",
            )
        self.assertEqual(ctx.exception.code, "FORBIDDEN")


class TestApprovalOnlyGating(unittest.TestCase):
    """Ensure approval transitions can only go through the approval endpoint."""

    def test_approve_via_generic_endpoint_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.PENDING_APPROVAL, ItemStatus.RESOLVED,
                actor_role=TeamRole.LEAD, is_assignee=False,
                via_approval_endpoint=False,
            )
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")
        self.assertIn("approval endpoint", ctx.exception.detail)

    def test_reject_via_generic_endpoint_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.PENDING_APPROVAL, ItemStatus.IN_PROGRESS,
                actor_role=TeamRole.LEAD, is_assignee=False,
                reason="Nope",
                via_approval_endpoint=False,
            )
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")

    def test_non_approval_via_approval_endpoint_denied(self):
        with self.assertRaises(WorkflowError) as ctx:
            validate_transition(
                ItemStatus.OPEN, ItemStatus.TRIAGED,
                actor_role=TeamRole.LEAD, is_assignee=False,
                via_approval_endpoint=True,
            )
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")
        self.assertIn("not an approval action", ctx.exception.detail)


class TestAllowedTransitions(unittest.TestCase):
    """Test the allowed_transitions helper."""

    def test_open_transitions_exclude_approval_by_default(self):
        ts = allowed_transitions(ItemStatus.OPEN)
        actions = {t.action for t in ts}
        self.assertIn("triage", actions)
        self.assertIn("start", actions)
        self.assertIn("cancel", actions)

    def test_pending_approval_with_include(self):
        ts = allowed_transitions(ItemStatus.PENDING_APPROVAL, include_approval_only=True)
        actions = {t.action for t in ts}
        self.assertIn("approve", actions)
        self.assertIn("reject", actions)

    def test_pending_approval_without_include(self):
        ts = allowed_transitions(ItemStatus.PENDING_APPROVAL, include_approval_only=False)
        actions = {t.action for t in ts}
        self.assertNotIn("approve", actions)
        self.assertNotIn("reject", actions)


if __name__ == "__main__":
    unittest.main()
