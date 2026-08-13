import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import server


class ServerFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp.name) / "test.db"
        server.NEW_REGISTRATION_LIMIT = 20
        server.EXEMPT_EXISTING_USERS = 0
        server.RATE_BUCKETS.clear()
        server.init_db()
        server.generate_ai_plan = lambda profile, job_id: (server.fallback_plan(profile), "test/provider")
        server.send_plan_email = lambda recipient, name, plan: None
        server.coach_answer = lambda question, profile, plan: "Vælg den korte version i dag, og fortsæt roligt i morgen."
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.AppHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=2)
        cls.httpd.server_close()
        cls.temp.cleanup()

    def request(self, method, path, payload=None, cookie="", csrf=""):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        conn.request(method, path, json.dumps(payload).encode() if payload is not None else None, headers)
        response = conn.getresponse()
        body = json.loads(response.read() or b"{}")
        set_cookie = response.getheader("Set-Cookie")
        conn.close()
        return response.status, body, set_cookie

    def wait_for_plan(self, user_id, week):
        deadline = time.time() + 5
        while time.time() < deadline:
            with server.db() as conn:
                row = conn.execute("SELECT plan_json FROM plans WHERE user_id=? AND program_week=? ORDER BY id DESC LIMIT 1", (user_id, week)).fetchone()
            if row:
                return json.loads(row["plan_json"])
            time.sleep(0.05)
        self.fail("Planjobbet blev ikke færdigt")

    def test_complete_program_flow(self):
        email = f"flow-{time.time_ns()}@example.dk"
        status, registered, header = self.request("POST", "/api/auth/register", {"email": email, "name": "Test Bruger", "password": "megethemmelig12", "programDays": 90})
        self.assertEqual(status, 201)
        cookie = header.split(";", 1)[0]
        csrf = registered["csrf"]
        profile = {
            "age": 45, "height": 178, "weight": 112, "targetWeight": 100,
            "activity": "starter", "diet": "flex", "trainingPlace": "home", "pace": "gentle",
            "minutes": 25, "walk": True, "swim": True, "strength": True, "knees": False,
            "back": False, "diabetes": False, "heart": False, "pregnant": False,
            "eatingDisorder": False, "uncontrolledBloodPressure": False, "recentSurgery": False,
            "mobility": "independent", "medication": "", "painAreas": "", "allergies": "",
            "dislikes": "", "cookingMinutes": 30, "consent": True,
        }
        status, queued, _ = self.request("POST", "/api/plan/generate", {"profile": profile}, cookie, csrf)
        self.assertEqual(status, 202)
        with server.db() as conn:
            user_id = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
        first = self.wait_for_plan(user_id, 1)
        self.assertEqual(first["program"]["currentWeek"], 1)
        self.assertEqual(first["program"]["totalWeeks"], 13)
        self.assertEqual(len(first["strengthWorkouts"]), 2)

        status, swapped, _ = self.request("POST", "/api/meal/swap", {"day": 1, "kind": "dinner"}, cookie, csrf)
        self.assertEqual(status, 200)
        self.assertIn("method", swapped["meal"])

        status, coached, _ = self.request("POST", "/api/coach", {"question": "Jeg er træt i dag, hvad gør jeg?"}, cookie, csrf)
        self.assertEqual(status, 200)
        self.assertIn("korte version", coached["answer"])

        review = {"weight": 111.4, "energy": 3, "difficulty": 3, "pain": 1, "win": "Gåturene virkede", "challenge": "Aftensmad tog tid", "nextFocus": "Kortere mad"}
        status, next_job, _ = self.request("POST", "/api/program/next-week", review, cookie, csrf)
        self.assertEqual(status, 202)
        second = self.wait_for_plan(user_id, 2)
        self.assertEqual(second["program"]["currentWeek"], 2)
        with server.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM weekly_reviews WHERE user_id=?", (user_id,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
