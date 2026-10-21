"""
Exhaustive tests for the authorization policy.

Tests the full role × action × relationship matrix from SYSTEM_DESIGN §5.2,
including:
  - Non-member → 404 (invisible)
  - Viewer restrictions
  - Member conditional access (reporter/assignee)
  - Lead full access
  - Org admin team management + read-only on items
  - Four-eyes rule on approval decisions
  - P0 priority lead-only restriction
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.enums import TeamRole, ItemPriority, ItemStatus
from app.domain.policy import (
    Action,
    ActorCtx,
    ResourceCtx,
    Decision,
    can,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _actor(
    user_id: str = "usr_actor",
    role: TeamRole | None = TeamRole.MEMBER,
    is_org_admin: bool = False,
) -> ActorCtx:
    return ActorCtx(user_id=user_id, is_org_admin=is_org_admin, role_in_team=role)


def _resource(
    team_id: str = "team_ops",
    reporter_id: str = "usr_reporter",
    assignee_id: str | None = "usr_assignee",
    status: ItemStatus = ItemStatus.OPEN,
    new_priority: ItemPriority | None = None,
    approval_requester_id: str | None = None,
) -> ResourceCtx:
    return ResourceCtx(
        team_id=team_id,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
        status=status,
        new_priority=new_priority,
        approval_requester_id=approval_requester_id,
    )


class TestNonMemberAccess(unittest.TestCase):
    """Non-members should get invisible (404) for everything except org admin reads."""

    def test_non_member_read_is_invisible(self):
        d = can(_actor(role=None), Action.READ_ITEM, _resource())
        self.assertFalse(d.allowed)
        self.assertTrue(d.not_visible)

    def test_non_member_create_is_invisible(self):
        d = can(_actor(role=None), Action.CREATE_ITEM, _resource())
        self.assertFalse(d.allowed)
        self.assertTrue(d.not_visible)

    def test_non_member_transition_is_invisible(self):
        d = can(_actor(role=None), Action.TRANSITION, _resource())
        self.assertFalse(d.allowed)
        self.assertTrue(d.not_visible)


class TestOrgAdmin(unittest.TestCase):
    """Org admins: manage teams, read all items, but no implicit write on items."""

    def test_org_admin_can_manage_teams(self):
        d = can(_actor(role=None, is_org_admin=True), Action.MANAGE_TEAMS, _resource())
        self.assertTrue(d.allowed)

    def test_non_admin_cannot_manage_teams(self):
        d = can(_actor(role=TeamRole.LEAD), Action.MANAGE_TEAMS, _resource())
        self.assertFalse(d.allowed)

    def test_org_admin_can_read_any_item(self):
        d = can(_actor(role=None, is_org_admin=True), Action.READ_ITEM, _resource())
        self.assertTrue(d.allowed)

    def test_org_admin_cannot_create_without_team_membership(self):
        d = can(_actor(role=None, is_org_admin=True), Action.CREATE_ITEM, _resource())
        self.assertFalse(d.allowed)
        self.assertTrue(d.not_visible)

    def test_org_admin_can_use_ai(self):
        d = can(_actor(role=None, is_org_admin=True), Action.USE_AI, _resource())
        self.assertTrue(d.allowed)


class TestViewerRole(unittest.TestCase):
    """Viewers can read and use AI, nothing else."""

    def test_viewer_can_read(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.READ_ITEM, _resource())
        self.assertTrue(d.allowed)

    def test_viewer_can_use_ai(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.USE_AI, _resource())
        self.assertTrue(d.allowed)

    def test_viewer_cannot_create(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.CREATE_ITEM, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_comment(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.COMMENT, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_claim(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.CLAIM, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_edit(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.EDIT_ITEM, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_transition(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.TRANSITION, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_assign(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.ASSIGN, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_triage(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.TRIAGE, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_request_approval(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.REQUEST_APPROVAL, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_decide_approval(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.DECIDE_APPROVAL, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_change_priority(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.CHANGE_PRIORITY, _resource())
        self.assertFalse(d.allowed)

    def test_viewer_cannot_release(self):
        d = can(_actor(role=TeamRole.VIEWER), Action.RELEASE, _resource())
        self.assertFalse(d.allowed)


class TestMemberRole(unittest.TestCase):
    """Members have conditional access based on reporter/assignee relationship."""

    def test_member_can_create(self):
        d = can(_actor(), Action.CREATE_ITEM, _resource())
        self.assertTrue(d.allowed)

    def test_member_can_comment(self):
        d = can(_actor(), Action.COMMENT, _resource())
        self.assertTrue(d.allowed)

    def test_member_can_claim(self):
        d = can(_actor(), Action.CLAIM, _resource())
        self.assertTrue(d.allowed)

    def test_member_can_transition(self):
        d = can(_actor(), Action.TRANSITION, _resource())
        self.assertTrue(d.allowed)

    def test_member_cannot_assign_others(self):
        d = can(_actor(), Action.ASSIGN, _resource())
        self.assertFalse(d.allowed)

    def test_member_cannot_triage(self):
        d = can(_actor(), Action.TRIAGE, _resource())
        self.assertFalse(d.allowed)

    # --- Edit: reporter or assignee only ---
    def test_member_reporter_can_edit(self):
        d = can(
            _actor(user_id="usr_reporter"),
            Action.EDIT_ITEM,
            _resource(reporter_id="usr_reporter"),
        )
        self.assertTrue(d.allowed)

    def test_member_assignee_can_edit(self):
        d = can(
            _actor(user_id="usr_assignee"),
            Action.EDIT_ITEM,
            _resource(assignee_id="usr_assignee"),
        )
        self.assertTrue(d.allowed)

    def test_member_non_related_cannot_edit(self):
        d = can(
            _actor(user_id="usr_bystander"),
            Action.EDIT_ITEM,
            _resource(reporter_id="usr_reporter", assignee_id="usr_assignee"),
        )
        self.assertFalse(d.allowed)

    # --- Priority: assignee only, P0 is lead-only ---
    def test_member_assignee_can_change_priority(self):
        d = can(
            _actor(user_id="usr_assignee"),
            Action.CHANGE_PRIORITY,
            _resource(assignee_id="usr_assignee", new_priority=ItemPriority.P1),
        )
        self.assertTrue(d.allowed)

    def test_member_non_assignee_cannot_change_priority(self):
        d = can(
            _actor(user_id="usr_other"),
            Action.CHANGE_PRIORITY,
            _resource(assignee_id="usr_assignee", new_priority=ItemPriority.P2),
        )
        self.assertFalse(d.allowed)

    def test_member_assignee_cannot_set_p0(self):
        d = can(
            _actor(user_id="usr_assignee"),
            Action.CHANGE_PRIORITY,
            _resource(assignee_id="usr_assignee", new_priority=ItemPriority.P0),
        )
        self.assertFalse(d.allowed)
        self.assertIn("P0", d.reason)

    # --- Release: own assignment only ---
    def test_member_can_release_own(self):
        d = can(
            _actor(user_id="usr_assignee"),
            Action.RELEASE,
            _resource(assignee_id="usr_assignee"),
        )
        self.assertTrue(d.allowed)

    def test_member_cannot_release_others(self):
        d = can(
            _actor(user_id="usr_other"),
            Action.RELEASE,
            _resource(assignee_id="usr_assignee"),
        )
        self.assertFalse(d.allowed)

    # --- Request approval: assignee only ---
    def test_member_assignee_can_request_approval(self):
        d = can(
            _actor(user_id="usr_assignee"),
            Action.REQUEST_APPROVAL,
            _resource(assignee_id="usr_assignee"),
        )
        self.assertTrue(d.allowed)

    def test_member_non_assignee_cannot_request_approval(self):
        d = can(
            _actor(user_id="usr_other"),
            Action.REQUEST_APPROVAL,
            _resource(assignee_id="usr_assignee"),
        )
        self.assertFalse(d.allowed)

    def test_member_cannot_decide_approval(self):
        d = can(_actor(), Action.DECIDE_APPROVAL, _resource())
        self.assertFalse(d.allowed)


class TestLeadRole(unittest.TestCase):
    """Leads have full access to item operations."""

    def test_lead_can_edit(self):
        d = can(_actor(role=TeamRole.LEAD), Action.EDIT_ITEM, _resource())
        self.assertTrue(d.allowed)

    def test_lead_can_change_priority_to_p0(self):
        d = can(
            _actor(role=TeamRole.LEAD),
            Action.CHANGE_PRIORITY,
            _resource(new_priority=ItemPriority.P0),
        )
        self.assertTrue(d.allowed)

    def test_lead_can_assign(self):
        d = can(_actor(role=TeamRole.LEAD), Action.ASSIGN, _resource())
        self.assertTrue(d.allowed)

    def test_lead_can_triage(self):
        d = can(_actor(role=TeamRole.LEAD), Action.TRIAGE, _resource())
        self.assertTrue(d.allowed)

    def test_lead_can_release_anyone(self):
        d = can(
            _actor(user_id="usr_lead", role=TeamRole.LEAD),
            Action.RELEASE,
            _resource(assignee_id="usr_someone_else"),
        )
        self.assertTrue(d.allowed)

    def test_lead_can_request_approval(self):
        d = can(_actor(role=TeamRole.LEAD), Action.REQUEST_APPROVAL, _resource())
        self.assertTrue(d.allowed)


class TestFourEyesRule(unittest.TestCase):
    """The person who requested the approval cannot be the one to decide it."""

    def test_lead_can_decide_others_approval(self):
        d = can(
            _actor(user_id="usr_lead_b", role=TeamRole.LEAD),
            Action.DECIDE_APPROVAL,
            _resource(approval_requester_id="usr_lead_a"),
        )
        self.assertTrue(d.allowed)

    def test_lead_cannot_decide_own_approval(self):
        d = can(
            _actor(user_id="usr_lead_a", role=TeamRole.LEAD),
            Action.DECIDE_APPROVAL,
            _resource(approval_requester_id="usr_lead_a"),
        )
        self.assertFalse(d.allowed)
        self.assertIn("Four-eyes", d.reason)


if __name__ == "__main__":
    unittest.main()
