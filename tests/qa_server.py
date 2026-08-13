"""Local-only QA server with deterministic data and no external calls."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from program_content import apply_program_structure, ensure_meal_safety, total_weeks


server.PORT = int(os.getenv("QA_PORT", "8964"))
server.ALLOWED_ORIGINS.add(f"http://127.0.0.1:{server.PORT}")
server.DB_PATH = Path(os.getenv("QA_DB_PATH", str(server.ROOT / ".tmp-visual" / "qa.db")))
server.send_plan_email = lambda recipient, name, plan: None
server.generate_ai_plan = lambda profile, job_id: (server.fallback_plan(profile), "qa/provider")
server.coach_answer = lambda question, profile, plan: "Vælg den korte version i dag. Det holder rytmen levende, og du kan fortsætte roligt i morgen."

profile = {
    "age": 45, "height": 178, "weight": 112, "targetWeight": 100,
    "activity": "starter", "diet": "flex", "trainingPlace": "home", "pace": "gentle",
    "minutes": 25, "walk": True, "swim": True, "strength": True, "knees": False,
    "back": False, "diabetes": False, "heart": False, "pregnant": False,
    "eatingDisorder": False, "uncontrolledBloodPressure": False, "recentSurgery": False,
    "mobility": "independent", "medication": "", "painAreas": "", "allergies": "",
    "dislikes": "", "cookingMinutes": 30, "consent": True,
}

server.init_db()
plan = apply_program_structure(ensure_meal_safety(server.fallback_plan(profile), profile), profile, 1, total_weeks(90))
with server.db() as conn:
    row = conn.execute("SELECT id FROM users WHERE email='qa@friform.local'").fetchone()
    user_id = row["id"] if row else conn.execute(
        "INSERT INTO users(email,name,password_hash,created_at,program_days,program_started_at,program_ends_at) VALUES(?,?,?,?,?,?,?)",
        ("qa@friform.local", "QA Bruger", server.password_hash("professioneltest12"), server.iso_now(), 90, server.iso_now(), (server.utc_now() + server.timedelta(days=90)).isoformat()),
    ).lastrowid
    conn.execute("INSERT INTO profiles(user_id,data_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at", (user_id, json.dumps(profile, ensure_ascii=False), server.iso_now()))
    if not conn.execute("SELECT 1 FROM plans WHERE user_id=?", (user_id,)).fetchone():
        conn.execute("INSERT INTO plans(user_id,plan_json,provider,created_at,program_week) VALUES(?,?,?,?,1)", (user_id, json.dumps(plan, ensure_ascii=False), "qa/provider", server.iso_now()))

if __name__ == "__main__":
    server.ThreadingHTTPServer(("127.0.0.1", server.PORT), server.AppHandler).serve_forever()
