import './Pages.css';

export default function AgentConnections() {
  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Agent Connections</h1>
        <p className="page-sub">Configure controlled delegation between registered agents</p>
      </div>

      <div style={{
        background: '#13161f',
        border: '1px solid #1e2130',
        borderRadius: '12px',
        padding: '48px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '16px',
      }}>
        <div style={{ fontSize: '48px' }}>⟶</div>
        <div style={{ fontSize: '20px', fontWeight: 600, color: '#fff' }}>
          Coming Soon
        </div>
        <div style={{ fontSize: '14px', color: '#6b7280', maxWidth: '400px' }}>
          Agent-to-agent connections have been temporarily removed from the backend
          and will be re-added in the next phase.
        </div>
        <div style={{
          background: '#0f1117',
          border: '1px solid #1e2130',
          borderRadius: '8px',
          padding: '16px 24px',
          fontSize: '13px',
          color: '#6b7280',
          marginTop: '8px',
        }}>
          <strong style={{ color: '#6c63ff' }}>Planned features:</strong>
          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div>⟶ Source agent delegates to target agent</div>
            <div>⟶ Multi-agent orchestration</div>
            <div>⟶ Sequential and parallel execution</div>
            <div>⟶ Result synthesis across agents</div>
          </div>
        </div>
      </div>
    </div>
  );
}