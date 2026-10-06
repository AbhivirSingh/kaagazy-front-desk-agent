import React, { useState, useEffect } from 'react';

export default function ConversationDetail({ conversationId = 'cv_4471', onBack }) {
  const [data, setData] = useState({
    id: conversationId,
    created_at: '27 Sep 2026, 11:42',
    clinic_name: 'Sunrise Clinic, Dehradun',
    turns: [
      {
        speaker: 'CALLER',
        text: 'Kal subah ka appointment mil jayega Dr. Rao ke saath?',
      },
      {
        speaker: 'TOOL',
        name: 'search_slots',
        arguments: { doctor_id: 'dr_rao', date: '2026-09-28', window: 'morning' },
        result: '3 slots: 09:30, 10:15, 11:00',
      },
      {
        speaker: 'AGENT',
        text: 'Ji, kal subah 9:30, 10:15 aur 11:00 khali hai. Kaun sa theek rahega?',
      },
      {
        speaker: 'CALLER',
        text: '10:15 kar dijiye. Waise abhi seene mein dard ho raha hai thoda.',
      },
      {
        speaker: 'TOOL',
        name: 'escalate_to_human',
        arguments: { reason: 'clinical_urgent', detail: 'caller reports active chest pain' },
        result: 'Handoff initiated',
      },
      {
        speaker: 'AGENT',
        text: 'Main abhi aapko clinic se connect kar rahi hoon. Agar dard badh raha hai, turant nazdeeki emergency par jaiye.',
      },
    ],
    outcome: {
      terminal_state: 'escalated',
      escalation_reason: 'clinical_urgent',
      patient_id: 'pt_0192',
      appointment_id: null,
      tool_calls: 2,
      turns: 6,
      tokens: 3140,
      latency_ms: 4200,
      determinism: 'STABLE',
      determinism_text: 'Same terminal state across 3 runs.',
    },
  });

  useEffect(() => {
    if (conversationId) {
      fetch(`/api/conversations/${conversationId}`)
        .then((res) => {
          if (!res.ok) throw new Error('Not found');
          return res.json();
        })
        .then((resData) => {
          setData(resData);
        })
        .catch(() => {
          // Keep wireframe default
        });
    }
  }, [conversationId]);

  const formatToolCallString = (name, args) => {
    const formattedArgs = Object.entries(args || {})
      .map(([k, v]) => `${k}="${v}"`)
      .join(', ');
    return `${name}(${formattedArgs})`;
  };

  const getStatusBadge = (state, reason) => {
    if (state === 'escalated') {
      const reasonLabel = reason?.replace('_', ' ').toUpperCase() || 'CLINICAL';
      return <span className="badge badge-clinical">ESCALATED — {reasonLabel}</span>;
    }
    if (state === 'booked') {
      return <span className="badge badge-booked">BOOKED</span>;
    }
    if (state === 'rescheduled') {
      return <span className="badge" style={{ backgroundColor: '#dbeafe', color: '#1d4ed8' }}>RESCHEDULED</span>;
    }
    if (state === 'cancelled') {
      return <span className="badge" style={{ backgroundColor: '#f4f4f5', color: '#52525b' }}>CANCELLED</span>;
    }
    if (state === 'refused') {
      return <span className="badge badge-scope">REFUSED</span>;
    }
    return <span className="badge badge-scope">ABANDONED</span>;
  };

  return (
    <div className="card-panel">
      {/* Header matching Wireframe */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Conversation {data.id}</h1>
          <p className="view-subtitle">
            {data.clinic_name || 'Sunrise Clinic, Dehradun'} — {data.created_at || '27 Sep 2026, 11:42'}
          </p>
        </div>
        <div>
          {getStatusBadge(data.outcome?.terminal_state, data.outcome?.escalation_reason)}
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="detail-grid">
        {/* Left: Transcript and tool calls */}
        <div className="transcript-panel">
          <h2 className="panel-title">Transcript and tool calls</h2>
          <div className="transcript-flow">
            {data.turns?.map((turn, index) => {
              if (turn.speaker === 'CALLER') {
                return (
                  <div className="turn-row" key={index}>
                    <span className="speaker-tag">CALLER</span>
                    <div className="caller-bubble">{turn.text}</div>
                  </div>
                );
              }
              if (turn.speaker === 'TOOL') {
                return (
                  <div className="turn-row" key={index}>
                    <span className="speaker-tag">TOOL</span>
                    <div className="tool-box">
                      <div className="tool-signature">
                        {formatToolCallString(turn.name, turn.arguments)}
                      </div>
                      {turn.result && (
                        <div className="tool-result">→ {turn.result}</div>
                      )}
                    </div>
                  </div>
                );
              }
              if (turn.speaker === 'AGENT') {
                return (
                  <div className="turn-row" key={index}>
                    <span className="speaker-tag">AGENT</span>
                    <div className="agent-bubble">{turn.text}</div>
                  </div>
                );
              }
              return null;
            })}
          </div>

          {/* Banner message at bottom */}
          {data.outcome?.terminal_state === 'escalated' && (
            <div className="alert-banner">
              Booking flow abandoned. No appointment was created.
            </div>
          )}
          {data.outcome?.terminal_state === 'booked' && (
            <div className="alert-banner success">
              Appointment {data.outcome.appointment_id || 'confirmed'} created in database.
            </div>
          )}
        </div>

        {/* Right: Outcome Panel */}
        <div className="outcome-panel">
          <h2 className="panel-title">Outcome</h2>
          <div className="outcome-list">
            <div className="outcome-row">
              <span className="outcome-label">terminal_state</span>
              <span className="outcome-val">{data.outcome?.terminal_state}</span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">escalation_reason</span>
              <span className="outcome-val">
                {data.outcome?.escalation_reason || 'null'}
              </span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">patient_id</span>
              <span className="outcome-val">{data.outcome?.patient_id || 'null'}</span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">appointment_id</span>
              <span className="outcome-val">{data.outcome?.appointment_id || 'null'}</span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">tool_calls</span>
              <span className="outcome-val">{data.outcome?.tool_calls ?? 0}</span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">turns</span>
              <span className="outcome-val">{data.outcome?.turns ?? 0}</span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">tokens</span>
              <span className="outcome-val">
                {data.outcome?.tokens ? Number(data.outcome.tokens).toLocaleString() : '0'}
              </span>
            </div>
            <div className="outcome-row">
              <span className="outcome-label">latency</span>
              <span className="outcome-val">
                {(Number(data.outcome?.latency_ms || 1000) / 1000).toFixed(1)} s
              </span>
            </div>
          </div>

          {/* Determinism */}
          <div className="determinism-box">
            <div className="determinism-label">Determinism</div>
            <div className="determinism-row">
              <span>{data.outcome?.determinism_text || 'Same terminal state across 3 runs.'}</span>
              <span className="badge badge-stable">
                {data.outcome?.determinism || 'STABLE'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
