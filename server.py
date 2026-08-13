#!/usr/bin/env python3
"""Fri Form: small dependency-free API and static server."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from program_content import (
    VIDEO_CREDITS,
    apply_program_structure,
    ensure_meal_safety,
    meal_options,
    safe_meal,
    total_weeks,
)


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")

PORT = int(os.getenv("PORT", "8963"))
DB_PATH = Path(os.getenv("FRIFORM_DB_PATH", str(ROOT / "data" / "friform.db")))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "reinodybbol@gmail.com").strip().lower()
EXEMPT_EXISTING_USERS = int(os.getenv("EXEMPT_EXISTING_USERS", "2"))
NEW_REGISTRATION_LIMIT = int(os.getenv("NEW_REGISTRATION_LIMIT", "20"))
SESSION_DAYS = 30
COOKIE_NAME = "friform_session"
ALLOWED_ORIGINS = {
    "https://fit.dybbol.com",
    "http://localhost:8963",
    "http://127.0.0.1:8963",
}
RATE_LOCK = threading.Lock()
RATE_BUCKETS: dict[str, list[float]] = {}


class RegistrationFullError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY,
              email TEXT NOT NULL COLLATE NOCASE UNIQUE,
              name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              last_login_at TEXT,
              program_days INTEGER,
              program_started_at TEXT,
              program_ends_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              csrf_token TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
              user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              data_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              plan_json TEXT NOT NULL,
              provider TEXT NOT NULL,
              created_at TEXT NOT NULL,
              emailed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS weekly_reviews (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              program_week INTEGER NOT NULL,
              weight REAL,
              energy INTEGER NOT NULL,
              difficulty INTEGER NOT NULL,
              pain INTEGER NOT NULL DEFAULT 0,
              win_text TEXT NOT NULL,
              challenge_text TEXT NOT NULL,
              next_focus TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(user_id, program_week)
            );
            CREATE TABLE IF NOT EXISTS coach_messages (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role TEXT NOT NULL CHECK(role IN ('user','assistant')),
              content TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkins (
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              day TEXT NOT NULL,
              item_id TEXT NOT NULL,
              completed INTEGER NOT NULL DEFAULT 0,
              weight REAL,
              mood INTEGER,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (user_id, day, item_id)
            );
            CREATE TABLE IF NOT EXISTS plan_jobs (
              id TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              status TEXT NOT NULL,
              error TEXT,
              plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
              provider TEXT,
              email_sent INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              expires_at TEXT NOT NULL,
              used_at TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_usage_events (
              id INTEGER PRIMARY KEY,
              job_id TEXT REFERENCES plan_jobs(id) ON DELETE CASCADE,
              provider TEXT NOT NULL,
              model TEXT NOT NULL,
              phase TEXT NOT NULL,
              status TEXT NOT NULL,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              cache_read_tokens INTEGER NOT NULL DEFAULT 0,
              cache_write_tokens INTEGER NOT NULL DEFAULT 0,
              estimated_cost_usd REAL NOT NULL DEFAULT 0,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              error_type TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_plans_user_created ON plans(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_checkins_user_day ON checkins(user_id, day);
            CREATE INDEX IF NOT EXISTS idx_plan_jobs_user_created ON plan_jobs(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_usage_started ON ai_usage_events(started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_usage_job ON ai_usage_events(job_id, id);
            CREATE INDEX IF NOT EXISTS idx_reviews_user_week ON weekly_reviews(user_id, program_week DESC);
            CREATE INDEX IF NOT EXISTS idx_coach_user_created ON coach_messages(user_id, id DESC);
            PRAGMA optimize;
            """
        )
        conn.execute("UPDATE plan_jobs SET status='failed',error='Serveren blev genstartet. Lav planen igen.',updated_at=? WHERE status IN ('pending','running')", (iso_now(),))
        conn.execute("DELETE FROM password_reset_tokens WHERE expires_at<?", (iso_now(),))
        conn.execute("UPDATE ai_usage_events SET status='interrupted',finished_at=? WHERE status='running'", (iso_now(),))
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "program_days" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN program_days INTEGER")
        if "program_started_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN program_started_at TEXT")
        if "program_ends_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN program_ends_at TEXT")
        plan_columns = {row["name"] for row in conn.execute("PRAGMA table_info(plans)")}
        if "program_week" not in plan_columns:
            conn.execute("ALTER TABLE plans ADD COLUMN program_week INTEGER NOT NULL DEFAULT 1")
        job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(plan_jobs)")}
        if "program_week" not in job_columns:
            conn.execute("ALTER TABLE plan_jobs ADD COLUMN program_week INTEGER NOT NULL DEFAULT 1")


def b64hex(data: bytes) -> str:
    return data.hex()


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${b64hex(salt)}${b64hex(derived)}"


def password_ok(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        derived = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(derived, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def clean_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Indtast en gyldig e-mailadresse.")
    return email


def clean_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if not 2 <= len(name) <= 60:
        raise ValueError("Navnet skal være mellem 2 og 60 tegn.")
    return name


def validate_password(value: Any) -> str:
    password = str(value or "")
    if len(password) < 10 or len(password) > 200:
        raise ValueError("Adgangskoden skal være mindst 10 tegn.")
    return password


def validate_program_days(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise ValueError("Vælg hvor længe dit gratis forløb skal vare.")
    if days not in {7, 30, 90, 180}:
        raise ValueError("Vælg 1 uge, 1, 3 eller 6 måneder.")
    return days


def user_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "email": row["email"],
        "name": row["name"],
        "isAdmin": row["email"].lower() == ADMIN_EMAIL,
        "programDays": row["program_days"],
        "programStartedAt": row["program_started_at"],
        "programEndsAt": row["program_ends_at"],
    }


def rate_allowed(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with RATE_LOCK:
        recent = [stamp for stamp in RATE_BUCKETS.get(key, []) if stamp > now - window_seconds]
        if len(recent) >= limit:
            RATE_BUCKETS[key] = recent
            return False
        recent.append(now)
        RATE_BUCKETS[key] = recent
        return True


def make_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    csrf = secrets.token_urlsafe(24)
    expires = (utc_now() + timedelta(days=SESSION_DAYS)).isoformat()
    conn.execute(
        "INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at,created_at) VALUES(?,?,?,?,?)",
        (token_hash, user_id, csrf, expires, iso_now()),
    )
    return raw, csrf


def latest_plan(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id,plan_json,provider,created_at,emailed_at,program_week FROM plans WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "plan": json.loads(row["plan_json"]),
        "provider": row["provider"],
        "created_at": row["created_at"],
        "emailed_at": row["emailed_at"],
        "program_week": row["program_week"],
    }


def bounded_number(data: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    try:
        value = float(data.get(key))
    except (TypeError, ValueError):
        raise ValueError(f"Feltet {key} mangler eller er ugyldigt.")
    if not minimum <= value <= maximum:
        raise ValueError(f"Feltet {key} ligger uden for det tilladte interval.")
    return value


def validate_profile(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Profilen mangler.")
    age = int(bounded_number(raw, "age", 18, 80))
    weight = round(bounded_number(raw, "weight", 40, 300), 1)
    height = int(bounded_number(raw, "height", 130, 220))
    target = round(bounded_number(raw, "targetWeight", 40, 280), 1)
    if target >= weight:
        raise ValueError("Målvægten skal være lavere end startvægten.")
    allowed = {
        "activity": {"starter", "light", "regular"},
        "diet": {"flex", "vegetarian", "pescetarian"},
        "trainingPlace": {"home", "gym", "mix"},
        "pace": {"gentle", "steady"},
    }
    result: dict[str, Any] = {
        "age": age,
        "weight": weight,
        "height": height,
        "targetWeight": target,
        "activity": str(raw.get("activity", "starter")),
        "diet": str(raw.get("diet", "flex")),
        "trainingPlace": str(raw.get("trainingPlace", "home")),
        "pace": str(raw.get("pace", "gentle")),
        "minutes": int(bounded_number(raw, "minutes", 10, 90)),
        "walk": bool(raw.get("walk", True)),
        "swim": bool(raw.get("swim", False)),
        "strength": bool(raw.get("strength", True)),
        "knees": bool(raw.get("knees", False)),
        "back": bool(raw.get("back", False)),
        "diabetes": bool(raw.get("diabetes", False)),
        "heart": bool(raw.get("heart", False)),
        "pregnant": bool(raw.get("pregnant", False)),
        "eatingDisorder": bool(raw.get("eatingDisorder", False)),
        "uncontrolledBloodPressure": bool(raw.get("uncontrolledBloodPressure", False)),
        "recentSurgery": bool(raw.get("recentSurgery", False)),
        "mobility": str(raw.get("mobility", "independent")),
        "medication": re.sub(r"\s+", " ", str(raw.get("medication", "")))[:200],
        "painAreas": re.sub(r"\s+", " ", str(raw.get("painAreas", "")))[:200],
        "allergies": re.sub(r"\s+", " ", str(raw.get("allergies", "")))[:200],
        "dislikes": re.sub(r"\s+", " ", str(raw.get("dislikes", "")))[:200],
        "cookingMinutes": int(bounded_number(raw, "cookingMinutes", 10, 90)),
        "consent": bool(raw.get("consent", False)),
    }
    for key, values in allowed.items():
        if result[key] not in values:
            raise ValueError(f"Ugyldigt valg i {key}.")
    if result["mobility"] not in {"independent", "support", "limited"}:
        raise ValueError("Ugyldigt valg i mobility.")
    if not (result["walk"] or result["swim"] or result["strength"]):
        raise ValueError("Vælg mindst én motionsform.")
    if not result["consent"]:
        raise ValueError("Du skal acceptere databehandlingen for at få en AI-plan.")
    return result


def safety_block(profile: dict[str, Any]) -> str | None:
    if profile["pregnant"]:
        return "Vægttab under graviditet bør planlægges sammen med jordemoder eller læge."
    if profile["eatingDisorder"]:
        return "Ved nuværende eller tidligere spiseforstyrrelse bør en individuel plan laves sammen med en fagperson."
    if profile["heart"]:
        return "Ved hjertesygdom skal træningsintensitet afklares med egen læge, før planen startes."
    if profile.get("uncontrolledBloodPressure"):
        return "Ved uafklaret eller meget højt blodtryk skal træning og vægttab først afklares med egen læge."
    if profile.get("recentSurgery"):
        return "Efter en nylig operation skal aktivitet først afklares med den afdeling eller fagperson, der følger dig."
    return None


def plan_prompt(profile: dict[str, Any]) -> str:
    safe = {key: value for key, value in profile.items() if key != "consent" and not key.startswith("_")}
    week = int(profile.get("_program_week", 1))
    return f"""
Lav en realistisk, detaljeret uge {week}-plan på dansk til en voksen.
Profilen er pseudonymiseret og indeholder ingen navn eller e-mail:
{json.dumps(safe, ensure_ascii=False)}

Planen er generel livsstilsvejledning, ikke behandling. Ingen ekstreme kure,
faste, kosttilskud eller løfter om bestemt vægttab. Brug almindelige danske
råvarer, tallerkenmodellen og gradvis aktivitet. Tag hensyn til knæ/ryg,
allergier og valgte motionsformer. Svømning må kun indgå, hvis swim=true.

Returnér KUN gyldig JSON med præcis denne form:
{{
  "title":"...", "intro":"...", "weeklyFocus":"...",
  "safetyNote":"...", "waterTip":"...", "sleepTip":"...",
  "days":[{{
    "day":1, "name":"Mandag", "focus":"...",
    "meals":{{
      "breakfast":{{"title":"...","ingredients":["..."],"portion":"...","method":["..."],"prepMinutes":10}},
      "lunch":{{"title":"...","ingredients":["..."],"portion":"...","method":["..."],"prepMinutes":10}},
      "dinner":{{"title":"...","ingredients":["..."],"portion":"...","method":["..."],"prepMinutes":30}},
      "snack":{{"title":"...","ingredients":["..."],"portion":"...","method":["..."],"prepMinutes":5}}
    }},
    "movement":{{"type":"gåtur|svømning|styrke|restitution","title":"...","minutes":20,"intensity":"...","instructions":["..."],"alternative":"..."}},
    "habit":"...", "encouragement":"..."
  }}],
  "strengthGuide":[{{"exercise":"...","sets":"...","reps":"...","how":"...","easier":"..."}}],
  "swimGuide":[{{"part":"...","minutes":5,"how":"..."}}],
  "shoppingList":{{"grønt":["..."],"protein":["..."],"fuldkornOgKartofler":["..."],"andet":["..."]}},
  "checkInQuestions":["..."],
  "medicalReminder":"..."
}}
Der skal være præcis 7 forskellige dage. Instruktioner skal være konkrete og venlige.
""".strip()


def parse_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI-svaret indeholdt ikke JSON.")
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI-svaret var ikke et JSON-objekt.")
    return parsed


def extract_json(text: str, profile: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_json_object(text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("days"), list) or len(parsed["days"]) != 7:
        raise ValueError("AI-planen havde ikke syv dage.")
    for index, day in enumerate(parsed["days"], start=1):
        if not isinstance(day, dict) or not isinstance(day.get("meals"), dict) or not isinstance(day.get("movement"), dict):
            raise ValueError(f"Dag {index} var ufuldstændig.")
    defaults = fallback_plan(profile)
    for key in ("title", "intro", "weeklyFocus", "safetyNote", "waterTip", "sleepTip", "strengthGuide", "swimGuide", "shoppingList", "checkInQuestions", "medicalReminder"):
        if key not in parsed or parsed[key] in (None, "", [], {}):
            parsed[key] = defaults[key]
    if not isinstance(parsed["strengthGuide"], list) or not isinstance(parsed["swimGuide"], list):
        raise ValueError("AI-planens træningsguide var ugyldig.")
    if profile["swim"] and not parsed["swimGuide"]:
        parsed["swimGuide"] = defaults["swimGuide"]
    if not isinstance(parsed["shoppingList"], dict) or not parsed["shoppingList"]:
        parsed["shoppingList"] = defaults["shoppingList"]
    movement_text = lambda day: f"{day.get('movement', {}).get('type', '')} {day.get('movement', {}).get('title', '')}".lower()
    if profile["walk"] and not any("gå" in movement_text(day) for day in parsed["days"]):
        parsed["days"][0]["movement"] = defaults["days"][0]["movement"]
    if profile["strength"] and not any("styrk" in movement_text(day) for day in parsed["days"]):
        parsed["days"][1]["movement"] = defaults["days"][1]["movement"]
    if profile["swim"] and not any("svøm" in movement_text(day) for day in parsed["days"]):
        parsed["days"][2]["movement"] = defaults["days"][2]["movement"]
    parsed["title"] = str(parsed.get("title", "Din Fri Form-plan"))[:120]
    return parsed


def call_json_api(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "FriForm/2.0 (+https://fit.dybbol.com)", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def qwen36_cost(usage: dict[str, Any]) -> float:
    return round(
        int(usage.get("input_tokens", 0)) * 0.50 / 1_000_000
        + int(usage.get("output_tokens", 0)) * 3.00 / 1_000_000
        + int(usage.get("cache_read_input_tokens", 0)) * 0.05 / 1_000_000
        + int(usage.get("cache_creation_input_tokens", 0)) * 0.625 / 1_000_000,
        8,
    )


def opencode_text(
    key: str,
    prompt: str,
    max_tokens: int = 2000,
    job_id: str = "",
    phase: str = "OpenCode-kald",
    system_message: str = "Du er en forsigtig dansk sundhedsplanlægger. Returnér kun gyldig JSON uden markdown.",
) -> str:
    with db() as conn:
        event_id = conn.execute(
            "INSERT INTO ai_usage_events(job_id,provider,model,phase,status,started_at) VALUES(?,?,?,?,?,?)",
            (job_id or None, "opencode-go", "qwen3.6-plus", phase, "running", iso_now()),
        ).lastrowid
    try:
        response = call_json_api(
            "https://opencode.ai/zen/go/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": "qwen3.6-plus",
                "system": system_message,
                "messages": [{"role": "user", "content": prompt}],
                "thinking": {"type": "disabled"},
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            120,
        )
        usage = response.get("usage", {})
        with db() as conn:
            conn.execute(
                """UPDATE ai_usage_events SET status='completed',input_tokens=?,output_tokens=?,
                   cache_read_tokens=?,cache_write_tokens=?,estimated_cost_usd=?,finished_at=? WHERE id=?""",
                (
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    int(usage.get("cache_read_input_tokens", 0)),
                    int(usage.get("cache_creation_input_tokens", 0)),
                    qwen36_cost(usage),
                    iso_now(),
                    event_id,
                ),
            )
    except Exception as exc:
        with db() as conn:
            conn.execute(
                "UPDATE ai_usage_events SET status='failed',error_type=?,finished_at=? WHERE id=?",
                (type(exc).__name__[:80], iso_now(), event_id),
            )
        raise
    blocks = [block.get("text", "") for block in response.get("content", []) if block.get("type") == "text"]
    if not blocks:
        raise ValueError("OpenCode returnerede ingen tekst.")
    return "\n".join(blocks)


def generate_opencode_plan(key: str, profile: dict[str, Any], job_id: str) -> dict[str, Any]:
    week = int(profile.get("_program_week", 1))
    review = str(profile.get("_weekly_review", "")).strip()
    safe_profile = json.dumps({k: v for k, v in profile.items() if k != "consent" and not k.startswith("_")}, ensure_ascii=False)
    review_context = f" Seneste ugecheck: {review}. Tilpas forsigtigt efter den." if review else ""
    common = f"Profil (uden navn og e-mail): {safe_profile}. Dette er uge {week} i et gradvist forløb.{review_context} Brug almindelige danske råvarer, tallerkenmodellen, gradvis aktivitet og alle valgte hensyn. Ingen faste, ekstreme kure, kosttilskud eller løfter."
    day_shape = """Hver dag skal have: day (tal), name, focus, meals med breakfast/lunch/dinner/snack; hvert måltid har title, ingredients (liste), portion, method (2-4 korte trin) og prepMinutes. movement har type, title, minutes, intensity, instructions (liste) og alternative. Desuden habit og encouragement."""
    prompts = {
        "overview": f"""{common}\nLav planens overblik som JSON med nøglerne title, intro, weeklyFocus, safetyNote, waterTip, sleepTip, strengthGuide, swimGuide, shoppingList, checkInQuestions og medicalReminder. strengthGuide er en liste med exercise, sets, reps, how og easier. swimGuide er en liste med part, minutes og how, når svømning er valgt. shoppingList har grupperne grønt, protein, fuldkornOgKartofler og andet.""",
        "days_12": f"""{common}\nLav dag 1-2 (Mandag-Tirsdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "days_34": f"""{common}\nLav dag 3-4 (Onsdag-Torsdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "days_56": f"""{common}\nLav dag 5-6 (Fredag-Lørdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "day_7": f"""{common}\nLav dag 7 (Søndag) som JSON {{\"days\":[...]}}. {day_shape} Gør dagen restituerende med mulighed for let aktivitet.""",
    }
    phase_names = {
        "overview": "Overblik og indkøbsliste",
        "days_12": "Mandag og tirsdag",
        "days_34": "Onsdag og torsdag",
        "days_56": "Fredag og lørdag",
        "day_7": "Søndag og kvalitetstjek",
    }
    parts = {
        name: parse_json_object(opencode_text(key, prompt, job_id=job_id, phase=phase_names[name]))
        for name, prompt in prompts.items()
    }
    days = []
    for name in ("days_12", "days_34", "days_56", "day_7"):
        days.extend(parts[name].get("days", []))
    if len(days) != 7:
        raise ValueError("OpenCode returnerede ikke syv dage.")
    overview = parts["overview"]
    overview["days"] = days
    return extract_json(json.dumps(overview, ensure_ascii=False), profile)


def generate_ai_plan(profile: dict[str, Any], job_id: str) -> tuple[dict[str, Any], str]:
    prompt = plan_prompt(profile)
    key = os.getenv("OPENCODE_GO_API_KEY", "").strip()
    if key:
        try:
            return generate_opencode_plan(key, profile, job_id), "opencode-go/qwen3.6-plus"
        except (KeyError, ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            status = getattr(exc, "code", "")
            print(f"OpenCode generation failed: {type(exc).__name__} {status}", file=sys.stderr, flush=True)

    try:
        response = call_json_api(
            os.getenv("OLLAMA_URL", "http://192.168.1.30:11434").rstrip("/") + "/api/generate",
            {},
            {"model": "gemma3:4b", "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0.2, "num_predict": 5000}},
            260,
        )
        return extract_json(response["response"], profile), "ollama/gemma3:4b"
    except (KeyError, ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Ollama generation failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        return fallback_plan(profile), "validated-template"


def fallback_plan(profile: dict[str, Any]) -> dict[str, Any]:
    minutes = profile["minutes"]
    prefers_swim = profile["swim"]
    movements = [
        ("gåtur", "Rolig gåtur", minutes, ["Gå i et tempo hvor du kan tale i hele sætninger.", "Vend om før du bliver udmattet."]),
        ("styrke", "Styrke hjemme", min(minutes, 30), ["Lav 2 rolige runder.", "Hold 60-90 sekunders pause mellem øvelserne."]),
        ("svømning" if prefers_swim else "gåtur", "Rolig svømning" if prefers_swim else "Kort gåtur", minutes, ["Skift mellem roligt arbejde og korte pauser."]),
        ("restitution", "Let bevægelse", max(10, minutes // 2), ["Vælg en helt rolig tur eller bevægelighed."]),
        ("styrke", "Styrke og balance", min(minutes, 30), ["Lav 2 rolige runder og stop ved smerte."]),
        ("gåtur", "Ugens længere gåtur", min(60, minutes + 15), ["Hold snakketempo og tag en pause efter behov."]),
        ("restitution", "Fri eller rolig svømning", 15, ["Målet er at føle dig bedre bagefter end før."]),
    ]
    names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
    dinners = ["Kylling, kartofler og grønt", "Linsegryde med fuldkornsris", "Fisk, rugbrød og råkost", "Grøntsagssuppe med bønner", "Fuldkornspasta med kødsovs og grønt", "Ovnret med rodfrugter og protein", "Rester efter tallerkenmodellen"]
    days = []
    for index, name in enumerate(names):
        kind, title, duration, instructions = movements[index]
        days.append({
            "day": index + 1,
            "name": name,
            "focus": "En mulig dag frem for en perfekt dag",
            "meals": {
                "breakfast": {"title": "Havregrød med skyr og bær", "ingredients": ["havregryn", "skyr", "bær"], "portion": "1 skål; stop når du er behageligt mæt"},
                "lunch": {"title": "Rugbrød med æg eller bønnepostej", "ingredients": ["2 skiver rugbrød", "protein", "grøntsager"], "portion": "2 åbne madder og grønt ved siden af"},
                "dinner": {"title": dinners[index], "ingredients": ["½ tallerken grønt", "¼ protein", "¼ kartofler eller fuldkorn"], "portion": "Brug tallerkenmodellen"},
                "snack": {"title": "Frugt, skyr eller en lille håndfuld nødder", "portion": "Kun hvis du er fysisk sulten"},
            },
            "movement": {"type": kind, "title": title, "minutes": duration, "intensity": "roligt snakketempo", "instructions": instructions, "alternative": "Del tiden i to korte pas"},
            "habit": "Drik et glas vand til dit største måltid.",
            "encouragement": "Det tæller også, når du gør mindre end planlagt.",
        })
    return {
        "title": "Din første rolige uge",
        "intro": "Planen bygger på almindelig mad, gentagelser og en rolig start.",
        "weeklyFocus": "Gennemfør det mulige og justér ned på trætte dage.",
        "safetyNote": "Stop ved smerter, svimmelhed, åndenød ud over det forventelige eller andet ubehag.",
        "waterTip": "Hav vand synligt og drik til måltiderne.",
        "sleepTip": "Forsøg at stå op og gå i seng på omtrent samme tidspunkt.",
        "days": days,
        "strengthGuide": [
            {"exercise": "Rejs-sæt-dig fra stol", "sets": "2", "reps": "6-10", "how": "Skub gennem fødderne og brug en høj stol.", "easier": "Brug armlæn."},
            {"exercise": "Væg-armbøjning", "sets": "2", "reps": "6-10", "how": "Hold kroppen lang og bevæg dig roligt mod væggen.", "easier": "Stå tættere på væggen."},
            {"exercise": "March på stedet", "sets": "2", "reps": "30 sek.", "how": "Hold ved en stol og løft fødderne skiftevis.", "easier": "Gør bevægelsen mindre."},
        ],
        "swimGuide": ([
            {"part": "Opvarmning", "minutes": 5, "how": "Rolige baner eller gang i vand."},
            {"part": "Hoveddel", "minutes": max(10, minutes - 10), "how": "2 rolige baner, kort pause, gentag."},
            {"part": "Nedkøling", "minutes": 5, "how": "Meget roligt tempo."},
        ] if prefers_swim else []),
        "shoppingList": {
            "grønt": ["frosne grøntsager", "gulerødder", "tomater", "kål", "frugt"],
            "protein": ["æg", "skyr", "kylling", "fisk", "bønner og linser"],
            "fuldkornOgKartofler": ["havregryn", "rugbrød", "kartofler", "fuldkornsris"],
            "andet": ["nødder", "rapsolie", "krydderier"],
        },
        "checkInQuestions": ["Hvad var lettest at gentage?", "Hvornår havde du mest energi?", "Hvad skal gøres lidt nemmere næste uge?"],
        "medicalReminder": "Planen er generel vejledning. Tal med læge eller anden fagperson ved sygdom, medicinændringer eller vedvarende smerter.",
    }


def send_email_message(message: EmailMessage) -> None:
    user = os.getenv("GMAIL_SMTP_USER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not password:
        raise RuntimeError("Gmail SMTP er ikke konfigureret.")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)


def send_password_reset_email(recipient: str, name: str, raw_token: str) -> None:
    user = os.getenv("GMAIL_SMTP_USER", "").strip()
    reset_url = f"https://fit.dybbol.com/reset-password?token={raw_token}"
    message = EmailMessage()
    message["Subject"] = "Nulstil din adgangskode til Fri Form"
    message["From"] = f"Fri Form <{user}>"
    message["To"] = recipient
    message.set_content(
        f"Hej {name}\n\nBrug dette engangslink til at vælge en ny adgangskode:\n{reset_url}\n\n"
        "Linket udløber efter 60 minutter. Hvis du ikke bad om det, kan du bare ignorere mailen."
    )
    message.add_alternative(
        f"""
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#24342e;line-height:1.6">
          <div style="background:#173f31;color:white;padding:26px;border-radius:18px 18px 0 0">
            <small style="letter-spacing:2px">FRI FORM · ALTID GRATIS</small>
            <h1 style="margin:8px 0 0">Vælg en ny adgangskode</h1>
          </div>
          <div style="padding:28px;background:#fbfaf4">
            <p>Hej {html.escape(name)},</p>
            <p>Du har bedt om at få nulstillet adgangskoden til Fri Form.</p>
            <p><a href="{html.escape(reset_url)}" style="display:inline-block;background:#e56f3d;color:white;padding:13px 20px;border-radius:999px;text-decoration:none;font-weight:bold">Vælg ny adgangskode</a></p>
            <p style="color:#64756f;font-size:14px">Linket kan kun bruges én gang og udløber efter 60 minutter. Hvis du ikke bad om det, skal du ikke gøre noget.</p>
          </div>
        </div>""",
        subtype="html",
    )
    send_email_message(message)


def send_password_reset_email_safely(recipient: str, name: str, raw_token: str) -> None:
    try:
        send_password_reset_email(recipient, name, raw_token)
    except Exception as exc:
        print(f"Password reset email failed: {type(exc).__name__}", file=sys.stderr, flush=True)


def send_plan_email(recipient: str, name: str, plan: dict[str, Any]) -> None:
    user = os.getenv("GMAIL_SMTP_USER", "").strip()
    program = plan.get("program", {})
    week = int(program.get("currentWeek", 1))
    total = int(program.get("totalWeeks", 1))
    message = EmailMessage()
    message["Subject"] = f"Din Fri Form-plan for uge {week} er klar"
    message["From"] = f"Fri Form <{user}>"
    message["To"] = recipient
    text_days = []
    html_days = []
    for day in plan["days"]:
        meals = day["meals"]
        move = day["movement"]
        text_days.append(
            f"{day['name']}: {meals['breakfast']['title']} / {meals['lunch']['title']} / {meals['dinner']['title']}. "
            f"Aktivitet: {move['title']} ({move['minutes']} min)."
        )
        html_days.append(
            "<section style='padding:18px 0;border-top:1px solid #dce8df'>"
            f"<h2 style='margin:0 0 8px;color:#173f31'>{html.escape(str(day['name']))}</h2>"
            f"<p><b>Morgen:</b> {html.escape(str(meals['breakfast']['title']))}<br>"
            f"<b>Frokost:</b> {html.escape(str(meals['lunch']['title']))}<br>"
            f"<b>Aften:</b> {html.escape(str(meals['dinner']['title']))}</p>"
            f"<p><b>Bevægelse:</b> {html.escape(str(move['title']))} · {int(move['minutes'])} min.<br>"
            f"{html.escape(' '.join(map(str, move.get('instructions', []))))}</p></section>"
        )
    plain = f"Hej {name}\n\n{plan['intro']}\n\n" + "\n".join(text_days) + f"\n\n{plan['medicalReminder']}\n\nSe og følg planen på https://fit.dybbol.com/"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#24342e;line-height:1.55">
      <div style="background:#173f31;color:white;padding:26px;border-radius:18px 18px 0 0">
        <small style="letter-spacing:2px">FRI FORM · ALTID GRATIS</small>
        <h1 style="margin:8px 0 0">Din personlige uge {week} af {total}</h1>
      </div>
      <div style="padding:26px;background:#fbfaf4">
        <p>Hej {html.escape(name)},</p><p><b>{html.escape(str(program.get('phase', 'Din næste uge')))}</b></p><p>{html.escape(str(plan['intro']))}</p>
        {''.join(html_days)}
        <p style="padding:16px;background:#edf5ef;border-radius:12px"><b>Vigtigt:</b> {html.escape(str(plan['medicalReminder']))}</p>
        <p><a href="https://fit.dybbol.com/" style="display:inline-block;background:#e56f3d;color:white;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:bold">Log ind og se min plan</a></p>
      </div>
    </div>"""
    message.set_content(plain)
    message.add_alternative(html_body, subtype="html")
    send_email_message(message)


def run_plan_job(
    job_id: str,
    user_id: int,
    recipient: str,
    name: str,
    profile: dict[str, Any],
    program_week: int,
    program_weeks: int,
    weekly_review: str = "",
) -> None:
    try:
        with db() as conn:
            conn.execute("UPDATE plan_jobs SET status='running',updated_at=? WHERE id=?", (iso_now(), job_id))
        generation_profile = dict(profile)
        generation_profile["_program_week"] = program_week
        if weekly_review:
            generation_profile["_weekly_review"] = weekly_review
        plan, provider = generate_ai_plan(generation_profile, job_id)
        plan = ensure_meal_safety(plan, profile)
        plan = apply_program_structure(plan, profile, program_week, program_weeks)
        email_sent = False
        try:
            send_plan_email(recipient, name, plan)
            email_sent = True
        except Exception as exc:
            print(f"Email send failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        with db() as conn:
            stored_profile = {key: value for key, value in profile.items() if not key.startswith("_")}
            conn.execute("INSERT INTO profiles(user_id,data_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at", (user_id, json.dumps(stored_profile, ensure_ascii=False), iso_now()))
            cursor = conn.execute("INSERT INTO plans(user_id,plan_json,provider,created_at,emailed_at,program_week) VALUES(?,?,?,?,?,?)", (user_id, json.dumps(plan, ensure_ascii=False), provider, iso_now(), iso_now() if email_sent else None, program_week))
            conn.execute("UPDATE plan_jobs SET status='done',plan_id=?,provider=?,email_sent=?,updated_at=? WHERE id=?", (cursor.lastrowid, provider, int(email_sent), iso_now(), job_id))
    except Exception as exc:
        print(f"Plan job failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        with db() as conn:
            conn.execute("UPDATE plan_jobs SET status='failed',error=?,updated_at=? WHERE id=?", ("Planen kunne ikke laves. Prøv igen om lidt.", iso_now(), job_id))


def ai_usage_window(conn: sqlite3.Connection, seconds: int, limit_usd: float) -> dict[str, Any]:
    cutoff = (utc_now() - timedelta(seconds=seconds)).isoformat()
    row = conn.execute(
        """SELECT COUNT(*) AS calls,COALESCE(SUM(input_tokens),0) AS input_tokens,
           COALESCE(SUM(output_tokens),0) AS output_tokens,
           COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
           COALESCE(SUM(cache_write_tokens),0) AS cache_write_tokens,
           COALESCE(SUM(estimated_cost_usd),0) AS cost_usd,MIN(started_at) AS oldest
           FROM ai_usage_events WHERE status='completed' AND started_at>=?""",
        (cutoff,),
    ).fetchone()
    release_at = None
    if row["oldest"]:
        release_at = (datetime.fromisoformat(row["oldest"]) + timedelta(seconds=seconds)).isoformat()
    cost = round(float(row["cost_usd"]), 6)
    return {
        "calls": int(row["calls"]),
        "inputTokens": int(row["input_tokens"]),
        "outputTokens": int(row["output_tokens"]),
        "cacheReadTokens": int(row["cache_read_tokens"]),
        "cacheWriteTokens": int(row["cache_write_tokens"]),
        "costUsd": cost,
        "limitUsd": limit_usd,
        "remainingUsd": round(max(0.0, limit_usd - cost), 6),
        "releaseAt": release_at,
    }


def coach_answer(question: str, profile: dict[str, Any], plan: dict[str, Any]) -> str:
    key = os.getenv("OPENCODE_GO_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AI-coachen er ikke konfigureret.")
    safe_profile = {k: v for k, v in profile.items() if k not in {"consent", "medication"} and not k.startswith("_")}
    program = plan.get("program", {})
    today_titles = [day.get("movement", {}).get("title", "") for day in plan.get("days", [])]
    prompt = f"""Brugerens pseudonymiserede profil: {json.dumps(safe_profile, ensure_ascii=False)}
Forløb: uge {program.get('currentWeek', 1)} af {program.get('totalWeeks', 1)}, fase {program.get('phase', 'rolig start')}.
Ugens aktiviteter: {json.dumps(today_titles, ensure_ascii=False)}
Brugerens spørgsmål: {question}

Svar på dansk i højst 170 ord. Vær konkret, varm og ikke-dømmende. Brug planen som udgangspunkt.
Giv højst tre små handlemuligheder. Du må ikke diagnosticere, ændre medicin, anbefale faste,
kosttilskud eller ekstreme restriktioner. Ved stærke smerter, akut åndenød, brystsmerter,
spiseforstyrrelse eller spørgsmål om medicin skal du tydeligt henvise til relevant fagperson.
Skriv almindelig tekst uden markdown-overskrift."""
    return opencode_text(
        key,
        prompt,
        max_tokens=600,
        phase="Fri Form-coach",
        system_message="Du er Fri Forms forsigtige danske livsstilscoach. Du giver generel støtte, aldrig lægelig behandling.",
    ).strip()[:3000]


class AppHandler(BaseHTTPRequestHandler):
    server_version = "FriForm/2"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    @property
    def client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return forwarded or self.client_address[0]

    def security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

    def json_response(self, status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self, max_bytes: int = 100_000) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Ugyldig forespørgsel.")
        if length <= 0 or length > max_bytes:
            raise ValueError("Forespørgslen er tom eller for stor.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Ugyldig JSON.")
        if not isinstance(value, dict):
            raise ValueError("JSON skal være et objekt.")
        return value

    def session(self) -> sqlite3.Row | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        if not morsel:
            return None
        token_hash = hashlib.sha256(morsel.value.encode()).hexdigest()
        with db() as conn:
            row = conn.execute(
                """SELECT s.token_hash,s.user_id,s.csrf_token,s.expires_at,u.email,u.name,
                   u.program_days,u.program_started_at,u.program_ends_at
                   FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""",
                (token_hash,),
            ).fetchone()
            if row and row["expires_at"] > iso_now():
                return row
            if row:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        return None

    def require_session(self, csrf: bool = False) -> sqlite3.Row | None:
        session = self.session()
        if not session:
            self.json_response(HTTPStatus.UNAUTHORIZED, {"error": "Log ind for at fortsætte."})
            return None
        if csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf_token"]):
            self.json_response(HTTPStatus.FORBIDDEN, {"error": "Sikkerhedstoken mangler. Genindlæs siden."})
            return None
        return session

    def origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            try:
                with db() as conn:
                    conn.execute("SELECT 1").fetchone()
                self.json_response(200, {"status": "ok", "database": "ok", "service": "fri-form"})
            except sqlite3.Error:
                self.json_response(503, {"status": "error"})
            return
        if path == "/api/capacity":
            with db() as conn:
                total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            enrolled = max(0, total - EXEMPT_EXISTING_USERS)
            self.json_response(200, {
                "limit": NEW_REGISTRATION_LIMIT,
                "enrolled": min(enrolled, NEW_REGISTRATION_LIMIT),
                "remaining": max(0, NEW_REGISTRATION_LIMIT - enrolled),
                "full": enrolled >= NEW_REGISTRATION_LIMIT,
            })
            return
        if path == "/api/me":
            session = self.session()
            if not session:
                self.json_response(200, {"authenticated": False})
                return
            with db() as conn:
                profile_row = conn.execute("SELECT data_json FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
                plan = latest_plan(conn, session["user_id"])
                if plan and profile_row and (
                    not plan["plan"].get("program")
                    or not plan["plan"].get("exerciseLibrary")
                ):
                    stored_profile = json.loads(profile_row["data_json"])
                    upgraded = ensure_meal_safety(plan["plan"], stored_profile)
                    upgraded = apply_program_structure(upgraded, stored_profile, int(plan["program_week"] or 1), total_weeks(session["program_days"]))
                    conn.execute("UPDATE plans SET plan_json=? WHERE id=? AND user_id=?", (json.dumps(upgraded, ensure_ascii=False), plan["id"], session["user_id"]))
                    plan["plan"] = upgraded
                checkins = [dict(row) for row in conn.execute("SELECT day,item_id,completed,weight,mood,updated_at FROM checkins WHERE user_id=? ORDER BY day", (session["user_id"],))]
                reviews = [dict(row) for row in conn.execute("SELECT program_week,weight,energy,difficulty,pain,win_text,challenge_text,next_focus,created_at FROM weekly_reviews WHERE user_id=? ORDER BY program_week", (session["user_id"],))]
                plan_history = [dict(row) for row in conn.execute("SELECT id,program_week,created_at,emailed_at,provider FROM plans WHERE user_id=? ORDER BY program_week,id", (session["user_id"],))]
                coach_messages = [dict(row) for row in conn.execute("SELECT role,content,created_at FROM (SELECT id,role,content,created_at FROM coach_messages WHERE user_id=? ORDER BY id DESC LIMIT 20) ORDER BY id", (session["user_id"],))]
            self.json_response(200, {
                "authenticated": True,
                "user": user_payload(session),
                "csrf": session["csrf_token"],
                "profile": json.loads(profile_row["data_json"]) if profile_row else None,
                "latestPlan": plan,
                "checkins": checkins,
                "weeklyReviews": reviews,
                "planHistory": plan_history,
                "coachMessages": coach_messages,
            })
            return
        if path == "/api/admin/stats":
            session = self.require_session()
            if not session:
                return
            if session["email"].lower() != ADMIN_EMAIL:
                self.json_response(HTTPStatus.FORBIDDEN, {"error": "Kun administratoren har adgang."})
                return
            week_ago = (utc_now() - timedelta(days=7)).isoformat()
            month_ago = (utc_now() - timedelta(days=30)).isoformat()
            today = utc_now().date().isoformat()
            with db() as conn:
                counts = {
                    "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                    "newToday": conn.execute("SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
                    "new7Days": conn.execute("SELECT COUNT(*) FROM users WHERE created_at>=?", (week_ago,)).fetchone()[0],
                    "active7Days": conn.execute("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE created_at>=?", (week_ago,)).fetchone()[0],
                    "active30Days": conn.execute("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE created_at>=?", (month_ago,)).fetchone()[0],
                    "profiles": conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0],
                    "plans": conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0],
                    "emailsSent": conn.execute("SELECT COUNT(*) FROM plans WHERE emailed_at IS NOT NULL").fetchone()[0],
                    "completedSteps": conn.execute("SELECT COUNT(*) FROM checkins WHERE completed=1").fetchone()[0],
                    "weeklyReviews": conn.execute("SELECT COUNT(*) FROM weekly_reviews").fetchone()[0],
                    "coachAnswers": conn.execute("SELECT COUNT(*) FROM coach_messages WHERE role='assistant'").fetchone()[0],
                    "failedJobs": conn.execute("SELECT COUNT(*) FROM plan_jobs WHERE status='failed'").fetchone()[0],
                }
                enrolled = max(0, counts["users"] - EXEMPT_EXISTING_USERS)
                counts["enrollmentLimit"] = NEW_REGISTRATION_LIMIT
                counts["enrolledNew"] = min(enrolled, NEW_REGISTRATION_LIMIT)
                counts["enrollmentRemaining"] = max(0, NEW_REGISTRATION_LIMIT - enrolled)
                recent = [dict(row) for row in conn.execute(
                    """SELECT u.email,u.name,u.created_at,u.last_login_at,u.program_days,u.program_ends_at,
                       COUNT(DISTINCT p.id) AS plans,
                       COUNT(DISTINCT c.day || ':' || c.item_id) AS checkins
                       FROM users u
                       LEFT JOIN plans p ON p.user_id=u.id
                       LEFT JOIN checkins c ON c.user_id=u.id AND c.completed=1
                       GROUP BY u.id ORDER BY u.id DESC LIMIT 25"""
                )]
                active_row = conn.execute(
                    """SELECT e.job_id,e.phase,e.started_at,
                       (SELECT COUNT(*) FROM ai_usage_events done WHERE done.job_id=e.job_id AND done.status='completed') AS completed_calls
                       FROM ai_usage_events e WHERE e.status='running' ORDER BY e.id DESC LIMIT 1"""
                ).fetchone()
                usage_events = [dict(row) for row in conn.execute(
                    """SELECT phase,status,input_tokens,output_tokens,cache_read_tokens,
                       estimated_cost_usd,started_at,finished_at,error_type
                       FROM ai_usage_events ORDER BY id DESC LIMIT 20"""
                )]
                ai_usage = {
                    "configured": bool(os.getenv("OPENCODE_GO_API_KEY", "").strip()),
                    "model": "qwen3.6-plus",
                    "active": ({**dict(active_row), "total_calls": 5 if active_row["job_id"] else 1} if active_row else None),
                    "fiveHours": ai_usage_window(conn, 5 * 3600, 12.0),
                    "week": ai_usage_window(conn, 7 * 86400, 30.0),
                    "month": ai_usage_window(conn, 30 * 86400, 60.0),
                    "recentEvents": usage_events,
                    "authoritativeUrl": "https://opencode.ai/console",
                    "scope": "Kun Fri Forms registrerede API-kald; OpenCode-console er autoritativ for hele kontoen.",
                }
            self.json_response(200, {"counts": counts, "recentUsers": recent, "aiUsage": ai_usage, "generatedAt": iso_now()})
            return
        if path.startswith("/api/plan/jobs/"):
            session = self.require_session()
            if not session:
                return
            job_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", job_id):
                self.json_response(404, {"error": "Jobbet blev ikke fundet."})
                return
            with db() as conn:
                job = conn.execute("SELECT status,error,plan_id,provider,email_sent,updated_at FROM plan_jobs WHERE id=? AND user_id=?", (job_id, session["user_id"])).fetchone()
                plan_row = None
                if job and job["status"] == "done" and job["plan_id"]:
                    plan_row = conn.execute("SELECT plan_json FROM plans WHERE id=? AND user_id=?", (job["plan_id"], session["user_id"])).fetchone()
            if not job:
                self.json_response(404, {"error": "Jobbet blev ikke fundet."})
                return
            self.json_response(200, {"status": job["status"], "error": job["error"], "provider": job["provider"], "email_sent": bool(job["email_sent"]), "plan": json.loads(plan_row["plan_json"]) if plan_row else None, "updated_at": job["updated_at"]})
            return
        if path.startswith("/api/"):
            self.json_response(404, {"error": "Ikke fundet."})
            return
        self.serve_static(path)

    def do_HEAD(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self.send_response(200)
            self.security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.startswith("/api/"):
            self.send_error(404)
            return
        relative = "index.html" if path in {"/", "/admin", "/reset-password"} else path.lstrip("/")
        candidate = (DIST / relative).resolve()
        try:
            candidate.relative_to(DIST.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix in {".js", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(candidate.stat().st_size))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if "/assets/" in str(candidate).replace("\\", "/") else "no-cache")
        self.end_headers()

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if not self.origin_ok():
            self.json_response(403, {"error": "Ugyldig oprindelse."})
            return
        try:
            if path == "/api/auth/register":
                if not rate_allowed(f"register:{self.client_ip}", 5, 3600):
                    self.json_response(429, {"error": "For mange forsøg. Prøv igen senere."})
                    return
                data = self.read_json()
                email, name, password = clean_email(data.get("email")), clean_name(data.get("name")), validate_password(data.get("password"))
                program_days = validate_program_days(data.get("programDays"))
                program_started = iso_now()
                program_ends = (utc_now() + timedelta(days=program_days)).isoformat()
                try:
                    with db() as conn:
                        conn.execute("BEGIN IMMEDIATE")
                        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                        if total >= EXEMPT_EXISTING_USERS + NEW_REGISTRATION_LIMIT:
                            raise RegistrationFullError()
                        cursor = conn.execute(
                            """INSERT INTO users(email,name,password_hash,created_at,program_days,program_started_at,program_ends_at)
                               VALUES(?,?,?,?,?,?,?)""",
                            (email, name, password_hash(password), iso_now(), program_days, program_started, program_ends),
                        )
                        raw, csrf = make_session(conn, cursor.lastrowid)
                except RegistrationFullError:
                    self.json_response(409, {"error": "De 20 pladser er optaget. Tilmeldingen er midlertidigt lukket.", "capacity_full": True})
                    return
                except sqlite3.IntegrityError:
                    self.json_response(409, {"error": "Der findes allerede en konto med denne e-mail."})
                    return
                cookie = f"{COOKIE_NAME}={raw}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax"
                self.json_response(201, {"ok": True, "csrf": csrf, "user": {"email": email, "name": name, "isAdmin": email == ADMIN_EMAIL, "programDays": program_days, "programStartedAt": program_started, "programEndsAt": program_ends}}, {"Set-Cookie": cookie})
                return

            if path == "/api/auth/login":
                if not rate_allowed(f"login:{self.client_ip}", 12, 900):
                    self.json_response(429, {"error": "For mange loginforsøg. Vent lidt og prøv igen."})
                    return
                data = self.read_json()
                email, password = clean_email(data.get("email")), str(data.get("password", ""))
                with db() as conn:
                    user = conn.execute("SELECT id,email,name,password_hash,program_days,program_started_at,program_ends_at FROM users WHERE email=?", (email,)).fetchone()
                    if not user or not password_ok(password, user["password_hash"]):
                        self.json_response(401, {"error": "E-mail eller adgangskode er forkert."})
                        return
                    raw, csrf = make_session(conn, user["id"])
                    conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (iso_now(), user["id"]))
                cookie = f"{COOKIE_NAME}={raw}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax"
                self.json_response(200, {"ok": True, "csrf": csrf, "user": user_payload(user)}, {"Set-Cookie": cookie})
                return

            if path == "/api/auth/forgot-password":
                data = self.read_json()
                email = clean_email(data.get("email"))
                email_key = hashlib.sha256(email.encode()).hexdigest()[:20]
                allowed = rate_allowed(f"forgot-ip:{self.client_ip}", 8, 3600)
                allowed = rate_allowed(f"forgot-email:{email_key}", 3, 3600) and allowed
                if allowed:
                    with db() as conn:
                        user = conn.execute("SELECT id,email,name FROM users WHERE email=?", (email,)).fetchone()
                        if user:
                            raw_token = secrets.token_urlsafe(32)
                            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                            conn.execute("UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (iso_now(), user["id"]))
                            conn.execute(
                                "INSERT INTO password_reset_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                                (token_hash, user["id"], (utc_now() + timedelta(minutes=60)).isoformat(), iso_now()),
                            )
                            threading.Thread(
                                target=send_password_reset_email_safely,
                                args=(user["email"], user["name"], raw_token),
                                daemon=True,
                                name=f"reset-{user['id']}",
                            ).start()
                self.json_response(200, {"ok": True, "message": "Hvis adressen findes, sender vi et nulstillingslink."})
                return

            if path == "/api/auth/reset-password":
                if not rate_allowed(f"reset:{self.client_ip}", 10, 3600):
                    self.json_response(429, {"error": "For mange forsøg. Prøv igen senere."})
                    return
                data = self.read_json()
                raw_token = str(data.get("token", ""))
                if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", raw_token):
                    raise ValueError("Linket er ugyldigt eller udløbet.")
                password = validate_password(data.get("password"))
                token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                with db() as conn:
                    token = conn.execute(
                        "SELECT user_id FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                        (token_hash, iso_now()),
                    ).fetchone()
                    if not token:
                        raise ValueError("Linket er ugyldigt eller udløbet.")
                    changed = conn.execute(
                        "UPDATE password_reset_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                        (iso_now(), token_hash),
                    )
                    if changed.rowcount != 1:
                        raise ValueError("Linket er ugyldigt eller udløbet.")
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), token["user_id"]))
                    conn.execute("DELETE FROM sessions WHERE user_id=?", (token["user_id"],))
                    conn.execute("UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (iso_now(), token["user_id"]))
                self.json_response(200, {"ok": True}, {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"})
                return

            if path == "/api/auth/logout":
                session = self.require_session(csrf=True)
                if not session:
                    return
                with db() as conn:
                    conn.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))
                self.json_response(200, {"ok": True}, {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"})
                return

            if path == "/api/plan/generate":
                session = self.require_session(csrf=True)
                if not session:
                    return
                if not rate_allowed(f"generate:{session['user_id']}", 3, 86400):
                    self.json_response(429, {"error": "Du kan lave op til tre nye planer i døgnet."})
                    return
                profile = validate_profile(self.read_json(max_bytes=40_000).get("profile"))
                blocked = safety_block(profile)
                if blocked:
                    self.json_response(422, {"error": blocked, "safety_block": True})
                    return
                job_id = secrets.token_urlsafe(18)
                with db() as conn:
                    latest = latest_plan(conn, session["user_id"])
                    program_week = int(latest["program_week"]) if latest else 1
                    conn.execute("INSERT INTO plan_jobs(id,user_id,status,created_at,updated_at,program_week) VALUES(?,?,?,?,?,?)", (job_id, session["user_id"], "pending", iso_now(), iso_now(), program_week))
                weeks = total_weeks(session["program_days"])
                threading.Thread(target=run_plan_job, args=(job_id, session["user_id"], session["email"], session["name"], profile, program_week, weeks), daemon=True, name=f"plan-{job_id[:8]}").start()
                self.json_response(202, {"ok": True, "job_id": job_id, "status": "pending"})
                return

            if path == "/api/program/next-week":
                session = self.require_session(csrf=True)
                if not session:
                    return
                if not rate_allowed(f"next-week:{session['user_id']}", 2, 86400):
                    self.json_response(429, {"error": "Du kan højst starte næste uge to gange i døgnet."})
                    return
                data = self.read_json(max_bytes=20_000)
                with db() as conn:
                    latest = latest_plan(conn, session["user_id"])
                    profile_row = conn.execute("SELECT data_json FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
                if not latest or not profile_row:
                    self.json_response(404, {"error": "Lav din første ugeplan først."})
                    return
                current_week = int(latest["program_week"])
                weeks = total_weeks(session["program_days"])
                if current_week >= weeks:
                    self.json_response(409, {"error": "Du har nået sidste uge i dit valgte forløb. Du kan stadig opdatere din profil og fortsætte gratis."})
                    return
                energy = int(data.get("energy", 3))
                difficulty = int(data.get("difficulty", 3))
                pain = int(data.get("pain", 0))
                if energy not in range(1, 6) or difficulty not in range(1, 6) or pain not in range(0, 6):
                    raise ValueError("Vælg værdierne på skalaerne.")
                if pain == 5:
                    self.json_response(422, {"error": "Ved stærke eller vedvarende smerter skal træningen sættes på pause og vurderes af en fagperson.", "safety_block": True})
                    return
                weight = data.get("weight")
                if weight not in (None, ""):
                    weight = round(float(weight), 1)
                    if not 40 <= weight <= 300:
                        raise ValueError("Ugyldig vægt.")
                clean_text = lambda key: re.sub(r"\s+", " ", str(data.get(key, "")).strip())[:500]
                win, challenge, next_focus = clean_text("win"), clean_text("challenge"), clean_text("nextFocus")
                if not win or not challenge:
                    raise ValueError("Skriv kort, hvad der virkede, og hvad der var svært.")
                review_text = f"energi {energy}/5, sværhedsgrad {difficulty}/5, smerte {pain}/5; virkede: {win}; svært: {challenge}; ønsket fokus: {next_focus or 'fortsæt roligt'}"
                next_week = current_week + 1
                job_id = secrets.token_urlsafe(18)
                with db() as conn:
                    existing_job = conn.execute("SELECT id FROM plan_jobs WHERE user_id=? AND program_week=? AND status IN ('pending','running') LIMIT 1", (session["user_id"], next_week)).fetchone()
                    if existing_job:
                        self.json_response(409, {"error": "Næste uge er allerede ved at blive lavet. Vent på mailen."})
                        return
                    conn.execute(
                        """INSERT INTO weekly_reviews(user_id,program_week,weight,energy,difficulty,pain,win_text,challenge_text,next_focus,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,program_week) DO UPDATE SET
                           weight=excluded.weight,energy=excluded.energy,difficulty=excluded.difficulty,pain=excluded.pain,
                           win_text=excluded.win_text,challenge_text=excluded.challenge_text,next_focus=excluded.next_focus,created_at=excluded.created_at""",
                        (session["user_id"], current_week, weight, energy, difficulty, pain, win, challenge, next_focus, iso_now()),
                    )
                    conn.execute("INSERT INTO plan_jobs(id,user_id,status,created_at,updated_at,program_week) VALUES(?,?,?,?,?,?)", (job_id, session["user_id"], "pending", iso_now(), iso_now(), next_week))
                profile = json.loads(profile_row["data_json"])
                threading.Thread(target=run_plan_job, args=(job_id, session["user_id"], session["email"], session["name"], profile, next_week, weeks, review_text), daemon=True, name=f"week-{job_id[:8]}").start()
                self.json_response(202, {"ok": True, "job_id": job_id, "status": "pending", "program_week": next_week})
                return

            if path == "/api/meal/swap":
                session = self.require_session(csrf=True)
                if not session:
                    return
                if not rate_allowed(f"meal-swap:{session['user_id']}", 20, 86400):
                    self.json_response(429, {"error": "Grænsen for måltidsbytter i dag er nået."})
                    return
                data = self.read_json()
                day_number = int(data.get("day", 0))
                kind = str(data.get("kind", ""))
                if day_number not in range(1, 8) or kind not in {"breakfast", "lunch", "dinner", "snack"}:
                    raise ValueError("Ugyldigt måltid.")
                with db() as conn:
                    latest = latest_plan(conn, session["user_id"])
                    profile_row = conn.execute("SELECT data_json FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
                if not latest or not profile_row:
                    self.json_response(404, {"error": "Planen blev ikke fundet."})
                    return
                profile = json.loads(profile_row["data_json"])
                plan = latest["plan"]
                meal = plan["days"][day_number - 1]["meals"][kind]
                options = meal_options(kind, profile)
                replacement = next((item for item in options if item["title"] != meal.get("title")), None)
                if replacement:
                    replacement.pop("diets", None)
                else:
                    replacement = safe_meal(kind, profile, meal.get("title", ""))
                plan["days"][day_number - 1]["meals"][kind] = replacement
                additions = plan.setdefault("shoppingList", {}).setdefault("andet", [])
                for ingredient in replacement.get("ingredients", []):
                    if ingredient not in additions:
                        additions.append(ingredient)
                with db() as conn:
                    conn.execute("UPDATE plans SET plan_json=? WHERE id=? AND user_id=?", (json.dumps(plan, ensure_ascii=False), latest["id"], session["user_id"]))
                self.json_response(200, {"ok": True, "meal": replacement, "plan": plan})
                return

            if path == "/api/coach":
                session = self.require_session(csrf=True)
                if not session:
                    return
                if not rate_allowed(f"coach:{session['user_id']}", 12, 86400):
                    self.json_response(429, {"error": "Du har brugt dagens 12 coach-svar. Prøv igen i morgen."})
                    return
                question = re.sub(r"\s+", " ", str(self.read_json(max_bytes=8_000).get("question", "")).strip())[:800]
                if len(question) < 3:
                    raise ValueError("Skriv et spørgsmål til coachen.")
                with db() as conn:
                    profile_row = conn.execute("SELECT data_json FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
                    latest = latest_plan(conn, session["user_id"])
                if not profile_row or not latest:
                    self.json_response(404, {"error": "Lav først en plan."})
                    return
                answer = coach_answer(question, json.loads(profile_row["data_json"]), latest["plan"])
                with db() as conn:
                    conn.execute("INSERT INTO coach_messages(user_id,role,content,created_at) VALUES(?,?,?,?)", (session["user_id"], "user", question, iso_now()))
                    conn.execute("INSERT INTO coach_messages(user_id,role,content,created_at) VALUES(?,?,?,?)", (session["user_id"], "assistant", answer, iso_now()))
                    conn.execute("DELETE FROM coach_messages WHERE user_id=? AND id NOT IN (SELECT id FROM coach_messages WHERE user_id=? ORDER BY id DESC LIMIT 100)", (session["user_id"], session["user_id"]))
                self.json_response(200, {"ok": True, "answer": answer, "createdAt": iso_now()})
                return

            if path == "/api/plan/email":
                session = self.require_session(csrf=True)
                if not session:
                    return
                if not rate_allowed(f"email:{session['user_id']}", 4, 86400):
                    self.json_response(429, {"error": "E-mailgrænsen for i dag er nået."})
                    return
                with db() as conn:
                    plan_row = latest_plan(conn, session["user_id"])
                if not plan_row:
                    self.json_response(404, {"error": "Lav først en plan."})
                    return
                send_plan_email(session["email"], session["name"], plan_row["plan"])
                with db() as conn:
                    conn.execute("UPDATE plans SET emailed_at=? WHERE id=? AND user_id=?", (iso_now(), plan_row["id"], session["user_id"]))
                self.json_response(200, {"ok": True})
                return

            if path == "/api/checkin":
                session = self.require_session(csrf=True)
                if not session:
                    return
                data = self.read_json()
                day = str(data.get("day", ""))
                item_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(data.get("itemId", "")))[:80]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not item_id:
                    raise ValueError("Ugyldigt check-in.")
                weight = data.get("weight")
                if weight is not None:
                    weight = round(float(weight), 1)
                    if not 40 <= weight <= 300:
                        raise ValueError("Ugyldig vægt.")
                mood = data.get("mood")
                if mood is not None and int(mood) not in range(1, 6):
                    raise ValueError("Ugyldigt energiniveau.")
                with db() as conn:
                    conn.execute("INSERT INTO checkins(user_id,day,item_id,completed,weight,mood,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,day,item_id) DO UPDATE SET completed=excluded.completed,weight=COALESCE(excluded.weight,checkins.weight),mood=COALESCE(excluded.mood,checkins.mood),updated_at=excluded.updated_at", (session["user_id"], day, item_id, int(bool(data.get("completed"))), weight, int(mood) if mood is not None else None, iso_now()))
                self.json_response(200, {"ok": True})
                return

            self.json_response(404, {"error": "Ikke fundet."})
        except ValueError as exc:
            self.json_response(400, {"error": str(exc)})
        except (urllib.error.URLError, smtplib.SMTPException, TimeoutError):
            self.json_response(502, {"error": "Den eksterne tjeneste svarede ikke. Prøv igen om lidt."})
        except Exception as exc:
            print(f"Unhandled POST error: {type(exc).__name__}", file=sys.stderr, flush=True)
            self.json_response(500, {"error": "Der opstod en uventet fejl."})

    def do_DELETE(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/api/account":
            self.json_response(404, {"error": "Ikke fundet."})
            return
        session = self.require_session(csrf=True)
        if not session:
            return
        with db() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (session["user_id"],))
        self.json_response(200, {"ok": True}, {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"})

    def serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"/", "/admin", "/reset-password"} else request_path.lstrip("/")
        candidate = (DIST / relative).resolve()
        try:
            candidate.relative_to(DIST.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix in {".js", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if "/assets/" in str(candidate).replace("\\", "/") else "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    init_db()
    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler)
    print(f"Fri Form listening on 0.0.0.0:{PORT}; db={DB_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
