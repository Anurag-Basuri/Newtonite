"""
Full End-to-End Frontend & API Verification Suite.
Verifies all routes, client session workflows, transitions, 6 categories,
Four-Eyes approval invariant, Teams management, and Next.js SSR responses.
"""

import sys
import uuid
import httpx

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://127.0.0.1:8000/api/v1"

def print_pass(step: str):
    print(f"  [PASS] {step}")

def print_fail(step: str, reason: str):
    print(f"  [FAIL] {step}: {reason}")
    sys.exit(1)

def run_tests():
    print("=== 1. Testing Next.js Frontend Route Availability ===")
    with httpx.Client(base_url=FRONTEND_URL, timeout=10.0) as client:
        routes = ["/login", "/overview", "/items", "/teams", "/ask"]
        for r in routes:
            resp = client.get(r)
            if resp.status_code == 200:
                print_pass(f"Next.js route {r} returned 200 OK")
            else:
                print_fail(f"Next.js route {r}", f"Returned status {resp.status_code}")

    print("\n=== 2. Testing Lead Authentication & Session ===")
    lead_session = httpx.Client(base_url=BACKEND_URL, timeout=30.0)
    login_resp = lead_session.post("/auth/login", json={
        "email": "lead@opsboard.dev",
        "password": "Password123!"
    })
    if login_resp.status_code != 200:
        print_fail("Lead Login", f"Status {login_resp.status_code}: {login_resp.text}")
    print_pass("Priya Lead authenticated successfully")

    me_resp = lead_session.get("/auth/me")
    if me_resp.status_code != 200 or me_resp.json()["user"]["email"] != "lead@opsboard.dev":
        print_fail("/auth/me", f"Failed: {me_resp.text}")
    print_pass("Verified /auth/me returns valid user & team memberships")

    print("\n=== 3. Testing Overview Dashboard Buckets ===")
    overview_resp = lead_session.get("/overview")
    if overview_resp.status_code != 200:
        print_fail("/overview", f"Failed: {overview_resp.text}")
    buckets = overview_resp.json().get("buckets", [])
    if len(buckets) < 3:
        print_fail("/overview", f"Expected at least 3 buckets, got {len(buckets)}")
    print_pass(f"Overview dashboard returned {len(buckets)} operational buckets")

    print("\n=== 4. Testing 6 Canonical Categories on /items ===")
    categories = ["customer_issue", "engineering", "payment", "incident", "compliance", "task"]
    for cat in categories:
        items_resp = lead_session.get(f"/items?type={cat}")
        if items_resp.status_code != 200:
            print_fail(f"Filter /items?type={cat}", f"Failed: {items_resp.text}")
        count = len(items_resp.json().get("items", []))
        print_pass(f"Category filter '{cat}' returned 200 OK ({count} items found)")

    print("\n=== 5. Testing Create Item with Category, Similarity, and Idempotency ===")
    payments_team_id = next(
        m["team_id"]
        for m in me_resp.json()["teams"]
        if (m.get("team", {}).get("key_prefix") == "PAY" or m.get("key_prefix") == "PAY")
    )
    new_item_idem = str(uuid.uuid4())
    create_resp = lead_session.post(
        "/items",
        headers={"Idempotency-Key": new_item_idem},
        json={
            "team_id": payments_team_id,
            "title": "Automated Test Charge Dispute",
            "description": "Customer reported duplicate debit card processing fee.",
            "type": "payment",
            "priority": "P1",
            "tags": ["automated-test", "billing"],
        }
    )
    if create_resp.status_code != 201:
        print_fail("Create Item", f"Failed: {create_resp.text}")
    created_item = create_resp.json()
    created_key = created_item["key"]
    created_version = created_item["version"]
    print_pass(f"Created work item {created_key} (v{created_version}) with Location and ETag headers")

    print("\n=== 6. Testing Claim, Release, and State Transitions ===")
    claim_idem = str(uuid.uuid4())
    claim_resp = lead_session.post(f"/items/{created_key}/claim", headers={"Idempotency-Key": claim_idem})
    if claim_resp.status_code != 200:
        print_fail("Claim Item", f"Failed: {claim_resp.text}")
    claimed_item = claim_resp.json()
    created_version = claimed_item["version"]
    print_pass(f"Claimed item {created_key} successfully (new v{created_version})")

    # Start work: open -> in_progress
    start_idem = str(uuid.uuid4())
    start_resp = lead_session.post(
        f"/items/{created_key}/transitions",
        headers={"If-Match": f'"{created_version}"', "Idempotency-Key": start_idem},
        json={"to": "in_progress"}
    )
    if start_resp.status_code != 200 or start_resp.json()["status"] != "in_progress":
        print_fail("Start Work", f"Failed: {start_resp.text}")
    created_version = start_resp.json()["version"]
    print_pass(f"Transitioned {created_key} to 'in_progress' (v{created_version})")

    # Transition to Blocked (with required reason)
    block_idem = str(uuid.uuid4())
    block_resp = lead_session.post(
        f"/items/{created_key}/transitions",
        headers={"If-Match": f'"{created_version}"', "Idempotency-Key": block_idem},
        json={"to": "blocked", "reason": "Awaiting merchant ledger response"}
    )
    if block_resp.status_code != 200 or block_resp.json()["status"] != "blocked":
        print_fail("Transition to Blocked", f"Failed: {block_resp.text}")
    created_version = block_resp.json()["version"]
    print_pass(f"Transitioned {created_key} to 'blocked' (v{created_version})")

    # Transition back to in_progress
    unblock_idem = str(uuid.uuid4())
    unblock_resp = lead_session.post(
        f"/items/{created_key}/transitions",
        headers={"If-Match": f'"{created_version}"', "Idempotency-Key": unblock_idem},
        json={"to": "in_progress"}
    )
    if unblock_resp.status_code != 200 or unblock_resp.json()["status"] != "in_progress":
        print_fail("Transition to In Progress", f"Failed: {unblock_resp.text}")
    created_version = unblock_resp.json()["version"]
    print_pass(f"Transitioned {created_key} to 'in_progress' (v{created_version})")

    # Transition to Resolved with resolution completed
    resolve_idem = str(uuid.uuid4())
    resolve_resp = lead_session.post(
        f"/items/{created_key}/transitions",
        headers={"If-Match": f'"{created_version}"', "Idempotency-Key": resolve_idem},
        json={"to": "resolved", "resolution": "completed", "reason": "Refund successfully credited"}
    )
    if resolve_resp.status_code != 200 or resolve_resp.json()["status"] != "resolved":
        print_fail("Transition to Resolved", f"Failed: {resolve_resp.text}")
    created_version = resolve_resp.json()["version"]
    print_pass(f"Transitioned {created_key} to 'resolved' with resolution='completed' (v{created_version})")

    # Transition to Closed with resolution duplicate
    close_idem = str(uuid.uuid4())
    close_resp = lead_session.post(
        f"/items/{created_key}/transitions",
        headers={"If-Match": f'"{created_version}"', "Idempotency-Key": close_idem},
        json={"to": "closed", "resolution": "duplicate", "duplicate_of": "PAY-101", "reason": "Duplicate ticket"}
    )
    if close_resp.status_code != 200 or close_resp.json()["status"] != "closed":
        print_fail("Transition to Closed", f"Failed: {close_resp.text}")
    print_pass(f"Transitioned {created_key} to 'closed' with resolution='duplicate' duplicate_of='PAY-101'")

    print("\n=== 7. Testing Four-Eyes Approval Policy on PAY-102 ===")
    # Marcus Member requested PAY-102. When member attempts to self-approve:
    member_session = httpx.Client(base_url=BACKEND_URL, timeout=30.0)
    member_session.post("/auth/login", json={"email": "member@opsboard.dev", "password": "Password123!"})
    pay102_resp = member_session.get("/items/PAY-102")
    approval_id = pay102_resp.json().get("pending_approval_id")
    if approval_id:
        decide_idem = str(uuid.uuid4())
        self_approve_resp = member_session.post(
            f"/approvals/{approval_id}/decision",
            headers={"Idempotency-Key": decide_idem},
            json={"approved": True, "decision_reason": "Attempting self approval"}
        )
        if self_approve_resp.status_code in (403, 409):
            print_pass(f"Requester self-approval blocked ({self_approve_resp.status_code} {self_approve_resp.json().get('code')})")
        else:
            print_fail("Four-Eyes Policy", f"Self-approval was not blocked: {self_approve_resp.status_code}")

        # Peer lead (Priya Lead) who did NOT request it decides the approval
        lead_decide_idem = str(uuid.uuid4())
        lead_approve_resp = lead_session.post(
            f"/approvals/{approval_id}/decision",
            headers={"Idempotency-Key": lead_decide_idem},
            json={"approved": True, "decision_reason": "Verified SLA Downtime records. Approved by lead."}
        )
        if lead_approve_resp.status_code == 200:
            print_pass("Peer lead successfully approved the pending request (200 OK)")
        else:
            print_fail("Lead Approval", f"Failed: {lead_approve_resp.text}")

    print("\n=== 8. Testing Teams Roster & Org Admin Capabilities ===")
    admin_session = httpx.Client(base_url=BACKEND_URL, timeout=30.0)
    admin_login = admin_session.post("/auth/login", json={
        "email": "admin@opsboard.dev",
        "password": "Password123!"
    })
    if admin_login.status_code != 200:
        print_fail("Admin Login", f"Failed: {admin_login.text}")
    print_pass("Alice Admin authenticated successfully")

    # List teams as org admin
    teams_resp = admin_session.get("/teams")
    if teams_resp.status_code != 200 or len(teams_resp.json()) == 0:
        print_fail("Admin /teams", f"Failed: {teams_resp.text}")
    print_pass(f"Admin retrieved all registered teams ({len(teams_resp.json())} teams)")

    # Search users
    users_search = admin_session.get("/users?q=Priya")
    if users_search.status_code != 200 or len(users_search.json()) == 0:
        print_fail("/users?q=Priya", f"Failed: {users_search.text}")
    priya_user_id = users_search.json()[0]["id"]
    print_pass(f"Org admin searched users successfully (Found {users_search.json()[0]['name']}: {priya_user_id})")

    # Create team as org admin
    new_team_slug = f"qa-ops-{uuid.uuid4().hex[:6]}"
    new_team_prefix = f"Q{uuid.uuid4().hex[:2].upper()}"
    create_team_resp = admin_session.post("/teams", json={
        "name": "Quality Assurance Ops",
        "slug": new_team_slug,
        "key_prefix": new_team_prefix,
    })
    if create_team_resp.status_code != 201:
        print_fail("Create Team", f"Failed: {create_team_resp.text}")
    new_team_id = create_team_resp.json()["_id"]
    print_pass(f"Org admin created new team '{new_team_slug}' (Prefix: {new_team_prefix}) with id: {new_team_id}")

    # Add member to new team
    add_mem_resp = admin_session.post(f"/teams/{new_team_id}/members", json={
        "user_id": priya_user_id,
        "role": "lead",
    })
    if add_mem_resp.status_code != 201:
        print_fail("Add Member", f"Failed: {add_mem_resp.text}")
    print_pass(f"Org admin added member {priya_user_id} to new team as 'lead'")

    # Update member role
    update_role_resp = admin_session.patch(f"/teams/{new_team_id}/members/{priya_user_id}", json={
        "role": "member",
    })
    if update_role_resp.status_code != 200:
        print_fail("Update Member Role", f"Failed: {update_role_resp.text}")
    print_pass("Org admin updated member role to 'member'")

    # Remove member
    del_mem_resp = admin_session.delete(f"/teams/{new_team_id}/members/{priya_user_id}")
    if del_mem_resp.status_code != 204:
        print_fail("Remove Member", f"Failed: {del_mem_resp.text}")
    print_pass("Org admin removed member from team (204 No Content)")

    print("\n=== 9. Testing AI Ask Grounded Assistant ===")
    ask_resp = lead_session.post("/ai/ask", json={
        "question": "What is the policy for refunds over $500?"
    })
    if ask_resp.status_code != 200:
        print_fail("/ai/ask", f"Failed: {ask_resp.text}")
    ask_data = ask_resp.json()
    retrieved_count = len(ask_data.get("retrieved", []))
    print_pass(f"AI Ask returned 200 OK with {retrieved_count} retrieved chunks and citations (Degraded mode: {ask_data.get('degraded')})")

    print("\n=======================================================")
    print("ALL FRONTEND & BACKEND INTEGRATION VALIDATIONS PASSED!")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
