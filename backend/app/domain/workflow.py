"""
Table-driven workflow state machine for work items.

Every legal state transition is declared as data. The service layer calls
`validate_transition()` — if it returns a `Transition`, the move is legal;
if it raises, the move is rejected with a precise error.

Design notes (from SYSTEM_DESIGN §5.1):
  - Transitions are rows, not if/else chains, so they are exhaustively testable.
  - Approval transitions (approve → resolved, reject → in_progress) are flagged
    `approval_only=True` and can ONLY be triggered through the approval endpoints,
    never through the generic `/transitions` endpoint.
  - Cancel always moves to `closed` and requires a resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.domain.enums import ItemStatus, ItemResolution, TeamRole


@dataclass(frozen=True)
class Transition:
    """
    One legal edge in the workflow state machine.

    Attributes:
        from_status:              Source state.
        to_status:                Target state.
        action:                   Human-readable verb for audit events.
        min_role:                 Minimum team role required (viewer < member < lead).
        requires_assignee:        If True, the actor must be the current assignee
                                  (or a lead, who can always act).
        requires_reason:          If True, a reason string is mandatory in the request.
        requires_resolution:      If True, a resolution enum is mandatory (close/cancel).
        approval_only:            If True, this transition is only reachable via the
                                  approval decision endpoint, not the generic transition.
    """
    from_status: ItemStatus
    to_status: ItemStatus
    action: str
    min_role: TeamRole = TeamRole.MEMBER
    requires_assignee: bool = False
    requires_reason: bool = False
    requires_resolution: bool = False
    approval_only: bool = False


# ---------------------------------------------------------------------------
# Transition table — the single source of truth for the workflow
# ---------------------------------------------------------------------------

TRANSITIONS: list[Transition] = [
    # --- Triage ---
    Transition(
        from_status=ItemStatus.OPEN,
        to_status=ItemStatus.TRIAGED,
        action="triage",
        min_role=TeamRole.LEAD,
    ),

    # --- Start work ---
    Transition(
        from_status=ItemStatus.OPEN,
        to_status=ItemStatus.IN_PROGRESS,
        action="start",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
    ),
    Transition(
        from_status=ItemStatus.TRIAGED,
        to_status=ItemStatus.IN_PROGRESS,
        action="start",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
    ),

    # --- Block / unblock ---
    Transition(
        from_status=ItemStatus.IN_PROGRESS,
        to_status=ItemStatus.BLOCKED,
        action="block",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
        requires_reason=True,
    ),
    Transition(
        from_status=ItemStatus.BLOCKED,
        to_status=ItemStatus.IN_PROGRESS,
        action="unblock",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
    ),

    # --- Resolve (without approval) ---
    Transition(
        from_status=ItemStatus.IN_PROGRESS,
        to_status=ItemStatus.RESOLVED,
        action="resolve",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
    ),

    # --- Approval flow (approval_only — not reachable from generic transition) ---
    Transition(
        from_status=ItemStatus.IN_PROGRESS,
        to_status=ItemStatus.PENDING_APPROVAL,
        action="request_approval",
        min_role=TeamRole.MEMBER,
        requires_assignee=True,
    ),
    Transition(
        from_status=ItemStatus.PENDING_APPROVAL,
        to_status=ItemStatus.RESOLVED,
        action="approve",
        min_role=TeamRole.LEAD,
        approval_only=True,
    ),
    Transition(
        from_status=ItemStatus.PENDING_APPROVAL,
        to_status=ItemStatus.IN_PROGRESS,
        action="reject",
        min_role=TeamRole.LEAD,
        requires_reason=True,
        approval_only=True,
    ),

    # --- Close ---
    Transition(
        from_status=ItemStatus.RESOLVED,
        to_status=ItemStatus.CLOSED,
        action="close",
        min_role=TeamRole.LEAD,
        requires_resolution=True,
    ),

    # --- Reopen ---
    Transition(
        from_status=ItemStatus.RESOLVED,
        to_status=ItemStatus.IN_PROGRESS,
        action="reopen",
        min_role=TeamRole.MEMBER,
        requires_reason=True,
    ),
    Transition(
        from_status=ItemStatus.CLOSED,
        to_status=ItemStatus.OPEN,
        action="reopen",
        min_role=TeamRole.LEAD,
        requires_reason=True,
    ),

    # --- Cancel (from any active non-resolved state → closed) ---
    Transition(
        from_status=ItemStatus.OPEN,
        to_status=ItemStatus.CLOSED,
        action="cancel",
        min_role=TeamRole.LEAD,
        requires_resolution=True,
    ),
    Transition(
        from_status=ItemStatus.TRIAGED,
        to_status=ItemStatus.CLOSED,
        action="cancel",
        min_role=TeamRole.LEAD,
        requires_resolution=True,
    ),
    Transition(
        from_status=ItemStatus.IN_PROGRESS,
        to_status=ItemStatus.CLOSED,
        action="cancel",
        min_role=TeamRole.LEAD,
        requires_resolution=True,
    ),
    Transition(
        from_status=ItemStatus.BLOCKED,
        to_status=ItemStatus.CLOSED,
        action="cancel",
        min_role=TeamRole.LEAD,
        requires_resolution=True,
    ),
]

# Pre-built lookup: (from_status, to_status) → Transition
_TRANSITION_MAP: dict[tuple[ItemStatus, ItemStatus], Transition] = {
    (t.from_status, t.to_status): t for t in TRANSITIONS
}

# Valid cancel resolutions
CANCEL_RESOLUTIONS = {ItemResolution.WONT_DO, ItemResolution.DUPLICATE, ItemResolution.CANCELLED}
CLOSE_RESOLUTIONS = {ItemResolution.COMPLETED, ItemResolution.WONT_DO, ItemResolution.DUPLICATE, ItemResolution.CANCELLED}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class WorkflowError(Exception):
    """Raised when a transition is invalid."""
    def __init__(self, code: str, detail: str, *, allowed: list[str] | None = None):
        self.code = code
        self.detail = detail
        self.allowed = allowed or []
        super().__init__(detail)


def get_transition(
    from_status: ItemStatus,
    to_status: ItemStatus,
) -> Transition | None:
    """Look up a transition. Returns None if it doesn't exist."""
    return _TRANSITION_MAP.get((from_status, to_status))


def allowed_transitions(
    from_status: ItemStatus,
    *,
    include_approval_only: bool = False,
) -> list[Transition]:
    """Return all transitions legal from a given status."""
    return [
        t for t in TRANSITIONS
        if t.from_status == from_status
        and (include_approval_only or not t.approval_only)
    ]


def validate_transition(
    from_status: ItemStatus,
    to_status: ItemStatus,
    *,
    actor_role: TeamRole,
    is_assignee: bool,
    reason: str | None = None,
    resolution: ItemResolution | None = None,
    duplicate_of: str | None = None,
    via_approval_endpoint: bool = False,
) -> Transition:
    """
    Validate a proposed state transition. Returns the matched Transition on
    success; raises WorkflowError with a precise code on failure.

    Args:
        from_status:          Current item status.
        to_status:            Desired target status.
        actor_role:           The actor's role in the item's team.
        is_assignee:          Whether the actor is the current assignee.
        reason:               Optional reason text from the request.
        resolution:           Optional resolution from the request.
        duplicate_of:         Optional duplicate item reference.
        via_approval_endpoint: True when called from approve/reject handlers.
    """
    transition = get_transition(from_status, to_status)

    # 1. Does this edge exist at all?
    if transition is None:
        valid = allowed_transitions(from_status)
        raise WorkflowError(
            code="INVALID_TRANSITION",
            detail=f"Cannot move from '{from_status}' to '{to_status}'.",
            allowed=[t.to_status.value for t in valid],
        )

    # 2. Approval-only transitions must come from the approval endpoint
    if transition.approval_only and not via_approval_endpoint:
        raise WorkflowError(
            code="INVALID_TRANSITION",
            detail=f"The '{transition.action}' transition must go through the approval endpoint.",
        )

    # 3. Non-approval transitions must NOT come from the approval endpoint
    if not transition.approval_only and via_approval_endpoint:
        raise WorkflowError(
            code="INVALID_TRANSITION",
            detail=f"The '{transition.action}' transition is not an approval action.",
        )

    # 4. Role check
    if not actor_role >= transition.min_role:
        raise WorkflowError(
            code="FORBIDDEN",
            detail=f"'{transition.action}' requires at least '{transition.min_role}' role.",
        )

    # 5. Assignee check — leads bypass this (they can always act)
    if transition.requires_assignee and not is_assignee and actor_role != TeamRole.LEAD:
        raise WorkflowError(
            code="FORBIDDEN",
            detail=f"'{transition.action}' requires you to be the assignee (or a lead).",
        )

    # 6. Reason required?
    if transition.requires_reason and not reason:
        raise WorkflowError(
            code="VALIDATION_ERROR",
            detail=f"'{transition.action}' requires a reason.",
        )

    # 7. Resolution required?
    if transition.requires_resolution:
        if not resolution:
            raise WorkflowError(
                code="VALIDATION_ERROR",
                detail=f"'{transition.action}' requires a resolution.",
            )
        # Cancel actions only accept cancel-appropriate resolutions
        if transition.action == "cancel" and resolution not in CANCEL_RESOLUTIONS:
            raise WorkflowError(
                code="VALIDATION_ERROR",
                detail=f"Cancel requires one of: {', '.join(r.value for r in CANCEL_RESOLUTIONS)}.",
            )
        # Close from resolved accepts all resolutions
        if transition.action == "close" and resolution not in CLOSE_RESOLUTIONS:
            raise WorkflowError(
                code="VALIDATION_ERROR",
                detail=f"Close requires one of: {', '.join(r.value for r in CLOSE_RESOLUTIONS)}.",
            )
        # Duplicate resolution requires duplicate_of reference
        if resolution == ItemResolution.DUPLICATE and not duplicate_of:
            raise WorkflowError(
                code="VALIDATION_ERROR",
                detail="Resolution 'duplicate' requires a 'duplicate_of' item reference.",
            )

    return transition
