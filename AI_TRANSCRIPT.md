# AI Coding Assistant Interaction Transcript

This file documents the engineering prompts, constraints, and instructions used during the development of the SwasthiQ Clinic Front Desk Agent.

---

### Prompt 1: Project Scaffolding & Requirements Analysis
```text
You are an expert full-stack AI engineer assisting me in building a robust, production-grade take-home assignment for an SDE Intern role at SwasthiQ. I have attached two files to this workspace: clinic.json, schema.md, and the conversations/ directory, as they dictate the exact data schema and expected deterministic output.

Project Objective:
Build a conversational front-desk agent for a synthetic solo clinic that handles booking, rescheduling, and cancelling appointments, while strictly knowing when to escalate calls to a human. The deliverable consists of a Python REST API backend and a React frontend matching two specific UI wireframes provided in the assignment PDF.

Core Constraints:
- Tech Stack: Python (FastAPI), React, and SQLite in-memory database.
- Tool Layer: Implement exactly six tools: search_slots, book_appointment, reschedule_appointment, cancel_appointment, lookup_patient, escalate_to_human.
- Concurrency & State: Slot cannot be double-booked; handle race conditions at the database transaction level.
- Zero Hallucination & Determinism: The agent must never invent a slot or appointment; identical inputs must produce identical terminal states.
- The Hard Rule: Immediate escalation on clinical symptoms.
- Ambiguity Handling: Broad patient lookups returning all candidate matches.
```

---

### Prompt 2: Phase 1 Database & Tool Layer Mechanics
```text
Proceed with scaffolding the backend/, frontend/, and adversarial/ directories, and generate the SQLite initialization script alongside the tool layer. As you write the backend code for Phase 1, ensure the following mechanics are hardcoded:

1. Atomic Transactions: Use strict SQLite transactional locks (BEGIN EXCLUSIVE) during book_appointment, reschedule_appointment, and cancel_appointment to eliminate double-booking race conditions.
2. LLM-Readable Exceptions: Return explicit, actionable string messages rather than generic 500 exceptions.
3. Broad Matching: Ensure lookup_patient utilizes a LIKE %...% query to catch partial names and returns all candidate matches.
```

---

### Prompt 3: Phase 2 Agent Orchestration, Phase 3 React UI, & Phase 4 Adversarial Testing
```text
Proceed with next steps:
- Build the conversational agent engine with date anchoring against request `today`, emergency clinical interceptors, and strict adherence to `schema.md`.
- Implement the React UI with the persistent sidebar, Screen 1 (Handoff Queue) with metric counters and resolve actions, and Screen 2 (Conversation Detail) with inline tool calls and outcome panels.
- Author 8 adversarial test scripts in adversarial/ that challenge naive agents with clinical pivots, unauthorized coworker bookings, ambiguous identities, and prompt injections.
- Document all choices in DECISIONS.md and provide a one-command setup in README.md.
```
