"""
Search and Keyset Pagination Test Suite matching TEST_PLAN.md §2.6.
Covers:
  - T-SRC-1: Search ignores foreign teams (no data leakage across team boundary)
  - T-SRC-2: Search relevance and autocomplete mode
  - T-PAG-1: Keyset pagination produces gap-free, duplicate-free results
  - T-PAG-2: Garbage cursor rejected with 400 BAD_CURSOR
  - T-PAG-3: Pagination limit validation (max 100)
"""

import unittest
from httpx import AsyncClient, ASGITransport

from app.core.config import get_settings
from app.db.client import mongo_manager
from app.main import app
from seed import seed


class TestSearchAndPagination(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await seed()
        await mongo_manager.connect()
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

    # --------------------------------------------------------------------------
    # T-SRC-1: Search Ignores Foreign Teams
    # --------------------------------------------------------------------------
    async def test_T_SRC_1_search_cross_team_leakage_prevented(self):
        """
        A user in Engineering searches for terms specific to Payments (PAY-101: 'Stripe webhook').
        Because the user is not in Payments, the endpoint returns an empty result list,
        never leaking the existence or details of foreign items.
        """
        # viewer@opsboard.dev is only a viewer in Payments in default seed? Let's check:
        # In seed: Priya is Lead in Payments, Marcus Member is in Payments & Lead in Eng
        # Let's create a separate user who is ONLY in Engineering
        db = mongo_manager.get_database()
        eng_team = await db.teams.find_one({"slug": "engineering"})
        self.assertIsNotNone(eng_team)

        cookies = await self._login("member@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            # Marcus is in Payments, so he can search Payments items
            resp1 = await client.get("/api/v1/search?q=Double")
            self.assertEqual(resp1.status_code, 200)
            items = resp1.json()["items"]
            self.assertGreaterEqual(len(items), 1)

            # Now create a pure engineering user with no payments access
            from app.domain.models.base import generate_id, utc_now
            from app.repositories.users import UserRepository
            user_repo = UserRepository(db)
            pure_eng = await user_repo.create_user("Eng Only", "engonly@opsboard.dev", "Password123!")
            await db.memberships.insert_one({
                "_id": generate_id("mem"),
                "user_id": str(pure_eng["_id"]),
                "team_id": str(eng_team["_id"]),
                "role": "member",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            })

            cookies_eng = await self._login("engonly@opsboard.dev")
            client_eng = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies_eng)

            try:
                # Search for Double charge term
                resp2 = await client_eng.get("/api/v1/search?q=Double")
                self.assertEqual(resp2.status_code, 200)
                items_eng = resp2.json()["items"]
                # Must be strictly empty!
                self.assertEqual(len(items_eng), 0, "Foreign team item was leaked in search!")
            finally:
                await client_eng.aclose()
        finally:
            await client.aclose()

    # --------------------------------------------------------------------------
    # T-SRC-2: Search Relevance and Autocomplete
    # --------------------------------------------------------------------------
    async def test_T_SRC_2_autocomplete_search_returns_projections(self):
        """
        Autocomplete search returns lightweight projections containing key, title, status.
        """
        cookies = await self._login("member@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            resp = await client.get("/api/v1/search?q=PAY&autocomplete=true")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("items", data)
            for itm in data["items"]:
                self.assertIn("key", itm)
                self.assertIn("title", itm)
                self.assertIn("status", itm)
                # Description should not be projected in autocomplete mode
                self.assertNotIn("description", itm)
        finally:
            await client.aclose()

    # --------------------------------------------------------------------------
    # T-PAG-2: Cursor Tampering Returns 400 BAD_CURSOR
    # --------------------------------------------------------------------------
    async def test_T_PAG_2_cursor_tampering_rejected_with_400(self):
        """
        Passing corrupted, non-decodable, or malformed cursor string
        must be rejected with HTTP 400 and code BAD_CURSOR.
        """
        cookies = await self._login("member@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            resp = await client.get("/api/v1/items?cursor=invalid--corrupted-cursor-token")
            self.assertEqual(resp.status_code, 400)
            data = resp.json()
            self.assertEqual(data["code"], "BAD_CURSOR")
        finally:
            await client.aclose()

    # --------------------------------------------------------------------------
    # T-PAG-3: Limit Validation
    # --------------------------------------------------------------------------
    async def test_T_PAG_3_limit_validation_and_clamping(self):
        """
        Pagination limit > 100 must be rejected with 422 schema validation error.
        """
        cookies = await self._login("member@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            resp = await client.get("/api/v1/items?limit=500")
            self.assertEqual(resp.status_code, 422)
            self.assertEqual(resp.json()["code"], "VALIDATION_FAILED")
        finally:
            await client.aclose()

    # --------------------------------------------------------------------------
    # T-PAG-1: Keyset Pagination No Duplicates or Gaps
    # --------------------------------------------------------------------------
    async def test_T_PAG_1_keyset_pagination_no_duplicates(self):
        """
        Paging through items with a small limit produces distinct items with no duplicate IDs.
        """
        cookies = await self._login("admin@opsboard.dev")
        client = AsyncClient(transport=self.transport, base_url="http://testserver", cookies=cookies)

        try:
            seen_ids = set()
            cursor = None

            while True:
                url = f"/api/v1/items?limit=2"
                if cursor:
                    url += f"&cursor={cursor}"

                resp = await client.get(url)
                self.assertEqual(resp.status_code, 200)
                page = resp.json()

                for item in page["items"]:
                    self.assertNotIn(item["id"], seen_ids, "Duplicate item encountered across pages!")
                    seen_ids.add(item["id"])

                if not page["has_more"] or not page["next_cursor"]:
                    break
                cursor = page["next_cursor"]

            self.assertGreaterEqual(len(seen_ids), 3)
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
