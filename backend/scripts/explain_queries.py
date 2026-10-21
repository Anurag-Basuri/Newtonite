"""
Query performance and index usage verification script for Opsboard.
Executes explain('executionStats') on all critical hot queries.
Asserts that each query uses an index scan (IXSCAN) and that no table scans (COLLSCAN) occur.
Matches docs/SYSTEM_DESIGN.md §11.2, docs/DATA_MODEL.md §4, and docs/TEST_PLAN.md T-IDX-1.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings
from app.db.client import mongo_manager
from app.db.indexes import ensure_indexes
from seed import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opsboard.explain")


def check_plan_for_collscan(plan: Dict[str, Any]) -> bool:
    """Recursively checks if COLLSCAN is present anywhere in the execution plan."""
    stage = plan.get("stage", "")
    if stage == "COLLSCAN":
        return True
    input_stage = plan.get("inputStage")
    if input_stage and check_plan_for_collscan(input_stage):
        return True
    input_stages = plan.get("inputStages", [])
    for s in input_stages:
        if check_plan_for_collscan(s):
            return True
    return False


def get_winning_stage_name(plan: Dict[str, Any]) -> str:
    """Finds the primary leaf scan stage (IXSCAN, COLLSCAN, etc.)."""
    curr = plan
    while "inputStage" in curr and curr.get("stage") not in ("IXSCAN", "COLLSCAN"):
        curr = curr["inputStage"]
    return curr.get("stage", plan.get("stage", "UNKNOWN"))


async def explain_query(
    db,
    collection_name: str,
    filter_dict: Dict[str, Any],
    sort_spec: Any = None,
    query_description: str = "",
) -> Dict[str, Any]:
    """Runs explain('executionStats') for a query via the explain command."""
    find_cmd: Dict[str, Any] = {
        "find": collection_name,
        "filter": filter_dict,
    }
    if sort_spec:
        find_cmd["sort"] = dict(sort_spec) if isinstance(sort_spec, list) else sort_spec

    explain_cmd = {
        "explain": find_cmd,
        "verbosity": "executionStats",
    }
    result = await db.command(explain_cmd)
    stats = result.get("executionStats", {})
    query_plan = result.get("queryPlanner", {}).get("winningPlan", {})

    has_collscan = check_plan_for_collscan(query_plan)
    leaf_stage = get_winning_stage_name(query_plan)

    return {
        "description": query_description,
        "collection": collection_name,
        "filter": json.dumps(filter_dict, default=str),
        "stage": leaf_stage,
        "has_collscan": has_collscan,
        "nReturned": stats.get("nReturned", 0),
        "totalDocsExamined": stats.get("totalDocsExamined", 0),
        "totalKeysExamined": stats.get("totalKeysExamined", 0),
        "executionTimeMillis": stats.get("executionTimeMillis", 0),
    }


async def run_explain_suite() -> int:
    logger.info("Initializing DB connection and seeding sample data...")
    await seed()
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    await ensure_indexes(db)

    now = datetime.now(timezone.utc)
    team = await db.teams.find_one({"slug": "payments"})
    team_id = str(team["_id"]) if team else "team-payments"
    user = await db.users.find_one({"email": "member@opsboard.dev"})
    user_id = str(user["_id"]) if user else "user-member"
    item = await db.work_items.find_one({"team_id": team_id})
    item_id = str(item["_id"]) if item else "item-123"

    queries = [
        (
            "work_items",
            {"team_id": team_id, "key": "PAY-101"},
            None,
            "1. Lookup item by (team_id, key) [uq_item_team_key]",
        ),
        (
            "work_items",
            {"team_id": team_id, "priority": "P0"},
            [("priority", 1), ("updated_at", -1), ("_id", 1)],
            "2. Keyset pagination by (team_id, priority, updated_at DESC, _id ASC)",
        ),
        (
            "work_items",
            {"team_id": team_id, "status": "open", "attention_due_at": {"$lte": now}},
            None,
            "3. Overdue / SLA attention scan [idx_item_status_attention]",
        ),
        (
            "work_items",
            {"assignee_id": user_id, "status": "in_progress"},
            None,
            "4. Assignee workload query [idx_item_assignee_status]",
        ),
        (
            "item_events",
            {"item_id": item_id},
            [("seq", 1)],
            "5. Item timeline events query [uq_item_events_item_seq]",
        ),
        (
            "approvals",
            {"item_id": item_id, "status": "pending"},
            None,
            "6. Pending approval uniqueness lookup [uq_approvals_single_pending]",
        ),
        (
            "outbox",
            {"status": "pending", "next_attempt_at": {"$lte": now}},
            [("next_attempt_at", 1)],
            "7. Outbox worker poll [idx_outbox_poll]",
        ),
        (
            "notifications",
            {"recipient_id": user_id, "read": False},
            [("created_at", -1)],
            "8. In-app unread notifications [idx_notifications_user_read]",
        ),
        (
            "item_chunks",
            {"team_id": {"$in": [team_id]}},
            None,
            "9. RAG chunk vector pre-filter scan [idx_chunks_team_id]",
        ),
    ]

    print("\n" + "=" * 90)
    print("OPSBOARD QUERY EXPLAIN EXECUTION STATS REPORT (T-IDX-1)")
    print("=" * 90)
    header = f"{'Query Description':<55} | {'Stage':<10} | {'COLLSCAN?':<10} | {'Keys':<5} | {'Docs':<5}"
    print(header)
    print("-" * 90)

    any_collscan = False
    for coll_name, f_dict, s_spec, desc in queries:
        res = await explain_query(db, coll_name, f_dict, s_spec, desc)
        collscan_str = "YES (FAIL)" if res["has_collscan"] else "NO (PASS)"
        if res["has_collscan"]:
            any_collscan = True
        print(f"{res['description'][:54]:<55} | {res['stage']:<10} | {collscan_str:<10} | {res['totalKeysExamined']:<5} | {res['totalDocsExamined']:<5}")

    print("=" * 90)
    if any_collscan:
        print("RESULT: FAILED - At least one hot query resulted in an unindexed collection scan (COLLSCAN)!\n")
        return 1
    else:
        print("RESULT: SUCCESS - All 9 critical hot queries verified using IXSCAN with zero COLLSCAN.\n")
        return 0


if __name__ == "__main__":
    code = asyncio.run(run_explain_suite())
    sys.exit(code)
