import './Pages.css';

export default function Tools() {
  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Tool Registry</h1>
        <p className="page-sub">Built-in and custom tools available to agents</p>
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
        <div style={{ fontSize: '48px' }}>⚙</div>
        <div style={{ fontSize: '20px', fontWeight: 600, color: '#fff' }}>
          Coming Soon
        </div>
        <div style={{ fontSize: '14px', color: '#6b7280', maxWidth: '400px' }}>
          Tool Registry has been temporarily removed from the backend
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
          <strong style={{ color: '#6c63ff' }}>Planned tools:</strong>
          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div>⚙ calculator</div>
            <div>⚙ web_search</div>
            <div>⚙ gmail_search</div>
            <div>⚙ google_drive_search</div>
            <div>⚙ calendar_search</div>
            <div>⚙ document_search</div>
          </div>
        </div>
      </div>
    </div>
  );
}