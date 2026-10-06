import React from 'react';

export default function Sidebar({ currentView, setCurrentView }) {
  const navItems = [
    { id: 'handoffs', label: 'Handoff Queue' },
    { id: 'detail', label: 'Conversation Detail' },
    { id: 'runner', label: 'Live Runner & Test Suite' },
    { id: 'logs', label: 'System Logs' },
  ];

  return (
    <aside className="sidebar">
      {navItems.map((item) => (
        <button
          key={item.id}
          className={`nav-item ${currentView === item.id ? 'active' : ''}`}
          onClick={() => setCurrentView(item.id)}
          title={item.label}
          aria-label={item.label}
        >
          <div className="nav-circle" />
        </button>
      ))}
    </aside>
  );
}
