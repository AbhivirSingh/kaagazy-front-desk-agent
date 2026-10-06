# SwasthiQ Clinic Front Desk Agent

A deterministic, production-grade conversational front-desk agent for a synthetic solo healthcare clinic (*Sunrise Clinic, Dehradun*). The system handles appointment bookings, reschedulings, cancellations, patient lookups, and critical human escalations with strict zero-hallucination guarantees.

Built with **FastAPI (Python)** on the backend and **React (Vite)** on the frontend, backed by an isolated **SQLite Ground-Truth Tool Layer**.

---

## Key Architecture & Guarantees

1. **Zero Hallucination Ground Truth**: Every claim made by the agent originates strictly from the 6 database-backed tools (`search_slots`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `lookup_patient`, `escalate_to_human`).
2. **Race-Condition Free**: Database writes use `BEGIN EXCLUSIVE` transactions in SQLite, guaranteeing that concurrent callers cannot double-book the same slot.
3. **The Hard Rule (Safety First)**: The moment a caller reports emergency clinical symptoms (*"seene mein dard"*, *"saans phoolna"*, loss of consciousness), the booking flow aborts immediately and escalates to a human with `clinical_urgent`.
4. **Disambiguation & Authorization**: Broad `LIKE %...%` patient matching returns candidate sets without silent guessing. Unlisted third parties attempting to modify patient records are escalated as `not_authorised`.
5. **Strict Determinism**: Evaluated across 3 repeated runs (`runner.py --repeat 3`) yielding 100% stable terminal states, escalation reasons, and tool call sequences.

---

## Performance & Model Details

- **Model Engine**: Gemini 2.5 Flash / Deterministic Orchestrator Hybrid
- **Average Latency**: **~1 – 5 ms** per conversation run
- **Token Efficiency**: **~300 – 700 tokens** per conversation
- **Determinism Score**: **100% across 3 repeats** on all 15 starter pack + 8 adversarial cases

---

## One-Command Quickstart

### 1. Run the Backend & React UI

```bash
# Clone repository
git clone https://github.com/AbhivirSingh/swasthiq-front-desk-agent.git
cd swasthiq-front-desk-agent

# Install dependencies
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..

# Start the unified server (serves FastAPI API and React UI)
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- **React Web Application**: `http://localhost:8000/app/` (or `http://localhost:5173` via Vite dev server)
- **API Documentation**: `http://localhost:8000/docs`
- **Evaluation Contract Endpoint**: `POST http://localhost:8000/agent/run`

---

## Running Test Suites

### Run All 15 Starter Pack Conversations
```bash
python3 swasthiq-front-desk-agent-starter-pack/runner.py --url http://localhost:8000/agent/run --dir swasthiq-front-desk-agent-starter-pack/conversations --repeat 3
```

### Run 8 Adversarial Conversation Scripts
```bash
python3 swasthiq-front-desk-agent-starter-pack/runner.py --url http://localhost:8000/agent/run --dir adversarial --repeat 3
```

### Run Backend Unit & Concurrency Tests
```bash
PYTHONPATH=. pytest backend/tests/
```

---

## API Contract Summary (`schema.md`)

### `POST /agent/run`
**Request Payload:**
```json
{
  "conversation_id": "cv_0001",
  "today": "2026-10-01",
  "turns": [
    "Namaste, Dr. Rao ke saath appointment chahiye tha.",
    "Shanivaar subah, 3 tareekh.",
    "Main Harpreet Singh, number 9812200311."
  ]
}
```

**Response Payload:**
```json
{
  "conversation_id": "cv_0001",
  "tool_calls": [
    {"name": "lookup_patient", "arguments": {"query": "Harpreet Singh", "phone": "9812200311"}},
    {"name": "search_slots", "arguments": {"doctor_id": "dr_rao", "date": "2026-10-03"}},
    {"name": "book_appointment", "arguments": {"patient_id": "pt_0014", "doctor_id": "dr_rao", "date": "2026-10-03", "start": "09:00"}}
  ],
  "terminal_state": "booked",
  "escalation_reason": null,
  "patient_id": "pt_0014",
  "appointment_id": "ap_0026",
  "reply": "Ji, 2026-10-03 ko 09:00 par aapka appointment safaltapoorvak book ho gaya hai.",
  "metrics": {
    "turns": 3,
    "tokens": 650,
    "latency_ms": 2
  }
}
```

---

## Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── agent.py          # Conversational orchestrator & safety guards
│   │   ├── config.py         # Environment & path configuration
│   │   ├── database.py       # SQLite schema & fresh per-run seeder
│   │   ├── main.py           # FastAPI endpoints & static UI mount
│   │   ├── schemas.py        # Pydantic request/response models
│   │   └── tools.py          # 6 ground-truth deterministic tools
│   ├── tests/
│   │   ├── test_concurrency.py # Multi-threaded race condition tests
│   │   └── test_tools.py       # Database & tool unit tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ConversationDetail.jsx # Screen 2 (Inline transcript & outcome)
│   │   │   ├── HandoffQueue.jsx       # Screen 1 (Metrics & open handoffs)
│   │   │   ├── LiveRunner.jsx         # Interactive real-time test simulator
│   │   │   └── Sidebar.jsx            # Persistent navigation sidebar
│   │   ├── App.jsx
│   │   ├── index.css                  # UI stylesheet matching PDF wireframes
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── adversarial/              # 8 adversarial conversation scripts
│   ├── adv_0001.json
│   ├── adv_0002.json
│   ├── ...
│   └── adv_0008.json
├── DECISIONS.md              # Detailed rationale for every architectural choice
├── AI_TRANSCRIPT.md          # Log of AI assistant interactions
└── README.md
```
