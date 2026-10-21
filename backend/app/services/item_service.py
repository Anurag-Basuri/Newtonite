"""
Item business service layer.
Coordinates repositories, UnitOfWork transactions, pure authorization policy,
and table-driven workflow validation.

CRITICAL INVARIANTS:
1. Every method loads the actor's context and calls `policy.can(...)`.
   If denied and not visible, raises NotFoundError (404). If denied, raises ForbiddenError (403).
2. Every multi-document mutation runs inside `UnitOfWork.run`.
3. Every mutation atomically writes:
     [Item state mutation + ItemEvent audit log + Outbox messages + Idempotency record].
4. Claim and approval use atomic compare-and-set preconditions.
5. Edits and transitions use optimistic locking conditioned on `version`.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import (
    NotFoundError,
    ForbiddenError,
    PreconditionFailedError,
    PreconditionRequiredError,
    ConflictError,
    ValidationError,
)
from app.db.uow import UnitOfWork
from app.domain.attention import calculate_attention_due_at
from app.domain.enums import (
    EventType,
    ItemPriority,
    ItemResolution,
    ItemStatus,
    ItemType,
    OutboxType,
    TeamRole,
)
from app.domain.policy import (
    Action,
    ActorCtx,
    ResourceCtx,
    can,
    compute_permissions,
)
from app.domain.workflow import (
    WorkflowError,
    allowed_transitions,
    validate_transition,
)
from app.domain.models.base import generate_id, utc_now
from app.infra.idempotency import IdempotencyService
from app.infra.outbox import OutboxService
from app.repositories.approvals import ApprovalRepository
from app.repositories.events import EventRepository
from app.repositories.items import ItemRepository
from app.repositories.teams import TeamRepository


class ItemService:
    def __init__(self, db: AsyncDatabase, uow: UnitOfWork) -> None:
        self.db = db
        self.uow = uow
        self.items = ItemRepository(db)
        self.events = EventRepository(db)
        self.teams = TeamRepository(db)
        self.approvals = ApprovalRepository(db)

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

    def _check_auth(
        self,
        actor: ActorCtx,
        action: Action,
        resource: ResourceCtx,
    ) -> None:
        decision = can(actor, action, resource)
        if not decision.allowed:
            if decision.not_visible:
                raise NotFoundError(detail="Work item or team not found.")
            raise ForbiddenError(detail=decision.reason)

    async def get_item(
        self,
        identifier: str,
        actor_id: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Load item, enforce authorization, compute advisory UI permissions."""
        item = await self.items.get_by_id_or_key(identifier)
        if not item:
            raise NotFoundError(detail="Work item not found.")

        actor = self._build_actor_ctx(actor_id, is_org_admin, memberships, item["team_id"])
        resource = ResourceCtx(
            team_id=item["team_id"],
            reporter_id=item.get("reporter_id"),
            assignee_id=item.get("assignee_id"),
            status=ItemStatus(item["status"]),
        )
        self._check_auth(actor, Action.READ_ITEM, resource)

        # Attach computed permissions and team metadata
        team = await self.teams.get_by_id(item["team_id"])
        item["team"] = {
            "id": team["_id"] if team else item["team_id"],
            "name": team["name"] if team else "",
            "key_prefix": team["key_prefix"] if team else "",
        }
        item["permissions"] = compute_permissions(actor, resource)
        return item

    async def list_items(
        self,
        actor_id: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        team_ids: Optional[List[str]] = None,
        view: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_id: Optional[str] = None,
        cursor_data: Optional[Tuple[str, datetime, str]] = None,
        limit: int = 25,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """List items keyset-paginated, filtered to caller's authorized teams."""
        user_team_ids = [m["team_id"] for m in memberships]
        if not user_team_ids and not is_org_admin:
            return [], False

        # If user explicitly requested specific teams, restrict to caller's teams
        if team_ids:
            if not is_org_admin:
                target_teams = [t for t in team_ids if t in user_team_ids]
            else:
                target_teams = team_ids
        else:
            if is_org_admin:
                all_teams = await self.teams.list_all_teams()
                target_teams = [t["_id"] for t in all_teams]
            else:
                target_teams = user_team_ids

        if not target_teams:
            return [], False

        return await self.items.list_items_keyset(
            target_teams,
            view=view,
            user_id=actor_id,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            cursor_data=cursor_data,
            limit=limit,
        )

    async def create_item(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        team_id: str,
        title: str,
        description: str,
        item_type: ItemType,
        priority: ItemPriority = ItemPriority.P2,
        due_at: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        Create a new work item atomically inside UnitOfWork.
        Generates human-readable key from team counter, appends ITEM_CREATED event,
        and enqueues background search indexing & notification jobs.
        """
        actor = self._build_actor_ctx(actor_id, is_org_admin, memberships, team_id)
        resource = ResourceCtx(team_id=team_id, new_priority=priority)
        self._check_auth(actor, Action.CREATE_ITEM, resource)

        if priority == ItemPriority.P0 and actor.role_in_team != TeamRole.LEAD:
            raise ForbiddenError(detail="Only team leads can set priority to P0.")

        async def _txn_callback(session):
            # 1. Increment team counter to get human key (e.g. PAY-143)
            key_prefix, counter = await self.teams.increment_item_counter(session, team_id)
            human_key = f"{key_prefix}-{counter}"
            item_id = generate_id("itm")
            now = utc_now()
            attention_due = calculate_attention_due_at(priority, ItemStatus.OPEN, now)

            type_val = item_type.value if hasattr(item_type, "value") else str(item_type)
            prio_val = priority.value if hasattr(priority, "value") else str(priority)

            item_doc = {
                "_id": item_id,
                "team_id": team_id,
                "key": human_key,
                "title": title.strip(),
                "description": description.strip(),
                "type": type_val,
                "status": ItemStatus.OPEN.value,
                "priority": prio_val,
                "resolution": None,
                "duplicate_of": None,
                "reporter_id": actor_id,
                "assignee_id": None,
                "assigned_at": None,
                "due_at": due_at,
                "tags": tags or [],
                "version": 1,
                "event_seq": 1,
                "created_at": now,
                "updated_at": now,
                "last_activity_at": now,
                "attention_due_at": attention_due,
                "pending_approval_id": None,
            }

            # 2. Insert work item
            await self.items.create_item_in_session(session, item_doc)

            # 3. Append ITEM_CREATED event
            event_doc = await self.events.append_event_in_session(
                session,
                item_id=item_id,
                team_id=team_id,
                seq=1,
                event_type=EventType.ITEM_CREATED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={"title": title, "type": type_val, "priority": prio_val},
            )

            # 4. Enqueue outbox side effects
            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.INDEX_ITEM,
                {"item_id": item_id, "team_id": team_id, "content_version": 1},
            )

            # 5. Record idempotency in the same transaction
            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=201,
                response_body=item_doc,
            )
            return item_doc

        return await self.uow.run(_txn_callback)

    async def claim_item(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        ATOMIC COMPARE-AND-SET CLAIM:
        One winner commits; losers receive AlreadyClaimedError (409) naming the winner.
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
        self._check_auth(actor, Action.CLAIM, resource)

        real_id = item["_id"]

        async def _txn_callback(session):
            updated_item = await self.items.claim_item_cas(session, real_id, actor_id)

            # Append audit event
            await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.ITEM_CLAIMED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={"assignee_id": actor_id, "action": "claimed"},
            )

            # Enqueue outbox notification
            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.NOTIFY,
                {
                    "item_id": real_id,
                    "team_id": item["team_id"],
                    "event_type": EventType.ITEM_CLAIMED.value,
                    "title": f"Item {item['key']} claimed by {actor_name}",
                    "recipient_user_ids": [item["reporter_id"]] if item.get("reporter_id") != actor_id else [],
                },
            )

            # Record idempotency
            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=200,
                response_body=updated_item,
            )
            return updated_item

        return await self.uow.run(_txn_callback)

    async def release_item(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """ATOMIC RELEASE: Only the current assignee (or lead) can release."""
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
        self._check_auth(actor, Action.RELEASE, resource)

        real_id = item["_id"]

        async def _txn_callback(session):
            updated_item = await self.items.release_item_cas(session, real_id, actor_id)

            await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.ITEM_RELEASED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={"previous_assignee_id": actor_id, "action": "released"},
            )

            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=200,
                response_body=updated_item,
            )
            return updated_item

        return await self.uow.run(_txn_callback)

    async def update_item_fields(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        expected_version: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[ItemPriority] = None,
        due_at: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        OPTIMISTIC LOCKING UPDATE:
        Requires `If-Match: <expected_version>`. Returns 412 VERSION_CONFLICT if stale.
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
            new_priority=priority,
        )
        self._check_auth(actor, Action.EDIT_ITEM, resource)

        if priority and priority != item["priority"]:
            self._check_auth(actor, Action.CHANGE_PRIORITY, resource)

        real_id = item["_id"]
        fields_to_set: Dict[str, Any] = {}
        changes: Dict[str, Any] = {}

        if title is not None and title.strip() != item["title"]:
            fields_to_set["title"] = title.strip()
            changes["title"] = {"old": item["title"], "new": title.strip()}

        if description is not None and description.strip() != item["description"]:
            fields_to_set["description"] = description.strip()
            changes["description"] = {"old": item["description"][:50], "new": description.strip()[:50]}

        if priority is not None and priority.value != item["priority"]:
            fields_to_set["priority"] = priority.value
            fields_to_set["attention_due_at"] = calculate_attention_due_at(priority, ItemStatus(item["status"]))
            changes["priority"] = {"old": item["priority"], "new": priority.value}

        if tags is not None and tags != item.get("tags", []):
            fields_to_set["tags"] = tags
            changes["tags"] = {"old": item.get("tags", []), "new": tags}

        if due_at is not None and due_at != item.get("due_at"):
            fields_to_set["due_at"] = due_at
            changes["due_at"] = {"old": item.get("due_at"), "new": due_at}

        if not fields_to_set:
            return item

        async def _txn_callback(session):
            updated_item = await self.items.update_with_version_cas(
                session, real_id, expected_version, fields_to_set
            )

            await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.ITEM_UPDATED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={"changes": changes},
            )

            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.INDEX_ITEM,
                {"item_id": real_id, "team_id": item["team_id"], "content_version": updated_item["version"]},
            )
            return updated_item

        return await self.uow.run(_txn_callback)

    async def transition_item(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        to_status: ItemStatus,
        expected_version: int,
        reason: Optional[str] = None,
        resolution: Optional[ItemResolution] = None,
        duplicate_of: Optional[str] = None,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        VALIDATE AND EXECUTE WORKFLOW STATE TRANSITION:
        Enforces state machine table rows, role limits, resolution requirements,
        and optimistic version check.
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
        self._check_auth(actor, Action.TRANSITION, resource)

        from_status = ItemStatus(item["status"])
        is_assignee = (item.get("assignee_id") == actor_id)

        # Validate transition using table-driven workflow engine
        try:
            transition = validate_transition(
                from_status,
                to_status,
                actor_role=actor.role_in_team or TeamRole.VIEWER,
                is_assignee=is_assignee,
                reason=reason,
                resolution=resolution,
                duplicate_of=duplicate_of,
                via_approval_endpoint=False,
            )
        except WorkflowError as e:
            raise ConflictError(
                detail=e.detail,
                code=e.code,
                meta={"allowed_transitions": e.allowed},
            )

        real_id = item["_id"]
        fields_to_set: Dict[str, Any] = {
            "status": to_status.value,
            "attention_due_at": calculate_attention_due_at(ItemPriority(item["priority"]), to_status),
        }
        if reason:
            fields_to_set["blocked_reason"] = reason if to_status == ItemStatus.BLOCKED else None
        if resolution:
            fields_to_set["resolution"] = resolution.value
        if duplicate_of:
            fields_to_set["duplicate_of"] = duplicate_of

        async def _txn_callback(session):
            updated_item = await self.items.update_with_version_cas(
                session, real_id, expected_version, fields_to_set
            )

            await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.ITEM_TRANSITIONED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={
                    "from_status": from_status.value,
                    "to_status": to_status.value,
                    "action": transition.action,
                    "reason": reason,
                    "resolution": resolution.value if resolution else None,
                    "duplicate_of": duplicate_of,
                },
            )

            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.NOTIFY,
                {
                    "item_id": real_id,
                    "team_id": item["team_id"],
                    "event_type": EventType.ITEM_TRANSITIONED.value,
                    "title": f"Item {item['key']} transitioned to {to_status.value} by {actor_name}",
                    "recipient_user_ids": [u for u in [item.get("reporter_id"), item.get("assignee_id")] if u and u != actor_id],
                },
            )

            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=200,
                response_body=updated_item,
            )
            return updated_item

        return await self.uow.run(_txn_callback)

    async def add_comment(
        self,
        actor_id: str,
        actor_name: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        *,
        item_id: str,
        body: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Dict[str, Any]:
        """
        POST A COMMENT:
        Comments are immutable events. Comments do NOT bump item.version,
        so commenting never causes a 412 version conflict for concurrent editors.
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
        self._check_auth(actor, Action.COMMENT, resource)

        real_id = item["_id"]

        async def _txn_callback(session):
            # Bump event_seq monotonically on item without bumping version
            updated_item = await self.db.work_items.find_one_and_update(
                {"_id": real_id},
                {"$inc": {"event_seq": 1}, "$set": {"last_activity_at": utc_now()}},
                return_document=True,
                session=session,
            )

            event_doc = await self.events.append_event_in_session(
                session,
                item_id=real_id,
                team_id=item["team_id"],
                seq=updated_item["event_seq"],
                event_type=EventType.ITEM_COMMENTED,
                actor_id=actor_id,
                actor_name=actor_name,
                data={"body": body.strip()},
            )

            await OutboxService.enqueue_in_session(
                session,
                self.db,
                OutboxType.NOTIFY,
                {
                    "item_id": real_id,
                    "team_id": item["team_id"],
                    "event_type": EventType.ITEM_COMMENTED.value,
                    "title": f"New comment on {item['key']} by {actor_name}",
                    "recipient_user_ids": [u for u in [item.get("reporter_id"), item.get("assignee_id")] if u and u != actor_id],
                },
            )

            await IdempotencyService.record_in_session(
                session,
                self.db,
                user_id=actor_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_status=201,
                response_body=event_doc,
            )
            return event_doc

        return await self.uow.run(_txn_callback)

    async def get_timeline(
        self,
        identifier: str,
        actor_id: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
        since_seq: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve ordered audit timeline events for an item."""
        item = await self.items.get_by_id_or_key(identifier)
        if not item:
            raise NotFoundError(detail="Work item not found.")

        actor = self._build_actor_ctx(actor_id, is_org_admin, memberships, item["team_id"])
        resource = ResourceCtx(
            team_id=item["team_id"],
            reporter_id=item.get("reporter_id"),
            assignee_id=item.get("assignee_id"),
            status=ItemStatus(item["status"]),
        )
        self._check_auth(actor, Action.READ_ITEM, resource)

        return await self.events.get_timeline(item["_id"], since_seq=since_seq, limit=limit)
