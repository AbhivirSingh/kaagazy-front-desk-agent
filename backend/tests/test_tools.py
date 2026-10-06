import pytest
import sqlite3
from backend.app.database import get_fresh_db_connection
from backend.app.tools import (
    search_slots,
    lookup_patient,
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
    escalate_to_human,
)


@pytest.fixture
def db():
    conn = get_fresh_db_connection()
    yield conn
    conn.close()


def test_search_slots_normal_day(db):
    res = search_slots(db, "dr_rao", "2026-10-01")
    assert res["success"] is True
    assert res["count"] > 0
    # 09:30 and 10:00 and 17:00 are booked in clinic.json
    assert "09:30" not in res["slots"]
    assert "10:00" not in res["slots"]
    assert "09:00" in res["slots"]


def test_search_slots_holiday(db):
    res = search_slots(db, "dr_rao", "2026-10-02")
    assert res["success"] is True
    assert res["count"] == 0
    assert "holiday" in res["message"].lower()


def test_search_slots_doctor_leave(db):
    res = search_slots(db, "dr_sethi", "2026-10-05")
    assert res["success"] is True
    assert res["count"] == 0
    assert "leave" in res["message"].lower()


def test_search_slots_sunday(db):
    res = search_slots(db, "dr_rao", "2026-10-04")
    assert res["success"] is True
    assert res["count"] == 0
    assert "no scheduled clinic hours" in res["message"].lower()


def test_lookup_patient_ambiguous(db):
    res = lookup_patient(db, query="Sharma")
    assert res["success"] is True
    assert res["ambiguous"] is True
    assert res["count"] >= 3
    names = [c["name"] for c in res["candidates"]]
    assert "Rajesh Kumar Sharma" in names
    assert "R. K. Sharma" in names
    assert "Rajesh Sharma" in names


def test_lookup_patient_unambiguous(db):
    res = lookup_patient(db, query="Rajesh Kumar Sharma", phone="9812200011")
    assert res["success"] is True
    assert res["ambiguous"] is False
    assert res["count"] == 1
    assert res["patient"]["id"] == "pt_0001"


def test_lookup_patient_with_guardian(db):
    res = lookup_patient(db, query="Sunita Gupta", phone="9812200166")
    assert res["success"] is True
    assert res["patient"]["id"] == "pt_0008"
    assert "pt_0006" in res["patient"]["guardian_of"]
    assert "pt_0007" in res["patient"]["guardian_of"]


def test_book_appointment_success(db):
    # Book on 2026-10-03 at 09:30 with dr_rao
    res = book_appointment(db, "pt_0014", "dr_rao", "2026-10-03", "09:30")
    assert res["success"] is True
    assert res["appointment_id"] == "ap_0026"
    assert res["status"] == "booked"

    # Now verify the slot is no longer available
    slots = search_slots(db, "dr_rao", "2026-10-03")
    assert "09:30" not in slots["slots"]


def test_book_appointment_conflict_rejection(db):
    # ap_0001 is on 2026-10-01 at 09:30 with dr_rao
    res = book_appointment(db, "pt_0002", "dr_rao", "2026-10-01", "09:30")
    assert res["success"] is False
    assert "already booked" in res["error"]


def test_reschedule_appointment_success(db):
    # Reschedule ap_0001 to 2026-10-03 at 10:00
    res = reschedule_appointment(db, "ap_0001", "2026-10-03", "10:00")
    assert res["success"] is True
    assert res["status"] == "rescheduled"
    assert res["new_date"] == "2026-10-03"
    assert res["new_start"] == "10:00"


def test_cancel_appointment_success(db):
    res = cancel_appointment(db, "ap_0001")
    assert res["success"] is True
    assert res["status"] == "cancelled"

    # Slot 09:30 on 2026-10-01 should now be open
    slots = search_slots(db, "dr_rao", "2026-10-01")
    assert "09:30" in slots["slots"]


def test_escalate_to_human(db):
    res = escalate_to_human(db, reason="clinical_urgent", detail="Chest pain reported")
    assert res["success"] is True
    assert res["escalated"] is True
    assert res["reason"] == "clinical_urgent"
