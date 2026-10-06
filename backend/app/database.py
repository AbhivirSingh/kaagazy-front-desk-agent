import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from .config import CLINIC_JSON_PATH

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clinic_info (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    timezone TEXT NOT NULL,
    slot_minutes INTEGER NOT NULL,
    reference_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    speciality TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctor_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL,
    day TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    FOREIGN KEY(doctor_id) REFERENCES doctors(id)
);

CREATE TABLE IF NOT EXISTS doctor_leaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL,
    leave_date TEXT NOT NULL,
    FOREIGN KEY(doctor_id) REFERENCES doctors(id),
    UNIQUE(doctor_id, leave_date)
);

CREATE TABLE IF NOT EXISTS holidays (
    holiday_date TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    dob TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_guardians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guardian_id TEXT NOT NULL,
    ward_id TEXT NOT NULL,
    FOREIGN KEY(guardian_id) REFERENCES patients(id),
    FOREIGN KEY(ward_id) REFERENCES patients(id),
    UNIQUE(guardian_id, ward_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_id TEXT NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('booked', 'cancelled', 'rescheduled', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    FOREIGN KEY(doctor_id) REFERENCES doctors(id)
);

-- Index for slot conflict checking
CREATE INDEX IF NOT EXISTS idx_appointments_slot ON appointments(doctor_id, date, start_time, status);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id, status);

CREATE TABLE IF NOT EXISTS conversation_runs (
    conversation_id TEXT PRIMARY KEY,
    today TEXT NOT NULL,
    turns_json TEXT NOT NULL,
    tool_calls_json TEXT NOT NULL,
    terminal_state TEXT NOT NULL,
    escalation_reason TEXT,
    patient_id TEXT,
    appointment_id TEXT,
    reply TEXT NOT NULL,
    metrics_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    caller_said TEXT,
    reason TEXT NOT NULL,
    detail TEXT,
    status TEXT NOT NULL DEFAULT 'open', -- 'open', 'resolved'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Cached parsed JSON to speed up database re-seeding
_CLINIC_CACHE: Optional[Dict[str, Any]] = None
_CACHE_LOCK = threading.Lock()


def get_clinic_data() -> Dict[str, Any]:
    global _CLINIC_CACHE
    if _CLINIC_CACHE is None:
        with _CACHE_LOCK:
            if _CLINIC_CACHE is None:
                path = Path(CLINIC_JSON_PATH)
                if not path.exists():
                    raise FileNotFoundError(f"clinic.json not found at {CLINIC_JSON_PATH}")
                with path.open("r", encoding="utf-8") as f:
                    _CLINIC_CACHE = json.load(f)
    return _CLINIC_CACHE


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


def seed_database(conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
    cur = conn.cursor()
    # Clinic
    clinic = data["clinic"]
    cur.execute(
        "INSERT OR REPLACE INTO clinic_info (id, name, city, timezone, slot_minutes, reference_date) VALUES (?, ?, ?, ?, ?, ?)",
        (clinic["id"], clinic["name"], clinic["city"], clinic["timezone"], clinic["slot_minutes"], clinic["reference_date"])
    )

    # Doctors & windows & leaves
    for doc in data.get("doctors", []):
        cur.execute(
            "INSERT OR REPLACE INTO doctors (id, name, speciality) VALUES (?, ?, ?)",
            (doc["id"], doc["name"], doc["speciality"])
        )
        for win in doc.get("windows", []):
            cur.execute(
                "INSERT INTO doctor_windows (doctor_id, day, start_time, end_time) VALUES (?, ?, ?, ?)",
                (doc["id"], win["day"], win["start"], win["end"])
            )
        for leave in doc.get("leave_dates", []):
            cur.execute(
                "INSERT OR IGNORE INTO doctor_leaves (doctor_id, leave_date) VALUES (?, ?)",
                (doc["id"], leave)
            )

    # Holidays
    for hol in data.get("holidays", []):
        cur.execute("INSERT OR IGNORE INTO holidays (holiday_date) VALUES (?)", (hol,))

    # Patients (first pass)
    for pt in data.get("patients", []):
        cur.execute(
            "INSERT OR REPLACE INTO patients (id, name, phone, dob) VALUES (?, ?, ?, ?)",
            (pt["id"], pt["name"], pt["phone"], pt["dob"])
        )

    # Guardianships (second pass after all patients exist)
    for pt in data.get("patients", []):
        for ward_id in pt.get("guardian_of", []):
            cur.execute(
                "INSERT OR IGNORE INTO patient_guardians (guardian_id, ward_id) VALUES (?, ?)",
                (pt["id"], ward_id)
            )

    # Initial Appointments
    for ap in data.get("appointments", []):
        cur.execute(
            "INSERT OR REPLACE INTO appointments (id, patient_id, doctor_id, date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ap["id"], ap["patient_id"], ap["doctor_id"], ap["date"], ap["start"], ap["end"], ap["status"])
        )

    conn.commit()


def get_fresh_db_connection() -> sqlite3.Connection:
    """
    Creates an isolated in-memory SQLite database pre-seeded with clinic.json.
    Ensures that state changes in one run do not leak into another run.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    seed_database(conn, get_clinic_data())
    return conn
