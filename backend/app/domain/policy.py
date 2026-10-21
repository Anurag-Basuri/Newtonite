"""
Pure authorization policy for Opsboard.

A single decision point: `can(actor, action, resource_ctx) → Decision`.
No I/O, no database calls. The service layer loads the actor's context and
the resource context, then calls this module. If the decision is `deny`,
the service raises the appropriate domain error.

Design notes (from SYSTEM_DESIGN §5.2):
  - Org admins can manage teams/memberships and read all items, but they
    have NO implicit write rights on items — they must be a team member.
  - Non-members get 404 (no existence leakage), not 403.
  - The four-eyes rule on approvals: the decider cannot be the requester.
  - Setting priority to P0 is lead-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.domain.enums import TeamRole, ItemPriority, ItemStatus


# ---------------------------------------------------------------------------
# Action enumeration
# ---------------------------------------------------------------------------

class Action(str, Enum):
    """All authorization-checked actions in the system."""
    # Item CRUD
    READ_ITEM = "read_item"
    CREATE_ITEM = "create_item"
    EDIT_ITEM = "edit_item"              # title, description, tags, due_at
    CHANGE_PRIORITY = "change_priority"

    # Ownership
    CLAIM = "claim"
    RELEASE = "release"
    ASSIGN = "assign"

    # Workflow
    TRANSITION = "transition"    # generic transitions checked via workflow.py
    TRIAGE = "triage"

    # Timeline
    COMMENT = "comment"

    # Approvals
    REQUEST_APPROVAL = "request_approval"
    DECIDE_APPROVAL = "decide_approval"

    # AI
    USE_AI = "use_ai"

    # Admin
    MANAGE_TEAMS = "manage_teams"


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    """
    Authorization decision.

    allowed=True  → proceed.
    allowed=False → raise 403 FORBIDDEN (or 404 if not_visible).
    """
    allowed: bool
    reason: str = ""
    not_visible: bool = False   # True → return 404 instead of 403


ALLOW = Decision(allowed=True)


def deny(reason: str) -> Decision:
    return Decision(allowed=False, reason=reason)


def invisible() -> Decision:
    """Item is outside the actor's teams → 404, not 403."""
    return Decision(allowed=False, reason="Not found", not_visible=True)


# ---------------------------------------------------------------------------
# Resource context (what the actor is trying to act on)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceCtx:
    """
    Lightweight snapshot of the resource being acted upon.
    Built by the service layer from the loaded item/approval, passed here.
    """
    team_id: str
    reporter_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[ItemStatus] = None
    new_priority: Optional[ItemPriority] = None   # for CHANGE_PRIORITY
    approval_requester_id: Optional[str] = None    # for DECIDE_APPROVAL (four-eyes)


# ---------------------------------------------------------------------------
# Actor context (who is acting)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActorCtx:
    """
    Snapshot of the authenticated user's identity and memberships.
    Built from UserContext by the service layer.
    """
    user_id: str
    is_org_admin: bool = False
    role_in_team: Optional[TeamRole] = None   # None = not a member of the item's team


# ---------------------------------------------------------------------------
# Policy function
# ---------------------------------------------------------------------------

def can(actor: ActorCtx, action: Action, resource: ResourceCtx) -> Decision:
    """
    Pure authorization decision.

    This is the ONLY place in the codebase that decides "is this allowed?".
    It is tested exhaustively as a role × action × relationship matrix.
    """

    # --- Admin-only actions (team/membership management) ---
    if action == Action.MANAGE_TEAMS:
        if actor.is_org_admin:
            return ALLOW
        return deny("Only org admins can manage teams and memberships.")

    # --- Team membership gate ---
    # Org admins can READ items in any team, but for all other actions
    # they need an actual team role.
    if actor.role_in_team is None:
        if action == Action.READ_ITEM and actor.is_org_admin:
            return ALLOW
        if action == Action.USE_AI and actor.is_org_admin:
            return ALLOW
        # Not a member → 404 (no existence leak)
        return invisible()

    role = actor.role_in_team

    # --- Per-action checks ---

    if action == Action.READ_ITEM:
        # Any team member (viewer+) can read
        return ALLOW

    if action == Action.USE_AI:
        # Any team member (viewer+) can use AI features
        return ALLOW

    if action == Action.CREATE_ITEM:
        if role >= TeamRole.MEMBER:
            return ALLOW
        return deny("Viewers cannot create items.")

    if action == Action.COMMENT:
        if role >= TeamRole.MEMBER:
            return ALLOW
        return deny("Viewers cannot comment.")

    if action == Action.EDIT_ITEM:
        if role == TeamRole.LEAD:
            return ALLOW
        if role == TeamRole.MEMBER:
            # Members can edit if they are the reporter or assignee
            if actor.user_id == resource.reporter_id or actor.user_id == resource.assignee_id:
                return ALLOW
            return deny("Members can only edit items they reported or are assigned to.")
        return deny("Viewers cannot edit items.")

    if action == Action.CHANGE_PRIORITY:
        if role == TeamRole.LEAD:
            return ALLOW
        if role == TeamRole.MEMBER:
            # Members can change priority only if they are the assignee
            if actor.user_id != resource.assignee_id:
                return deny("Only the assignee or a lead can change priority.")
            # But setting P0 is lead-only
            if resource.new_priority == ItemPriority.P0:
                return deny("Setting priority to P0 requires lead role.")
            return ALLOW
        return deny("Viewers cannot change priority.")

    if action == Action.CLAIM:
        if role >= TeamRole.MEMBER:
            return ALLOW
        return deny("Viewers cannot claim items.")

    if action == Action.RELEASE:
        if role == TeamRole.LEAD:
            return ALLOW
        if role == TeamRole.MEMBER:
            # Can only release your own assignment
            if actor.user_id == resource.assignee_id:
                return ALLOW
            return deny("You can only release your own assignment.")
        return deny("Viewers cannot release assignments.")

    if action == Action.ASSIGN:
        if role == TeamRole.LEAD:
            return ALLOW
        return deny("Only leads can assign or unassign others.")

    if action == Action.TRIAGE:
        if role == TeamRole.LEAD:
            return ALLOW
        return deny("Only leads can triage items.")

    if action == Action.TRANSITION:
        # The workflow.py state machine handles the detailed role + assignee
        # checks per transition. Here we just ensure the actor is at least
        # a member (viewers can never transition).
        if role >= TeamRole.MEMBER:
            return ALLOW
        return deny("Viewers cannot change item status.")

    if action == Action.REQUEST_APPROVAL:
        if role == TeamRole.LEAD:
            return ALLOW
        if role == TeamRole.MEMBER:
            if actor.user_id == resource.assignee_id:
                return ALLOW
            return deny("Only the assignee or a lead can request approval.")
        return deny("Viewers cannot request approval.")

    if action == Action.DECIDE_APPROVAL:
        if role != TeamRole.LEAD:
            return deny("Only leads can decide approvals.")
        # Four-eyes rule: the decider cannot be the person who requested it
        if actor.user_id == resource.approval_requester_id:
            return deny("Four-eyes rule: you cannot decide an approval you requested.")
        return ALLOW

    # Unknown action — deny by default (fail closed)
    return deny(f"Unknown action: {action}")


def compute_permissions(actor: ActorCtx, resource: ResourceCtx) -> dict[str, Any]:
    """
    Compute advisory permissions dictionary for UI rendering.
    Enables frontend buttons/menus based on pure policy decisions.
    """
    from typing import Any
    return {
        "can_edit": can(actor, Action.EDIT_ITEM, resource).allowed,
        "can_claim": can(actor, Action.CLAIM, resource).allowed,
        "can_release": can(actor, Action.RELEASE, resource).allowed,
        "can_assign": can(actor, Action.ASSIGN, resource).allowed,
        "can_comment": can(actor, Action.COMMENT, resource).allowed,
        "can_request_approval": can(actor, Action.REQUEST_APPROVAL, resource).allowed,
        "can_change_priority": can(actor, Action.CHANGE_PRIORITY, resource).allowed,
    }

