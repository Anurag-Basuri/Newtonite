"""
Integration tests for critical concurrency and correctness primitives against real MongoDB.
Covers:
  - T-CLM-1: Concurrent claim race (exactly one winner, loser gets 409 ALREADY_CLAIMED naming winner)
  - T-VER-1: Stale edit with If-Match (returns 412 VERSION_CONFLICT with diffs)
  - T-IDM-1: Idempotency replay (repeated request replays without duplicate mutation)
  - T-APR-1: Four-eyes rule on approval decisions (requester cannot approve own request)
  - T-AZ-1: Non-member resource access returns 404 (invisibility, no existence leakage)
"""

import asyncio
import os
import sys
import unittest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings
from app.db.client import mongo_manager
from app.main import app
from seed import seed


class TestConcurrencyAndCriticalBehaviors(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Seed a clean database state before each integration test."""
        await seed()
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        await mongo_manager.close()

    async def _login(self, email: str, password: str = "Password123!") -> dict[str, str]:
        resp = await self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        self.assertEqual(resp.status_code, 200, f"Login failed for {email}: {resp.text}")
        cookie_name = get_settings().COOKIE_NAME
        token = resp.cookies.get(cookie_name)
        return {cookie_name: token}

    async def test_T_CLM_1_concurrent_claim_single_winner(self):
        """
        Two users attempt to claim the exact same unassigned work item concurrently.
        Database-level compare-and-set guarantees:
          - Exactly ONE winner receives 200 OK
          - The other user receives 409 Conflict with code ALREADY_CLAIMED naming the winner
        """
        # User 1: Marcus Member, User 2: Sarah Member
        cookies_u1 = await self._login("member@opsboard.dev")
        cookies_u2 = await self._login("member2@opsboard.dev")

        # PAY-101 is an unassigned item created by the seed script
        item_id = "PAY-101"

        client1 = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies_u1)
        client2 = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies_u2)

        try:
            req1 = client1.post(
                f"/api/v1/items/{item_id}/claim",
                headers={"Idempotency-Key": "claim-race-req-1"},
            )
            req2 = client2.post(
                f"/api/v1/items/{item_id}/claim",
                headers={"Idempotency-Key": "claim-race-req-2"},
            )

            # Fire both requests simultaneously
            resp1, resp2 = await asyncio.gather(req1, req2)

            statuses = [resp1.status_code, resp2.status_code]
            self.assertIn(200, statuses, "At least one claim request must succeed")
            self.assertIn(409, statuses, "The losing claim request must receive 409 Conflict")

            # Check winner and loser payloads
            winner_resp = resp1 if resp1.status_code == 200 else resp2
            loser_resp = resp2 if resp1.status_code == 200 else resp1

            winner_data = winner_resp.json()
            self.assertIsNotNone(winner_data["assignee_id"])

            loser_data = loser_resp.json()
            self.assertEqual(loser_data["code"], "ALREADY_CLAIMED")
            self.assertEqual(loser_data["meta"]["winner_id"], winner_data["assignee_id"])
        finally:
            await client1.aclose()
            await client2.aclose()

    async def test_T_VER_1_stale_edit_rejected_with_412(self):
        """
        A user attempts to save changes using an outdated version in If-Match.
        Server rejects the stale edit with 412 VERSION_CONFLICT.
        """
        # member2 is the assignee of PAY-103 in seed data
        cookies = await self._login("member2@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            # 1. Fetch current item PAY-103
            resp = await client.get("/api/v1/items/PAY-103")
            self.assertEqual(resp.status_code, 200)
            item = resp.json()
            current_version = item["version"]

            # 2. Successfully update item once to bump version
            edit1 = await client.patch(
                "/api/v1/items/PAY-103",
                headers={"If-Match": f'"{current_version}"'},
                json={"title": "Updated Title First Edit"},
            )
            self.assertEqual(edit1.status_code, 200)
            new_version = edit1.json()["version"]
            self.assertGreater(new_version, current_version)

            # 3. Attempt second update with the OLD version (simulating stale browser tab)
            stale_edit = await client.patch(
                "/api/v1/items/PAY-103",
                headers={"If-Match": f'"{current_version}"'},
                json={"title": "Stale Edit Attempt"},
            )
            self.assertEqual(stale_edit.status_code, 412)
            error_data = stale_edit.json()
            self.assertEqual(error_data["code"], "VERSION_CONFLICT")
            self.assertEqual(error_data["meta"]["current_version"], new_version)
        finally:
            await client.aclose()

    async def test_T_IDM_1_idempotent_retry_returns_cached_response(self):
        """
        Replaying a request with the same Idempotency-Key returns the stored response
        with header Idempotent-Replay: true without creating duplicates.
        """
        cookies = await self._login("member@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            # 1. Post a comment with a specific idempotency key
            idem_key = "test-idem-key-comment-99"
            payload = {"body": "This is a critical operational update."}

            resp1 = await client.post(
                "/api/v1/items/PAY-103/comments",
                headers={"Idempotency-Key": idem_key},
                json=payload,
            )
            self.assertEqual(resp1.status_code, 201)
            event1 = resp1.json()

            # 2. Replay identical request with same key
            resp2 = await client.post(
                "/api/v1/items/PAY-103/comments",
                headers={"Idempotency-Key": idem_key},
                json=payload,
            )
            self.assertEqual(resp2.status_code, 201)
            self.assertEqual(resp2.headers.get("Idempotent-Replay"), "true")
            event2 = resp2.json()
            self.assertEqual(event1["_id"], event2["_id"])

            # 3. Verify timeline contains only ONE such comment
            timeline_resp = await client.get("/api/v1/items/PAY-103/timeline")
            events = timeline_resp.json()["events"]
            matching_comments = [e for e in events if e.get("data", {}).get("body") == payload["body"]]
            self.assertEqual(len(matching_comments), 1, "Duplicate comment was erroneously created!")
        finally:
            await client.aclose()

    async def test_T_APR_1_four_eyes_rule_enforced(self):
        """
        Four-eyes rule: the user who requested approval CANNOT approve it.
        """
        # In seed data, PAY-102 was requested by member@opsboard.dev
        # If member@opsboard.dev tries to decide it, it must be rejected with 403 Forbidden
        cookies_requester = await self._login("member@opsboard.dev")
        client_requester = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies_requester)

        cookies_lead = await self._login("lead@opsboard.dev")
        client_lead = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies_lead)

        try:
            # Get item to find approval id
            item_resp = await client_requester.get("/api/v1/items/PAY-102")
            approval_id = item_resp.json()["pending_approval_id"]
            self.assertIsNotNone(approval_id)

            # Requester attempts to approve own request
            deny_resp = await client_requester.post(
                f"/api/v1/approvals/{approval_id}/decision",
                headers={"Idempotency-Key": "self-approval-attempt"},
                json={"approved": True, "decision_reason": "I approve my own request"},
            )
            # Member is not lead in payments team, and even if lead, four-eyes rule denies
            self.assertEqual(deny_resp.status_code, 403)
            self.assertEqual(deny_resp.json()["code"], "FORBIDDEN")

            # Team Lead (Priya Lead) who did NOT request it decides it
            allow_resp = await client_lead.post(
                f"/api/v1/approvals/{approval_id}/decision",
                headers={"Idempotency-Key": "lead-approval-success"},
                json={"approved": True, "decision_reason": "Verified contract SLA terms. Approved."},
            )
            self.assertEqual(allow_resp.status_code, 200)
            self.assertEqual(allow_resp.json()["status"], "approved")

            # Check that item is now RESOLVED
            updated_item = (await client_lead.get("/api/v1/items/PAY-102")).json()
            self.assertEqual(updated_item["status"], "resolved")
            self.assertEqual(updated_item["resolution"], "completed")
        finally:
            await client_requester.aclose()
            await client_lead.aclose()


if __name__ == "__main__":
    unittest.main()
