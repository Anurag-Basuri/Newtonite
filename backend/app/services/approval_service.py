"""
Approval business service layer.
Enforces the four-eyes rule (a user cannot approve their own request),
gated status transitions, and atomic decision conditional updates.
"""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import NotFoundError, ForbiddenError, ConflictError
from app.db.uow import UnitOfWork
from app.domain.attention import calculate_attention_due_at
from app.domain.enums import (
    ApprovalStatus,
    EventType,
    ItemPriority,
    ItemStatus,
    OutboxType,
    TeamRole,
)
from app.domain.policy import Action, ActorCtx, ResourceCtx, can
from app.domain.workflow import validate_transition, WorkflowError
from app.domain.models.base import utc_now
from app.infra.idempotency import IdempotencyService
from app.infra.outbox import OutboxService
from app.repositories.approvals import ApprovalRepository
from app.repositories.events import EventRepository
from app.repositories.items import ItemRepository


class ApprovalService:
    def __init__(self, db: AsyncDatabase, uow: UnitOfWork) -> None:
        self.db = db
        self.uow = uow
        self.items = ItemRepository(db)
        self.approvals = ApprovalRepository(db)
        self.events = EventRepository(db)

    def _build_actor_ctx(
        self,
        actor_id: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        team_id: str,
    ) -> ActorCtx:
        role_in_team = None
        for m in memberships:
            if m["team_id"] == team_id:
                role_in_team = TeamRole(m["role"])
                break
        return ActorCtx(user_id=actor_id, is_org_admin=is_org_admin, role_in_team=role_in_team)

    async def request_approval(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        request_note: str,
        expected_version: int,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        Request approval for an item. Transitions item to PENDING_APPROVAL.
        Guarantees that only one pending approval can exist at a time.
        """
        item = await self.items.get_by_id_or_key(item_id)
        if not item:
            raise NotFoundError(detail="Work item not found.")

        actor = self._build_actor_ctx(actor_id, is_org_admin, memberships, item["team_id"])
        resource = ResourceCtx(
            team_id=item["team_id"],
            reporter_id=item.get("reporter_id"),
            assignee_id=item.get("assignee_id"),
            status=ItemStatus(item["status"]),
        )
        decision = can(actor, Action.REQUEST_APPROVAL, resource)
        if not decision.allowed:
            if decision.not_visible:
                raise NotFoundError(detail="Work item not found.")
            raise ForbiddenError(detail=decision.reason)

        real_id = item["_id"]
        from_status = ItemStatus(item["status"])
        is_assignee = (item.get("assignee_id") == actor_id)

        try:
            validate_transition(
                from_status,
                ItemStatus.PENDING_APPROVAL,
                actor_role=actor.role_in_team or TeamRole.VIEWER,
                is_assignee=is_assignee,
                reason=request_note,
            )
        except WorkflowError as e:
            raise ConflictError(detail=e.detail, code=e.code)

        async def _txn_callback(session):
            # 1. Create approval document (unique partial index guarantees single pending)
            approval_doc = await self.approvals.create_approval_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                requested_by=actor_id,
                request_note=request_note.strip(),
            )

            # 2. Update item to PENDING_APPROVAL with pending_approval_id
            fields = {
                "status": ItemStatus.PENDING_APPROVAL.value,
                "pending_approval_id": approval_doc["_id"],
                "attention_due_at": calculate_attention_due_at(ItemPriority(item["priority"]), ItemStatus.PENDING_APPROVAL),
            }
            updated_item = await self.items.update_with_version_cas(
                session, real_id, expected_version, fields
            )

            # 3. Append event
            await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.APPROVAL_REQUESTED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={
                    "approval_id": approval_doc["_id"],
                    "request_note": request_note.strip(),
                },
            )

            # 4. Outbox notification
            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.NOTIFY,
                {
                    "item_id": real_id,
                    "team_id": item["team_id"],
                    "event_type": EventType.APPROVAL_REQUESTED.value,
                    "title": f"Approval requested on {item['key']} by {actor_name}",
                    "recipient_user_ids": [],  # Worker will fan out to team leads
                },
            )

            # 5. Idempotency record
            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=200,
                response_body=approval_doc,
            )
            return approval_doc

        return await self.uow.run(_txn_callback)

    async def decide_approval(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        approval_id: str,
        approved: bool,
        decision_reason: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        Decide an approval request (approve or reject).
        ENFORCES FOUR-EYES RULE: the decider CANNOT be the requester.
        """
        approval = await self.approvals.get_by_id(approval_id)
        if not approval:
            raise NotFoundError(detail="Approval request not found.")

        item = await self.items.get_by_id_or_key(approval["item_id"])
        if not item:
            raise NotFoundError(detail="Work item not found.")

        actor = self._build_actor_ctx(actor_id, is_org_admin, memberships, item["team_id"])
        resource = ResourceCtx(
            team_id=item["team_id"],
            reporter_id=item.get("reporter_id"),
            assignee_id=item.get("assignee_id"),
            status=ItemStatus(item["status"]),
            approval_requester_id=approval["requested_by"],
        )
        decision = can(actor, Action.DECIDE_APPROVAL, resource)
        if not decision.allowed:
            if decision.not_visible:
                raise NotFoundError(detail="Work item not found.")
            raise ForbiddenError(detail=decision.reason)

        real_item_id = item["_id"]
        target_status = ItemStatus.RESOLVED if approved else ItemStatus.IN_PROGRESS
        approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED

        async def _txn_callback(session):
            # 1. Decide approval with CAS
            updated_approval = await self.approvals.decide_approval_cas(
                session,
                approval_id=approval_id,
                status=approval_status,
                decided_by=actor_id,
                decision_reason=decision_reason.strip(),
            )

            # 2. Update work item status and clear pending_approval_id
            fields = {
                "status": target_status.value,
                "pending_approval_id": None,
                "attention_due_at": calculate_attention_due_at(ItemPriority(item["priority"]), target_status),
            }
            if approved:
                fields["resolution"] = "completed"

            updated_item = await self.items.update_with_version_cas(
                session, real_item_id, item["version"], fields
            )

            # 3. Append event
            await self.events.append_event_in_session(
                session,
                item_id=real_item_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.APPROVAL_DECIDED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={
                    "approval_id": approval_id,
                    "approved": approved,
                    "decision_reason": decision_reason.strip(),
                    "new_status": target_status.value,
                },
            )

            # 4. Outbox notification
            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.NOTIFY,
                {
                    "item_id": real_item_id,
                    "team_id": item["team_id"],
                    "event_type": EventType.APPROVAL_DECIDED.value,
                    "title": f"Approval {'approved' if approved else 'rejected'} on {item['key']} by {actor_name}",
                    "recipient_user_ids": [approval["requested_by"]],
                },
            )

            # 5. Idempotency record
            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=200,
                response_body=updated_approval,
            )
            return updated_approval

        return await self.uow.run(_txn_callback)
