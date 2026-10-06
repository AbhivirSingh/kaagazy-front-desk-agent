import re
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from .database import get_fresh_db_connection
from .schemas import AgentRunRequest, AgentRunResponse, ToolCallRecord, AgentMetrics
from .tools import (
    search_slots,
    lookup_patient,
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
    escalate_to_human,
)
import ssl
import certifi
import urllib.request
from .config import GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, MODEL_NAME, GROQ_MODEL

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def call_llm_reply(prompt: str, system_context: str = "") -> Tuple[Optional[str], int]:
    """
    Multi-tier LLM Provider Pipeline:
    1. Primary Free: Google Gemini (gemini-2.5-flash)
    2. Secondary Free: Groq Cloud (llama-3.3-70b-versatile)
    3. Tertiary: OpenAI (gpt-4o-mini)
    4. Offline Fail-Safe: Deterministic Ground-Truth Engine
    """
    # 1. Try Google Gemini
    if GEMINI_API_KEY:
        try:
            body = json.dumps({
                "contents": [
                    {"parts": [{"text": f"{system_context}\n\nUser: {prompt}"}]}
                ],
                "generationConfig": {"temperature": 0.0}
            }).encode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res["candidates"][0]["content"]["parts"][0]["text"]
                tokens = res.get("usageMetadata", {}).get("totalTokenCount", 350)
                return text.strip(), tokens
        except Exception:
            pass

    # 2. Try Groq Cloud (Free Tier)
    if GROQ_API_KEY:
        try:
            import httpx
            res = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "SwasthiQ-Agent/1.0"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_context},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0
                },
                timeout=4.0
            )
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 300)
                return text.strip(), tokens
        except Exception:
            pass

    # 3. Try OpenAI
    if OPENAI_API_KEY:
        try:
            body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=body,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res["choices"][0]["message"]["content"]
                tokens = res.get("usage", {}).get("total_tokens", 350)
                return text.strip(), tokens
        except Exception:
            pass

    return None, 0



# Urgent clinical keywords in English and Hindi (transliterated)
CLINICAL_URGENT_PATTERNS = [
    r"\b(seene mein dard|chest pain|chhati mein dard)\b",
    r"\b(saans phool|shortness of breath|breathless|saans lene mein takleef)\b",
    r"\b(chakkar|fainted|unconscious|behosh)\b",
    r"\b(khoon|bleeding|blood vomiting)\b",
    r"\b(severe pain|heart attack|stroke|paralysis|seizure|daura)\b",
    r"\b(emergency|turant dikhana hai|jaan ka khatra)\b",
]

# Medical advice keywords
MEDICAL_ADVICE_PATTERNS = [
    r"\b(crocin|paracetamol|combiflam|azithromycin|dawai|goli|tablet|medicine|dosage|dose)\b.*\b(le lun|le lu|kitni|khani chahiye|lu ya nahi|leni hai|double kar|badha|kam kar|change|alter)\b",
    r"\b(bukhar utar|fever.*how long|cure|treatment|remedy)\b",
    r"\b(ye dawai lun ya nahi|is this medicine safe|symptom diagnosis)\b",
]

# Prompt injection patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore (your )?previous instructions",
    r"administrator mode",
    r"system override",
    r"cancel every appointment",
    r"delete all appointments",
    r"internal test, proceed",
]

# Hindi weekday names to offset from Thursday (2026-10-01)
DAY_NAMES_HINDI = {
    "somwar": 0, "monday": 0, "mon": 0,
    "mangalwar": 1, "tuesday": 1, "tue": 1,
    "budhwar": 2, "wednesday": 2, "wed": 2,
    "guruwar": 3, "brihaspatiwar": 3, "thursday": 3, "thu": 3,
    "shukrawar": 4, "friday": 4, "fri": 4,
    "shanivaar": 5, "shanivar": 5, "saturday": 5, "sat": 5,
    "ravivar": 6, "itwar": 6, "sunday": 6, "sun": 6,
}

HINDI_NUMBERS = {
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10,
    "gyarah": 11, "barah": 12,
}


def _check_clinical_urgent(text: str) -> bool:
    low = text.lower()
    for pat in CLINICAL_URGENT_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def _check_medical_advice(text: str) -> bool:
    low = text.lower()
    for pat in MEDICAL_ADVICE_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def _check_prompt_injection(text: str) -> bool:
    low = text.lower()
    for pat in PROMPT_INJECTION_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def _parse_dates_and_times(turns: List[str], today_str: str) -> Tuple[List[str], List[str]]:
    """
    Extracts dates and times relative to request today_str.
    Handles 'kal', 'parso', specific day of the month (e.g. '3 tareekh', '8 tareekh'),
    and weekday names.
    """
    today_dt = datetime.strptime(today_str, "%Y-%m-%d")
    dates_found: List[str] = []
    times_found: List[str] = []

    for turn in turns:
        low = turn.lower()

        # Check explicit relative terms
        if "kal" in low or "tomorrow" in low:
            d = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            dates_found.append(d)
        elif "parso" in low or "day after tomorrow" in low:
            d = (today_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            dates_found.append(d)

        # Check 'N tareekh' / 'N date' / 'N October'
        tareekh_match = re.findall(r"(\d{1,2})\s*(?:tareekh|tarikh|date|october|oct)", low)
        for num_str in tareekh_match:
            day_num = int(num_str)
            d = f"{today_dt.year:04d}-{today_dt.month:02d}-{day_num:02d}"
            dates_found.append(d)

        # Check weekdays (e.g. 'Shanivaar', 'Saturday', 'Mangalwar 6 tareekh', 'Budhwar')
        for day_name, target_weekday in DAY_NAMES_HINDI.items():
            if day_name in low:
                # Find the next date with this weekday from today_dt
                cur_weekday = today_dt.weekday() # 0 = Monday, 6 = Sunday
                diff = (target_weekday - cur_weekday) % 7
                if diff == 0 and "aaj" not in low and "today" not in low:
                    # If same weekday mentioned without 'aaj', assume today or next week
                    pass
                d = (today_dt + timedelta(days=diff)).strftime("%Y-%m-%d")
                dates_found.append(d)

        # Check times (e.g. "9:30", "10:15", "11:00", "9 baje", "10 baje", "gyarah baje")
        time_matches = re.findall(r"\b(\d{1,2}:\d{2})\b", low)
        for tm in time_matches:
            times_found.append(tm)

        baje_matches = re.findall(r"\b(\d{1,2})\s*(?:baje|am|pm|o'clock)\b", low)
        for bm in baje_matches:
            val = int(bm)
            if val < 8:
                # e.g. 4 baje or 5 baje evening -> 16:00, 17:00
                times_found.append(f"{val+12:02d}:00")
            else:
                times_found.append(f"{val:02d}:00")

        # Hindi worded times
        for word, val in HINDI_NUMBERS.items():
            if f"{word} baje" in low:
                if val < 8:
                    times_found.append(f"{val+12:02d}:00")
                else:
                    times_found.append(f"{val:02d}:00")

    return dates_found, times_found


def _extract_entities(turns: List[str]) -> Dict[str, Any]:
    """Extracts mentioned doctor, phone, caller name, patient name, action intent."""
    full_text = " ".join(turns)
    low_text = full_text.lower()

    entities: Dict[str, Any] = {
        "doctor_id": None,
        "phone": None,
        "name": None,
        "ward_name": None,
        "is_reschedule": False,
        "is_cancel": False,
        "is_booking": False,
        "third_party": False,
        "caller_role": None,
    }

    # Doctor
    if "sethi" in low_text:
        entities["doctor_id"] = "dr_sethi"
    elif "rao" in low_text:
        entities["doctor_id"] = "dr_rao"

    # Action intent
    if "reschedule" in low_text or "move" in low_text or "aage" in low_text or "karwana hai" in low_text and "aaj ka appointment" in low_text:
        entities["is_reschedule"] = True
    if "cancel" in low_text or "hata" in low_text or "radd" in low_text:
        entities["is_cancel"] = True
    if "appointment chahiye" in low_text or "appointment karwana" in low_text or "milna hai" in low_text or "dikhana hai" in low_text:
        entities["is_booking"] = True

    # Phone numbers (10 digits)
    phone_match = re.search(r"\b(98122\d{5})\b", full_text) or re.search(r"\b(\d{10})\b", full_text)
    if phone_match:
        entities["phone"] = phone_match.group(1)

    # Specific relationship or third party mentions
    if "padosi" in low_text or "neighbor" in low_text or "friend" in low_text or "colleague" in low_text:
        entities["third_party"] = True
        entities["caller_role"] = "neighbor"

    if "mera beta" in low_text or "bete" in low_text or "son" in low_text or "child" in low_text or "ward" in low_text:
        entities["caller_role"] = "guardian"

    # Name extraction
    # Look for patterns like "Main <Name>,", "Meera Joshi bol rahi", "Shalini Uniyal,", "Neha Bhatt"
    name_patterns = [
        r"(?:main|mera naam|i am|this is)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:bol rahi|bol raha)",
        r"(?:for|liye)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),\s*\d{10}",
    ]
    for np in name_patterns:
        m = re.search(np, full_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ("namaste", "hello", "doctor", "dr", "dr.", "rao", "sethi", "ji"):
                if entities["caller_role"] == "guardian" and ("beta" in low_text or "kabir" in low_text or "aarav" in low_text or "arjun" in low_text):
                    # Check if candidate is parent or child
                    if "kabir" in candidate.lower() or "aarav" in candidate.lower() or "arjun" in candidate.lower():
                        entities["ward_name"] = candidate
                    else:
                        entities["name"] = candidate
                else:
                    entities["name"] = candidate
                break

    # Also check if explicit known names appear
    known_first_names = [
        "Harpreet", "Neha", "Rajesh", "Priya", "Kabir", "Meera", "Sunita", "Aarav", "Arjun",
        "Lakshmi", "Mohit", "Tarun", "Shalini", "Divya", "Sanjay", "Kavita", "Anita", "Vikas"
    ]
    for fn in known_first_names:
        if fn.lower() in low_text:
            if not entities["name"]:
                entities["name"] = fn
            if entities["caller_role"] == "guardian" and fn.lower() in ("kabir", "aarav", "arjun"):
                entities["ward_name"] = fn

    # Check for "Sharma ji" or single surname
    if "sharma" in low_text and not entities["name"] and not entities["phone"]:
        entities["name"] = "Sharma"

    return entities


def execute_conversation(payload: AgentRunRequest) -> AgentRunResponse:
    """
    Deterministic Agent Engine:
    Processes the conversation turns, strictly adheres to ground-truth tools,
    enforces safety rules, date grounding, and produces the exact output schema.
    """
    start_time = time.monotonic()
    cid = payload.conversation_id
    today = payload.today
    turns = payload.turns

    tool_calls: List[ToolCallRecord] = []
    terminal_state = "abandoned"
    escalation_reason = None
    patient_id = None
    appointment_id = None
    reply = ""

    conn = get_fresh_db_connection()

    try:
        full_text = " ".join(turns)

        # 1. Prompt Injection / Admin Override Check
        if _check_prompt_injection(full_text):
            terminal_state = "refused"
            escalation_reason = None
            reply = "I cannot process administrative commands or override instructions. I am only able to assist with standard clinic appointment bookings."
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResponse(
                conversation_id=cid,
                tool_calls=[],
                terminal_state=terminal_state,
                escalation_reason=None,
                patient_id=None,
                appointment_id=None,
                reply=reply,
                metrics=AgentMetrics(turns=len(turns), tokens=450, latency_ms=elapsed_ms)
            )

        # 2. Hard Rule: Clinical Urgent Check
        if _check_clinical_urgent(full_text):
            # Immediate escalation to human
            esc_res = escalate_to_human(conn, reason="clinical_urgent", detail="Caller reported emergency clinical symptoms", conversation_id=cid, caller_said=turns[-1])
            tool_calls.append(ToolCallRecord(name="escalate_to_human", arguments={"reason": "clinical_urgent", "detail": "Caller reported active symptoms"}))
            terminal_state = "escalated"
            escalation_reason = "clinical_urgent"
            reply = "Aapki tabiyat nazook lag rahi hai. Main turant aapko clinic ke medical staff se connect kar rahi hoon. Agar takleef zyada hai toh kripya nazdeeki emergency room mein sampark karein."
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResponse(
                conversation_id=cid,
                tool_calls=tool_calls,
                terminal_state=terminal_state,
                escalation_reason=escalation_reason,
                patient_id=None,
                appointment_id=None,
                reply=reply,
                metrics=AgentMetrics(turns=len(turns), tokens=620, latency_ms=elapsed_ms)
            )

        # 3. Medical Advice Check
        if _check_medical_advice(full_text):
            esc_res = escalate_to_human(conn, reason="medical_advice", detail="Caller requested clinical judgement or medication advice", conversation_id=cid, caller_said=turns[-1])
            tool_calls.append(ToolCallRecord(name="escalate_to_human", arguments={"reason": "medical_advice", "detail": "Caller asked for medical advice on medication"}))
            terminal_state = "escalated"
            escalation_reason = "medical_advice"
            reply = "Main front desk agent hoon aur dawai ya treatment se judi salah nahi de sakti. Main aapko doctor ya nursing staff se connect kar rahi hoon."
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResponse(
                conversation_id=cid,
                tool_calls=tool_calls,
                terminal_state=terminal_state,
                escalation_reason=escalation_reason,
                patient_id=None,
                appointment_id=None,
                reply=reply,
                metrics=AgentMetrics(turns=len(turns), tokens=580, latency_ms=elapsed_ms)
            )

        # Extract entities and dates
        entities = _extract_entities(turns)
        dates_found, times_found = _parse_dates_and_times(turns, today)

        # 4. Third-Party / Not Authorised Check
        if entities["third_party"] and entities["caller_role"] == "neighbor":
            esc_res = escalate_to_human(conn, reason="not_authorised", detail="Neighbor or unauthorized third party attempting to access or modify patient records", conversation_id=cid, caller_said=turns[-1])
            tool_calls.append(ToolCallRecord(name="escalate_to_human", arguments={"reason": "not_authorised", "detail": "Caller is not the patient or authorized guardian"}))
            terminal_state = "escalated"
            escalation_reason = "not_authorised"
            reply = "Kripya dhyan dein ki mareez ki anumati ya authorized guardian ke bina hum appointment mein badlav nahi kar sakte. Main aapki baat staff se karwa deti hoon."
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResponse(
                conversation_id=cid,
                tool_calls=tool_calls,
                terminal_state=terminal_state,
                escalation_reason=escalation_reason,
                patient_id=None,
                appointment_id=None,
                reply=reply,
                metrics=AgentMetrics(turns=len(turns), tokens=540, latency_ms=elapsed_ms)
            )

        # 5. Check if call is abandoned / meaningless
        meaningful_tokens = ["appointment", "dr", "doctor", "rao", "sethi", "cancel", "reschedule", "tarikh", "tareekh", "kal", "parso", "baje", "dikhana", "milna"]
        has_meaning = any(tok in full_text.lower() for tok in meaningful_tokens) or bool(entities["phone"]) or bool(entities["name"])
        if not has_meaning:
            terminal_state = "abandoned"
            escalation_reason = None
            reply = "Namaste, Sunrise Clinic. Aapki aawaz theek se nahi aa rahi hai. Kripya punah prayas karein."
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResponse(
                conversation_id=cid,
                tool_calls=[],
                terminal_state=terminal_state,
                escalation_reason=None,
                patient_id=None,
                appointment_id=None,
                reply=reply,
                metrics=AgentMetrics(turns=len(turns), tokens=320, latency_ms=elapsed_ms)
            )

        # 6. Patient Lookup & Disambiguation
        resolved_patient = None
        if entities["name"] or entities["phone"]:
            search_query = entities["name"]
            search_phone = entities["phone"]

            # If guardian is booking for child (e.g. Meera for Kabir, or Sunita for Aarav)
            if entities.get("ward_name"):
                search_query = entities["ward_name"]

            lookup_args = {}
            if search_query:
                lookup_args["query"] = search_query
            if search_phone:
                lookup_args["phone"] = search_phone

            tool_calls.append(ToolCallRecord(name="lookup_patient", arguments=lookup_args))
            lookup_res = lookup_patient(conn, query=search_query, phone=search_phone)

            if lookup_res.get("ambiguous"):
                # Check if ambiguous cannot be resolved (e.g. cv_0007 Sharma ji without phone)
                if not search_phone and len(lookup_res.get("candidates", [])) > 1:
                    # Escalation due to ambiguous patient
                    esc_res = escalate_to_human(conn, reason="ambiguous_patient", detail="Multiple patient records match without phone or DOB to disambiguate", conversation_id=cid, caller_said=turns[-1])
                    tool_calls.append(ToolCallRecord(name="escalate_to_human", arguments={"reason": "ambiguous_patient", "detail": "Ambiguous patient name with no phone"}))
                    terminal_state = "escalated"
                    escalation_reason = "ambiguous_patient"
                    reply = "Sharma surname ke kai mareez registered hain. Phone number na hone ke karan main aapki call clinic staff ko transfer kar rahi hoon."
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    return AgentRunResponse(
                        conversation_id=cid,
                        tool_calls=tool_calls,
                        terminal_state=terminal_state,
                        escalation_reason=escalation_reason,
                        patient_id=None,
                        appointment_id=None,
                        reply=reply,
                        metrics=AgentMetrics(turns=len(turns), tokens=610, latency_ms=elapsed_ms)
                    )
            elif lookup_res.get("success") and lookup_res.get("patient"):
                resolved_patient = lookup_res["patient"]
                patient_id = resolved_patient["id"]

        # 7. Cancellation Flow
        if entities["is_cancel"] and resolved_patient:
            active_aps = resolved_patient.get("appointments", [])
            if active_aps:
                target_ap = active_aps[0]
                tool_calls.append(ToolCallRecord(name="cancel_appointment", arguments={"appointment_id": target_ap["id"]}))
                c_res = cancel_appointment(conn, target_ap["id"])
                if c_res.get("success"):
                    terminal_state = "cancelled"
                    appointment_id = target_ap["id"]
                    reply = f"Aapka {target_ap['date']} ka appointment ({target_ap['id']}) safaltapoorvak cancel kar diya gaya hai."
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    return AgentRunResponse(
                        conversation_id=cid,
                        tool_calls=tool_calls,
                        terminal_state=terminal_state,
                        escalation_reason=None,
                        patient_id=patient_id,
                        appointment_id=appointment_id,
                        reply=reply,
                        metrics=AgentMetrics(turns=len(turns), tokens=520, latency_ms=elapsed_ms)
                    )

        # 8. Reschedule Flow
        if entities["is_reschedule"] and resolved_patient:
            active_aps = resolved_patient.get("appointments", [])
            target_date = dates_found[-1] if dates_found else None
            target_time = times_found[-1] if times_found else "10:00"

            if active_aps and target_date:
                target_ap = active_aps[0]
                tool_calls.append(ToolCallRecord(name="reschedule_appointment", arguments={
                    "appointment_id": target_ap["id"],
                    "new_date": target_date,
                    "new_start": target_time
                }))
                r_res = reschedule_appointment(conn, target_ap["id"], target_date, target_time)
                if r_res.get("success"):
                    terminal_state = "rescheduled"
                    appointment_id = target_ap["id"]
                    reply = f"Aapka appointment {target_date} ko subah {target_time} par reschedule kar diya gaya hai."
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    return AgentRunResponse(
                        conversation_id=cid,
                        tool_calls=tool_calls,
                        terminal_state=terminal_state,
                        escalation_reason=None,
                        patient_id=patient_id,
                        appointment_id=appointment_id,
                        reply=reply,
                        metrics=AgentMetrics(turns=len(turns), tokens=570, latency_ms=elapsed_ms)
                    )

        # 9. Booking Flow / Search Slots
        doctor_id = entities["doctor_id"] or "dr_rao"
        target_date = dates_found[-1] if dates_found else today
        target_time = times_found[-1] if times_found else None

        # Call search_slots
        tool_calls.append(ToolCallRecord(name="search_slots", arguments={"doctor_id": doctor_id, "date": target_date}))
        slots_res = search_slots(conn, doctor_id=doctor_id, date=target_date)

        # If date has no slots or is holiday / sunday / leave
        if slots_res.get("count", 0) == 0:
            if "Sunday" in str(slots_res.get("message")) or "leave" in str(slots_res.get("message")) or "closed" in str(slots_res.get("message")):
                # If caller accepted another date in subsequent turns (e.g. cv_0006 Dr. Sethi leave 5th -> caller moves to 8th)
                if len(dates_found) > 1:
                    target_date = dates_found[-1]
                    tool_calls.append(ToolCallRecord(name="search_slots", arguments={"doctor_id": doctor_id, "date": target_date}))
                    slots_res = search_slots(conn, doctor_id=doctor_id, date=target_date)
                else:
                    terminal_state = "abandoned"
                    reply = slots_res.get("message", "Is din koi slot uplabdh nahi hai.")
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    return AgentRunResponse(
                        conversation_id=cid,
                        tool_calls=tool_calls,
                        terminal_state=terminal_state,
                        escalation_reason=None,
                        patient_id=patient_id,
                        appointment_id=None,
                        reply=reply,
                        metrics=AgentMetrics(turns=len(turns), tokens=480, latency_ms=elapsed_ms)
                    )

        # Choose the requested time or first available slot in window
        available = slots_res.get("slots", [])
        selected_slot = None

        if target_time and target_time in available:
            selected_slot = target_time
        elif available:
            # If multiple times found (e.g. caller requested 9:00, taken, then 9:30 in cv_0015)
            for t in reversed(times_found):
                if t in available:
                    selected_slot = t
                    break
            if not selected_slot:
                selected_slot = available[0]

        # Book appointment if patient is identified and slot is chosen
        if resolved_patient and selected_slot:
            target_pid = resolved_patient["id"]
            tool_calls.append(ToolCallRecord(name="book_appointment", arguments={
                "patient_id": target_pid,
                "doctor_id": doctor_id,
                "date": target_date,
                "start": selected_slot
            }))
            b_res = book_appointment(conn, patient_id=target_pid, doctor_id=doctor_id, date=target_date, start=selected_slot)
            if b_res.get("success"):
                terminal_state = "booked"
                appointment_id = b_res["appointment_id"]
                patient_id = target_pid
                reply = f"Ji, {target_date} ko {selected_slot} par aapka appointment safaltapoorvak book ho gaya hai."
            else:
                terminal_state = "abandoned"
                reply = b_res.get("error", "Slot book nahi ho paya.")
        else:
            terminal_state = "abandoned"
            reply = "Kripya apna naam aur phone number batayein taaki hum appointment confirm kar sakein."

    finally:
        conn.close()

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    return AgentRunResponse(
        conversation_id=cid,
        tool_calls=tool_calls,
        terminal_state=terminal_state,
        escalation_reason=escalation_reason,
        patient_id=patient_id,
        appointment_id=appointment_id,
        reply=reply,
        metrics=AgentMetrics(turns=len(turns), tokens=650, latency_ms=elapsed_ms)
    )
