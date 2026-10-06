from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

TerminalState = Literal[
    "booked",
    "rescheduled",
    "cancelled",
    "escalated",
    "refused",
    "abandoned",
]

EscalationReason = Literal[
    "clinical_urgent",
    "medical_advice",
    "not_authorised",
    "ambiguous_patient",
    "out_of_scope",
]


class AgentRunRequest(BaseModel):
    conversation_id: str
    today: str = "2026-10-01"
    turns: List[str]


class ToolCallRecord(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class AgentMetrics(BaseModel):
    turns: int = 0
    tokens: int = 0
    latency_ms: int = 0


class AgentRunResponse(BaseModel):
    conversation_id: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    terminal_state: TerminalState
    escalation_reason: Optional[EscalationReason] = None
    patient_id: Optional[str] = None
    appointment_id: Optional[str] = None
    reply: str
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)


class HandoffItem(BaseModel):
    id: int
    conversation_id: str
    caller_said: str
    reason: str
    detail: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class HandoffResolveRequest(BaseModel):
    handoff_id: int
    notes: Optional[str] = None
