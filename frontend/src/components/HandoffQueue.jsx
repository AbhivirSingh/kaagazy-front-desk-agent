import React, { useState, useEffect } from 'react';

export default function HandoffQueue({ onSelectConversation }) {
  const [stats, setStats] = useState({
    total_conversations: 37,
    completed_by_agent: 31,
    completed_pct: 84,
    total_escalated: 6,
    open_escalations: 4,
    urgent_count: 1,
  });

  const [handoffs, setHandoffs] = useState([]);
  const [loading, setLoading] = useState(true);

  const [llmProviders, setLlmProviders] = useState([
    { id: 'gemini', name: 'Google Gemini', model: 'gemini-2.5-flash', tier: 'Primary', status: 'online' },
    { id: 'groq', name: 'Groq Cloud', model: 'qwen/qwen3.8-27b', tier: 'Secondary Fallback', status: 'online' },
  ]);

  const fetchStatsAndHandoffs = () => {
    Promise.all([
      fetch('/api/dashboard/stats').then((r) => r.json()),
      fetch('/api/handoffs').then((r) => r.json()),
      fetch('/api/llm/status').then((r) => r.json()).catch(() => null),
    ])
      .then(([statsData, handoffsData, llmData]) => {
        if (statsData) setStats(statsData);
        if (handoffsData) setHandoffs(handoffsData);
        if (llmData && llmData.providers) setLlmProviders(llmData.providers);
      })
      .catch((err) => {
        console.error('Failed to load dashboard data', err);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchStatsAndHandoffs();
  }, []);

  const handleResolve = async (id, reason) => {
    // Optimistic update
    setHandoffs((prev) =>
      prev.map((h) => (h.id === id ? { ...h, status: 'resolved' } : h))
    );

    setStats((prev) => {
      const isUrgent = reason === 'clinical_urgent' || reason === 'clinical';
      return {
        ...prev,
        open_escalations: Math.max(0, prev.open_escalations - 1),
        urgent_count: isUrgent ? Math.max(0, prev.urgent_count - 1) : prev.urgent_count,
      };
    });

    try {
      await fetch(`/api/handoffs/${id}/resolve`, { method: 'POST' });
      // Synchronize with server
      const updatedStats = await fetch('/api/dashboard/stats').then((r) => r.json());
      if (updatedStats) setStats(updatedStats);
    } catch (e) {
      console.error('Failed to resolve handoff', e);
    }
  };

  const getReasonBadge = (reason) => {
    switch (reason?.toLowerCase()) {
      case 'clinical_urgent':
      case 'clinical':
        return <span className="badge badge-clinical">CLINICAL</span>;
      case 'not_authorised':
      case 'not authorized':
        return <span className="badge badge-not-authorised">NOT AUTHORISED</span>;
      case 'ambiguous_patient':
      case 'ambiguous':
        return <span className="badge badge-ambiguous">AMBIGUOUS PATIENT</span>;
      case 'medical_advice':
        return <span className="badge badge-medical-advice">MEDICAL ADVICE</span>;
      default:
        return <span className="badge badge-scope">OUT OF SCOPE</span>;
    }
  };

  return (
    <div className="card-panel">
      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Handoff Queue</h1>
          <p className="view-subtitle">Sunrise Clinic, Dehradun — conversations the agent escalated</p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {llmProviders.map((p) => (
            <div
              key={p.id}
              className="badge"
              title={`${p.tier}: ${p.name} (${p.model}) - Latency: ${p.latency_ms || 300}ms`}
              style={{
                backgroundColor: p.status === 'online' ? '#f0fdf4' : '#fef2f2',
                borderColor: p.status === 'online' ? '#bbf7d0' : '#fecaca',
                color: p.status === 'online' ? '#15803d' : '#b91c1c',
                fontSize: '11px',
                fontFamily: 'JetBrains Mono',
                textTransform: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span style={{ fontSize: '8px' }}>●</span> {p.id === 'gemini' ? 'Gemini' : 'Groq'} ({p.model.split('/')[1] || p.model})
            </div>
          ))}
          <div className="badge badge-open">
            {stats.open_escalations} OPEN
          </div>
        </div>
      </div>

      {/* 4 Counter Cards across the top */}
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">Conversations</span>
          <span className="metric-value">{stats.total_conversations}</span>
          <span className="metric-footer">today</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Completed by Agent</span>
          <span className="metric-value">{stats.completed_by_agent}</span>
          <span className="metric-footer agent">{stats.completed_pct}%</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Escalated</span>
          <span className="metric-value">{stats.total_escalated}</span>
          <span className="metric-footer">{stats.open_escalations} still open</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Urgent</span>
          <span className="metric-value">{stats.urgent_count}</span>
          <span className="metric-footer urgent">clinical, unresolved</span>
        </div>
      </div>

      {/* Open Handoffs Table */}
      <div className="table-container">
        <h2 className="table-header-title">Open handoffs</h2>
        <table className="custom-table">
          <thead>
            <tr>
              <th>Conversation</th>
              <th>Caller Said</th>
              <th>Reason</th>
              <th>Time</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {handoffs.map((row) => {
              const isResolved = row.status === 'resolved';
              return (
                <tr key={row.id}>
                  <td>
                    <span
                      className="convo-link"
                      onClick={() => onSelectConversation(row.conversation_id)}
                    >
                      {row.conversation_id}
                    </span>
                  </td>
                  <td className="caller-quote">{row.caller_said}</td>
                  <td>{getReasonBadge(row.reason)}</td>
                  <td>{row.time || '11:42'}</td>
                  <td>
                    <button
                      className={`btn-resolve ${isResolved ? 'resolved' : ''}`}
                      onClick={() => !isResolved && handleResolve(row.id, row.reason)}
                      disabled={isResolved}
                    >
                      {isResolved ? 'Resolved' : 'Resolve'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
