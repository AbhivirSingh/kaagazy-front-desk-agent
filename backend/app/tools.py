import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

VALID_ESCALATION_REASONS = {
    "clinical_urgent",
    "medical_advice",
    "not_authorised",
    "ambiguous_patient",
    "out_of_scope",
}

VALID_TERMINAL_STATES = {
    "booked",
    "rescheduled",
    "cancelled",
    "escalated",
    "refused",
    "abandoned",
}


def _resolve_doctor_id(conn: sqlite3.Connection, doctor_id_or_name: str) -> Optional[Dict[str, Any]]:
    """Resolves doctor identifier or name variation to doctor record."""
    if not doctor_id_or_name:
        return None
    raw = doctor_id_or_name.strip()
    cur = conn.cursor()
    # Try exact ID
    cur.execute("SELECT id, name, speciality FROM doctors WHERE id = ?", (raw.lower(),))
    row = cur.fetchone()
    if row:
        return dict(row)

    # Normalize name variations e.g. "Dr. Rao", "Rao", "Dr. Vikram Sethi"
    clean_name = raw.replace("Dr.", "").replace("Dr ", "").strip().lower()
    cur.execute("SELECT id, name, speciality FROM doctors WHERE LOWER(name) LIKE ? OR LOWER(id) LIKE ?",
                (f"%{clean_name}%", f"%{clean_name}%"))
    row = cur.fetchone()
    if row:
        return dict(row)
    return None


def _format_time(t_str: str) -> str:
    """Ensures HH:MM format."""
    parts = t_str.strip().split(":")
    if len(parts) == 1:
        # e.g. "9" or "10"
        return f"{int(parts[0]):02d}:00"
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def _add_minutes(time_str: str, minutes: int = 15) -> str:
    """Adds minutes to HH:MM string."""
    dt = datetime.strptime(time_str, "%H:%M") + timedelta(minutes=minutes)
    return dt.strftime("%H:%M")


def _is_time_in_range(start: str, end: str, current: str) -> bool:
    """Checks if current time is within [start, end)."""
    return start <= current < end


def search_slots(conn: sqlite3.Connection, doctor_id: str, date: str, window: Optional[str] = None) -> Dict[str, Any]:
    """
    Find available 15-minute appointment slots for a doctor on a given date.
    Strict ground truth: never invents slots.
    """
    doc = _resolve_doctor_id(conn, doctor_id)
    if not doc:
        return {
            "success": False,
            "error": f"Error: Unknown doctor '{doctor_id}'. Available doctors are Dr. Rao (dr_rao) and Dr. Sethi (dr_sethi).",
            "slots": [],
            "count": 0
        }

    doc_id = doc["id"]
    doc_name = doc["name"]

    # Validate date
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {
            "success": False,
            "error": f"Error: Invalid date format '{date}'. Expected YYYY-MM-DD.",
            "slots": [],
            "count": 0
        }

    day_of_week = dt.strftime("%a")  # Mon, Tue, Wed, Thu, Fri, Sat, Sun
    cur = conn.cursor()

    # 1. Check clinic holiday
    cur.execute("SELECT holiday_date FROM holidays WHERE holiday_date = ?", (date,))
    if cur.fetchone():
        return {
            "success": True,
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "date": date,
            "day": day_of_week,
            "slots": [],
            "count": 0,
            "message": f"Clinic is closed on {date} due to a scheduled holiday."
        }

    # 2. Check doctor leave
    cur.execute("SELECT leave_date FROM doctor_leaves WHERE doctor_id = ? AND leave_date = ?", (doc_id, date))
    if cur.fetchone():
        return {
            "success": True,
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "date": date,
            "day": day_of_week,
            "slots": [],
            "count": 0,
            "message": f"{doc_name} is on leave on {date}."
        }

    # 3. Check doctor working windows for this day of week
    cur.execute("SELECT start_time, end_time FROM doctor_windows WHERE doctor_id = ? AND day = ? ORDER BY start_time",
                (doc_id, day_of_week))
    windows = cur.fetchall()
    if not windows:
        return {
            "success": True,
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "date": date,
            "day": day_of_week,
            "slots": [],
            "count": 0,
            "message": f"{doc_name} has no scheduled clinic hours on {day_of_week} ({date})."
        }

    # 4. Generate all possible 15-minute slot starts within windows
    all_slots = []
    for win in windows:
        w_start = win["start_time"]
        w_end = win["end_time"]
        curr = w_start
        while curr < w_end:
            next_curr = _add_minutes(curr, 15)
            if next_curr <= w_end and curr not in all_slots:
                all_slots.append(curr)
            curr = next_curr

    # 5. Fetch booked appointments for doctor on date
    cur.execute(
        "SELECT start_time FROM appointments WHERE doctor_id = ? AND date = ? AND status = 'booked'",
        (doc_id, date)
    )
    booked_times = {row["start_time"] for row in cur.fetchall()}

    available_slots = [s for s in sorted(all_slots) if s not in booked_times]

    # 6. Apply window filter if requested (e.g. morning/subah, afternoon/dopahar, evening/shaam)
    if window:
        w_clean = window.strip().lower()
        if w_clean in ("morning", "subah"):
            available_slots = [s for s in available_slots if s < "12:00"]
        elif w_clean in ("afternoon", "dopahar"):
            available_slots = [s for s in available_slots if "12:00" <= s < "16:00"]
        elif w_clean in ("evening", "shaam"):
            available_slots = [s for s in available_slots if s >= "16:00"]

    return {
        "success": True,
        "doctor_id": doc_id,
        "doctor_name": doc_name,
        "date": date,
        "day": day_of_week,
        "slots": available_slots,
        "count": len(available_slots),
        "message": f"Found {len(available_slots)} available slot(s) for {doc_name} on {date}."
    }


def lookup_patient(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    phone: Optional[str] = None,
    dob: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search patients using broad LIKE matching across names, phone, and DOB.
    Returns all candidate matches without truncation.
    """
    cur = conn.cursor()
    conditions = []
    params = []

    if phone:
        clean_phone = phone.strip()
        conditions.append("phone = ?")
        params.append(clean_phone)

    if dob:
        conditions.append("dob = ?")
        params.append(dob.strip())

    if query:
        clean_query = query.strip()
        # Broad LIKE matching across full name
        conditions.append("LOWER(name) LIKE ?")
        params.append(f"%{clean_query.lower()}%")

    if not conditions:
        return {
            "success": False,
            "error": "Error: At least one search parameter (query/name, phone, or dob) must be provided.",
            "candidates": [],
            "count": 0
        }

    sql = f"SELECT id, name, phone, dob FROM patients WHERE {' AND '.join(conditions)} ORDER BY id"
    cur.execute(sql, params)
    rows = cur.fetchall()

    candidates = []
    for r in rows:
        p_dict = dict(r)
        # Fetch active appointments
        cur.execute(
            "SELECT id, doctor_id, date, start_time, end_time, status FROM appointments WHERE patient_id = ? AND status = 'booked' ORDER BY date, start_time",
            (p_dict["id"],)
        )
        p_dict["appointments"] = [dict(ap) for ap in cur.fetchall()]

        # Fetch guardianship
        cur.execute("SELECT ward_id FROM patient_guardians WHERE guardian_id = ?", (p_dict["id"],))
        p_dict["guardian_of"] = [g["ward_id"] for g in cur.fetchall()]

        candidates.append(p_dict)

    count = len(candidates)
    if count == 0:
        return {
            "success": False,
            "error": f"Error: No patient records found matching query='{query}', phone='{phone}', dob='{dob}'.",
            "candidates": [],
            "count": 0
        }
    elif count == 1:
        return {
            "success": True,
            "ambiguous": False,
            "count": 1,
            "patient": candidates[0],
            "candidates": candidates,
            "message": f"Found 1 matching patient: {candidates[0]['name']} (ID: {candidates[0]['id']})."
        }
    else:
        names_str = ", ".join([f"{c['name']} (ID: {c['id']}, Phone: {c['phone']})" for c in candidates])
        return {
            "success": True,
            "ambiguous": True,
            "count": count,
            "candidates": candidates,
            "message": f"Ambiguity detected: Found {count} matching patients: {names_str}. Disambiguation required using phone number or full name."
        }


def book_appointment(
    conn: sqlite3.Connection,
    patient_id: str,
    doctor_id: str,
    date: str,
    start: str
) -> Dict[str, Any]:
    """
    Creates an appointment in a free slot using atomic EXCLUSIVE locks to prevent race conditions.
    """
    if not patient_id or not doctor_id or not date or not start:
        return {
            "success": False,
            "error": "Error: Missing required arguments. patient_id, doctor_id, date, and start are all mandatory."
        }

    doc = _resolve_doctor_id(conn, doctor_id)
    if not doc:
        return {
            "success": False,
            "error": f"Error: Unknown doctor '{doctor_id}'."
        }
    doc_id = doc["id"]
    doc_name = doc["name"]

    # Normalize time
    try:
        start_formatted = _format_time(start)
        end_formatted = _add_minutes(start_formatted, 15)
    except Exception:
        return {
            "success": False,
            "error": f"Error: Invalid start time format '{start}'. Expected HH:MM."
        }

    cur = conn.cursor()

    try:
        # Atomic lock
        conn.execute("BEGIN EXCLUSIVE")

        # 1. Verify patient exists
        cur.execute("SELECT id, name FROM patients WHERE id = ?", (patient_id,))
        pt_row = cur.fetchone()
        if not pt_row:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Patient ID '{patient_id}' not found in clinic records."
            }
        patient_name = pt_row["name"]

        # 2. Check clinic holiday
        cur.execute("SELECT holiday_date FROM holidays WHERE holiday_date = ?", (date,))
        if cur.fetchone():
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Clinic is closed on {date} (holiday)."
            }

        # 3. Check doctor leave
        cur.execute("SELECT leave_date FROM doctor_leaves WHERE doctor_id = ? AND leave_date = ?", (doc_id, date))
        if cur.fetchone():
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: {doc_name} is on leave on {date}."
            }

        # 4. Check doctor working windows
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            day_of_week = dt.strftime("%a")
        except ValueError:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Invalid date format '{date}'."
            }

        cur.execute(
            "SELECT start_time, end_time FROM doctor_windows WHERE doctor_id = ? AND day = ?",
            (doc_id, day_of_week)
        )
        windows = cur.fetchall()
        in_window = any(win["start_time"] <= start_formatted and end_formatted <= win["end_time"] for win in windows)
        if not in_window:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Slot {start_formatted} on {day_of_week} ({date}) is outside {doc_name}'s scheduled clinic hours."
            }

        # 5. Check if slot is already booked (prevent race conditions)
        cur.execute(
            "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND start_time = ? AND status = 'booked'",
            (doc_id, date, start_formatted)
        )
        conflict = cur.fetchone()
        if conflict:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Slot {start_formatted} on {date} with {doc_name} is already booked (Appointment: {conflict['id']}). Please pick another slot."
            }

        # 6. Generate next appointment ID (e.g. ap_0026)
        cur.execute("SELECT id FROM appointments")
        all_ids = cur.fetchall()
        max_num = 0
        for row in all_ids:
            ap_id_str = row["id"]
            if ap_id_str.startswith("ap_"):
                try:
                    num = int(ap_id_str.split("_")[1])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        new_appointment_id = f"ap_{max_num + 1:04d}"

        # 7. Insert appointment
        cur.execute(
            "INSERT INTO appointments (id, patient_id, doctor_id, date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, ?, 'booked')",
            (new_appointment_id, patient_id, doc_id, date, start_formatted, end_formatted)
        )
        conn.execute("COMMIT")

        return {
            "success": True,
            "appointment_id": new_appointment_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "date": date,
            "start": start_formatted,
            "end": end_formatted,
            "status": "booked",
            "message": f"Appointment {new_appointment_id} successfully booked for {patient_name} with {doc_name} on {date} at {start_formatted}."
        }
    except Exception as e:
        conn.execute("ROLLBACK")
        return {
            "success": False,
            "error": f"Database Error during book_appointment: {str(e)}"
        }


def reschedule_appointment(
    conn: sqlite3.Connection,
    appointment_id: str,
    new_date: str,
    new_start: str
) -> Dict[str, Any]:
    """
    Reschedules an existing active appointment to a new slot using atomic EXCLUSIVE locks.
    """
    if not appointment_id or not new_date or not new_start:
        return {
            "success": False,
            "error": "Error: appointment_id, new_date, and new_start are all mandatory."
        }

    try:
        start_formatted = _format_time(new_start)
        end_formatted = _add_minutes(start_formatted, 15)
        dt = datetime.strptime(new_date, "%Y-%m-%d")
        day_of_week = dt.strftime("%a")
    except Exception as e:
        return {
            "success": False,
            "error": f"Error: Invalid date or time format ({new_date} {new_start}): {str(e)}"
        }

    cur = conn.cursor()

    try:
        conn.execute("BEGIN EXCLUSIVE")

        # 1. Fetch current appointment
        cur.execute(
            "SELECT id, patient_id, doctor_id, date, start_time, end_time, status FROM appointments WHERE id = ?",
            (appointment_id,)
        )
        ap_row = cur.fetchone()
        if not ap_row:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Appointment '{appointment_id}' not found."
            }
        if ap_row["status"] != "booked":
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Cannot reschedule appointment '{appointment_id}' with status '{ap_row['status']}'."
            }

        doc_id = ap_row["doctor_id"]
        patient_id = ap_row["patient_id"]
        old_date = ap_row["date"]
        old_start = ap_row["start_time"]

        # 2. Check holiday
        cur.execute("SELECT holiday_date FROM holidays WHERE holiday_date = ?", (new_date,))
        if cur.fetchone():
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Clinic is closed on {new_date} (holiday)."
            }

        # 3. Check leave
        cur.execute("SELECT leave_date FROM doctor_leaves WHERE doctor_id = ? AND leave_date = ?", (doc_id, new_date))
        if cur.fetchone():
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Doctor is on leave on {new_date}."
            }

        # 4. Check doctor working hours
        cur.execute(
            "SELECT start_time, end_time FROM doctor_windows WHERE doctor_id = ? AND day = ?",
            (doc_id, day_of_week)
        )
        windows = cur.fetchall()
        in_window = any(win["start_time"] <= start_formatted and end_formatted <= win["end_time"] for win in windows)
        if not in_window:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Slot {start_formatted} on {day_of_week} ({new_date}) is outside doctor's scheduled clinic hours."
            }

        # 5. Check slot conflict
        cur.execute(
            "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND start_time = ? AND status = 'booked' AND id != ?",
            (doc_id, new_date, start_formatted, appointment_id)
        )
        conflict = cur.fetchone()
        if conflict:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Slot {start_formatted} on {new_date} is already booked (Appointment: {conflict['id']})."
            }

        # 6. Update appointment
        cur.execute(
            "UPDATE appointments SET date = ?, start_time = ?, end_time = ? WHERE id = ?",
            (new_date, start_formatted, end_formatted, appointment_id)
        )
        conn.execute("COMMIT")

        return {
            "success": True,
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "doctor_id": doc_id,
            "old_date": old_date,
            "old_start": old_start,
            "new_date": new_date,
            "new_start": start_formatted,
            "new_end": end_formatted,
            "status": "rescheduled",
            "message": f"Appointment {appointment_id} successfully rescheduled from {old_date} {old_start} to {new_date} {start_formatted}."
        }
    except Exception as e:
        conn.execute("ROLLBACK")
        return {
            "success": False,
            "error": f"Database Error during reschedule_appointment: {str(e)}"
        }


def cancel_appointment(conn: sqlite3.Connection, appointment_id: str) -> Dict[str, Any]:
    """
    Cancels an existing appointment using atomic EXCLUSIVE locks.
    """
    if not appointment_id:
        return {
            "success": False,
            "error": "Error: appointment_id is required."
        }

    cur = conn.cursor()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        cur.execute("SELECT id, patient_id, doctor_id, date, start_time, status FROM appointments WHERE id = ?",
                    (appointment_id,))
        row = cur.fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return {
                "success": False,
                "error": f"Error: Appointment '{appointment_id}' not found."
            }

        if row["status"] == "cancelled":
            conn.execute("ROLLBACK")
            return {
                "success": True,
                "appointment_id": appointment_id,
                "patient_id": row["patient_id"],
                "doctor_id": row["doctor_id"],
                "status": "cancelled",
                "message": f"Appointment {appointment_id} was already cancelled."
            }

        cur.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,))
        conn.execute("COMMIT")

        return {
            "success": True,
            "appointment_id": appointment_id,
            "patient_id": row["patient_id"],
            "doctor_id": row["doctor_id"],
            "date": row["date"],
            "start": row["start_time"],
            "status": "cancelled",
            "message": f"Appointment {appointment_id} for patient {row['patient_id']} has been successfully cancelled."
        }
    except Exception as e:
        conn.execute("ROLLBACK")
        return {
            "success": False,
            "error": f"Database Error during cancel_appointment: {str(e)}"
        }


def escalate_to_human(
    conn: sqlite3.Connection,
    reason: str,
    detail: Optional[str] = None,
    conversation_id: Optional[str] = None,
    caller_said: Optional[str] = None
) -> Dict[str, Any]:
    """
    Escalates the call to clinic staff for human intervention.
    """
    reason_clean = reason.strip().lower() if reason else ""
    if reason_clean not in VALID_ESCALATION_REASONS:
        # Fallback mapping
        if "urgent" in reason_clean or "emergency" in reason_clean or "pain" in reason_clean or "symptom" in reason_clean:
            reason_clean = "clinical_urgent"
        elif "medical" in reason_clean or "advice" in reason_clean or "dose" in reason_clean or "crocin" in reason_clean or "medicine" in reason_clean:
            reason_clean = "medical_advice"
        elif "author" in reason_clean or "third" in reason_clean or "neighbor" in reason_clean:
            reason_clean = "not_authorised"
        elif "ambiguous" in reason_clean or "multiple" in reason_clean or "match" in reason_clean:
            reason_clean = "ambiguous_patient"
        else:
            reason_clean = "out_of_scope"

    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO handoffs (conversation_id, caller_said, reason, detail, status) VALUES (?, ?, ?, ?, 'open')",
            (conversation_id or "unknown", caller_said or "", reason_clean, detail or "")
        )
        conn.commit()
    except Exception:
        pass

    return {
        "success": True,
        "escalated": True,
        "reason": reason_clean,
        "detail": detail or "",
        "message": f"Call escalated to human staff. Escalation reason: {reason_clean}."
    }
