import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import HandoffQueue from './components/HandoffQueue';
import ConversationDetail from './components/ConversationDetail';
import LiveRunner from './components/LiveRunner';

export default function App() {
  const [currentView, setCurrentView] = useState('handoffs');
  const [selectedConversationId, setSelectedConversationId] = useState('cv_4471');

  const handleSelectConversation = (id) => {
    setSelectedConversationId(id);
    setCurrentView('detail');
  };

  return (
    <div className="app-container">
      {/* Shared Sidebar */}
      <Sidebar currentView={currentView} setCurrentView={setCurrentView} />

      {/* Main Content Area */}
      <main className="main-content">
        {currentView === 'handoffs' && (
          <HandoffQueue onSelectConversation={handleSelectConversation} />
        )}

        {currentView === 'detail' && (
          <ConversationDetail
            conversationId={selectedConversationId}
            onBack={() => setCurrentView('handoffs')}
          />
        )}

        {currentView === 'runner' && (
          <LiveRunner onInspectConversation={handleSelectConversation} />
        )}

        {currentView === 'logs' && (
          <div className="card-panel">
            <h1 className="view-title">System & Ground-Truth Logs</h1>
            <p className="view-subtitle" style={{ marginBottom: '20px' }}>
              Deterministic SQLite Ground-Truth Logs and Contract Audits
            </p>
            <div style={{ backgroundColor: '#ffffff', padding: '16px', border: '1px solid #e2e8f0', borderRadius: '8px', fontFamily: 'JetBrains Mono', fontSize: '12px' }}>
              <div>[SYSTEM] SQLite DB engine active with BEGIN EXCLUSIVE atomic locking.</div>
              <div>[SYSTEM] Contract validator: schema.md loaded.</div>
              <div>[SYSTEM] Safety-First rule active: Immediate escalation on clinical keywords.</div>
              <div>[SYSTEM] Reference Date anchor: 2026-10-01 (Never system clock).</div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
