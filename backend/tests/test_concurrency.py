import threading
import sqlite3
import pytest
from backend.app.database import get_fresh_db_connection
from backend.app.tools import book_appointment


def test_concurrent_booking_race_condition():
    """
    Spawns multiple threads trying to book the exact same slot at the exact same instant.
    Asserts that exactly 1 booking succeeds and all other concurrent attempts fail gracefully with conflict errors.
    """
    # Create a shared in-memory connection with shared cache or a file-based temporary db
    import tempfile
    from pathlib import Path
    from backend.app.database import init_schema, seed_database, get_clinic_data

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_file = tmp.name

        # Initialize DB
        init_conn = sqlite3.connect(db_file)
        init_conn.row_factory = sqlite3.Row
        init_schema(init_conn)
        seed_database(init_conn, get_clinic_data())
        init_conn.close()

        results = []
        errors = []

        def attempt_booking(patient_id):
            conn = sqlite3.connect(db_file, timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                res = book_appointment(conn, patient_id=patient_id, doctor_id="dr_rao", date="2026-10-03", start="11:00")
                results.append(res)
            except Exception as e:
                errors.append(str(e))
            finally:
                conn.close()

        threads = []
        # 5 different patients attempting to book 2026-10-03 11:00 with dr_rao
        patient_ids = ["pt_0001", "pt_0002", "pt_0003", "pt_0004", "pt_0005"]
        for pid in patient_ids:
            t = threading.Thread(target=attempt_booking, args=(pid,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.get("success") is True]
        failures = [r for r in results if r.get("success") is False]

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert len(failures) == 4, f"Expected exactly 4 rejections, got {len(failures)}"
        for f in failures:
            assert "already booked" in f["error"].lower()
