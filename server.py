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
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


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
SESSION_DAYS = 30
COOKIE_NAME = "friform_session"
ALLOWED_ORIGINS = {
    "https://fit.dybbol.com",
    "http://localhost:8963",
    "http://127.0.0.1:8963",
}
RATE_LOCK = threading.Lock()
RATE_BUCKETS: dict[str, list[float]] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


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
              last_login_at TEXT
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
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_plans_user_created ON plans(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_checkins_user_day ON checkins(user_id, day);
            CREATE INDEX IF NOT EXISTS idx_plan_jobs_user_created ON plan_jobs(user_id, created_at DESC);
            PRAGMA optimize;
            """
        )
        conn.execute("UPDATE plan_jobs SET status='failed',error='Serveren blev genstartet. Lav planen igen.',updated_at=? WHERE status IN ('pending','running')", (iso_now(),))


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
        "SELECT id,plan_json,provider,created_at,emailed_at FROM plans WHERE user_id=? ORDER BY id DESC LIMIT 1",
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
        "allergies": re.sub(r"\s+", " ", str(raw.get("allergies", "")))[:200],
        "dislikes": re.sub(r"\s+", " ", str(raw.get("dislikes", "")))[:200],
        "cookingMinutes": int(bounded_number(raw, "cookingMinutes", 10, 90)),
        "consent": bool(raw.get("consent", False)),
    }
    for key, values in allowed.items():
        if result[key] not in values:
            raise ValueError(f"Ugyldigt valg i {key}.")
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
    return None


def plan_prompt(profile: dict[str, Any]) -> str:
    safe = {key: value for key, value in profile.items() if key != "consent"}
    return f"""
Lav en realistisk, detaljeret 7-dages vægttabsplan på dansk til en voksen.
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
      "breakfast":{{"title":"...","ingredients":["..."],"portion":"..."}},
      "lunch":{{"title":"...","ingredients":["..."],"portion":"..."}},
      "dinner":{{"title":"...","ingredients":["..."],"portion":"..."}},
      "snack":{{"title":"...","portion":"..."}}
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


def opencode_text(key: str, prompt: str, max_tokens: int = 2000) -> str:
    response = call_json_api(
        "https://opencode.ai/zen/go/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        {
            "model": "qwen3.6-plus",
            "system": "Du er en forsigtig dansk sundhedsplanlægger. Returnér kun gyldig JSON uden markdown.",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
        120,
    )
    blocks = [block.get("text", "") for block in response.get("content", []) if block.get("type") == "text"]
    if not blocks:
        raise ValueError("OpenCode returnerede ingen tekst.")
    return "\n".join(blocks)


def generate_opencode_plan(key: str, profile: dict[str, Any]) -> dict[str, Any]:
    safe_profile = json.dumps({k: v for k, v in profile.items() if k != "consent"}, ensure_ascii=False)
    common = f"Profil (uden navn og e-mail): {safe_profile}. Brug almindelige danske råvarer, tallerkenmodellen, gradvis aktivitet og alle valgte hensyn. Ingen faste, ekstreme kure, kosttilskud eller løfter."
    day_shape = """Hver dag skal have: day (tal), name, focus, meals med breakfast/lunch/dinner/snack; hvert måltid har title, ingredients (liste) og portion. movement har type, title, minutes, intensity, instructions (liste) og alternative. Desuden habit og encouragement."""
    prompts = {
        "overview": f"""{common}\nLav planens overblik som JSON med nøglerne title, intro, weeklyFocus, safetyNote, waterTip, sleepTip, strengthGuide, swimGuide, shoppingList, checkInQuestions og medicalReminder. strengthGuide er en liste med exercise, sets, reps, how og easier. swimGuide er en liste med part, minutes og how, når svømning er valgt. shoppingList har grupperne grønt, protein, fuldkornOgKartofler og andet.""",
        "days_12": f"""{common}\nLav dag 1-2 (Mandag-Tirsdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "days_34": f"""{common}\nLav dag 3-4 (Onsdag-Torsdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "days_56": f"""{common}\nLav dag 5-6 (Fredag-Lørdag) som JSON {{\"days\":[...]}}. {day_shape} Variation mellem valgte motionsformer og konkrete, forskellige måltider.""",
        "day_7": f"""{common}\nLav dag 7 (Søndag) som JSON {{\"days\":[...]}}. {day_shape} Gør dagen restituerende med mulighed for let aktivitet.""",
    }
    parts = {name: parse_json_object(opencode_text(key, prompt)) for name, prompt in prompts.items()}
    days = []
    for name in ("days_12", "days_34", "days_56", "day_7"):
        days.extend(parts[name].get("days", []))
    if len(days) != 7:
        raise ValueError("OpenCode returnerede ikke syv dage.")
    overview = parts["overview"]
    overview["days"] = days
    return extract_json(json.dumps(overview, ensure_ascii=False), profile)


def generate_ai_plan(profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
    prompt = plan_prompt(profile)
    key = os.getenv("OPENCODE_GO_API_KEY", "").strip()
    if key:
        try:
            return generate_opencode_plan(key, profile), "opencode-go/qwen3.6-plus"
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


def send_plan_email(recipient: str, name: str, plan: dict[str, Any]) -> None:
    user = os.getenv("GMAIL_SMTP_USER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not password:
        raise RuntimeError("Gmail SMTP er ikke konfigureret.")
    message = EmailMessage()
    message["Subject"] = "Din personlige Fri Form-plan"
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
        <h1 style="margin:8px 0 0">Din personlige ugeplan</h1>
      </div>
      <div style="padding:26px;background:#fbfaf4">
        <p>Hej {html.escape(name)},</p><p>{html.escape(str(plan['intro']))}</p>
        {''.join(html_days)}
        <p style="padding:16px;background:#edf5ef;border-radius:12px"><b>Vigtigt:</b> {html.escape(str(plan['medicalReminder']))}</p>
        <p><a href="https://fit.dybbol.com/" style="display:inline-block;background:#e56f3d;color:white;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:bold">Åbn min daglige plan</a></p>
      </div>
    </div>"""
    message.set_content(plain)
    message.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)


def run_plan_job(job_id: str, user_id: int, recipient: str, name: str, profile: dict[str, Any]) -> None:
    try:
        with db() as conn:
            conn.execute("UPDATE plan_jobs SET status='running',updated_at=? WHERE id=?", (iso_now(), job_id))
        plan, provider = generate_ai_plan(profile)
        email_sent = False
        try:
            send_plan_email(recipient, name, plan)
            email_sent = True
        except Exception as exc:
            print(f"Email send failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        with db() as conn:
            conn.execute("INSERT INTO profiles(user_id,data_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at", (user_id, json.dumps(profile, ensure_ascii=False), iso_now()))
            cursor = conn.execute("INSERT INTO plans(user_id,plan_json,provider,created_at,emailed_at) VALUES(?,?,?,?,?)", (user_id, json.dumps(plan, ensure_ascii=False), provider, iso_now(), iso_now() if email_sent else None))
            conn.execute("UPDATE plan_jobs SET status='done',plan_id=?,provider=?,email_sent=?,updated_at=? WHERE id=?", (cursor.lastrowid, provider, int(email_sent), iso_now(), job_id))
    except Exception as exc:
        print(f"Plan job failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        with db() as conn:
            conn.execute("UPDATE plan_jobs SET status='failed',error=?,updated_at=? WHERE id=?", ("Planen kunne ikke laves. Prøv igen om lidt.", iso_now(), job_id))


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
                "SELECT s.token_hash,s.user_id,s.csrf_token,s.expires_at,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
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
        if path == "/api/me":
            session = self.session()
            if not session:
                self.json_response(200, {"authenticated": False})
                return
            with db() as conn:
                profile_row = conn.execute("SELECT data_json FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
                plan = latest_plan(conn, session["user_id"])
                checkins = [dict(row) for row in conn.execute("SELECT day,item_id,completed,weight,mood,updated_at FROM checkins WHERE user_id=? ORDER BY day", (session["user_id"],))]
            self.json_response(200, {
                "authenticated": True,
                "user": {"email": session["email"], "name": session["name"]},
                "csrf": session["csrf_token"],
                "profile": json.loads(profile_row["data_json"]) if profile_row else None,
                "latestPlan": plan,
                "checkins": checkins,
            })
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
        relative = path.lstrip("/") or "index.html"
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
                try:
                    with db() as conn:
                        cursor = conn.execute("INSERT INTO users(email,name,password_hash,created_at) VALUES(?,?,?,?)", (email, name, password_hash(password), iso_now()))
                        raw, csrf = make_session(conn, cursor.lastrowid)
                except sqlite3.IntegrityError:
                    self.json_response(409, {"error": "Der findes allerede en konto med denne e-mail."})
                    return
                cookie = f"{COOKIE_NAME}={raw}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax"
                self.json_response(201, {"ok": True, "csrf": csrf, "user": {"email": email, "name": name}}, {"Set-Cookie": cookie})
                return

            if path == "/api/auth/login":
                if not rate_allowed(f"login:{self.client_ip}", 12, 900):
                    self.json_response(429, {"error": "For mange loginforsøg. Vent lidt og prøv igen."})
                    return
                data = self.read_json()
                email, password = clean_email(data.get("email")), str(data.get("password", ""))
                with db() as conn:
                    user = conn.execute("SELECT id,email,name,password_hash FROM users WHERE email=?", (email,)).fetchone()
                    if not user or not password_ok(password, user["password_hash"]):
                        self.json_response(401, {"error": "E-mail eller adgangskode er forkert."})
                        return
                    raw, csrf = make_session(conn, user["id"])
                    conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (iso_now(), user["id"]))
                cookie = f"{COOKIE_NAME}={raw}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax"
                self.json_response(200, {"ok": True, "csrf": csrf, "user": {"email": user["email"], "name": user["name"]}}, {"Set-Cookie": cookie})
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
                    conn.execute("INSERT INTO plan_jobs(id,user_id,status,created_at,updated_at) VALUES(?,?,?,?,?)", (job_id, session["user_id"], "pending", iso_now(), iso_now()))
                threading.Thread(target=run_plan_job, args=(job_id, session["user_id"], session["email"], session["name"], profile), daemon=True, name=f"plan-{job_id[:8]}").start()
                self.json_response(202, {"ok": True, "job_id": job_id, "status": "pending"})
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
        relative = request_path.lstrip("/") or "index.html"
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
