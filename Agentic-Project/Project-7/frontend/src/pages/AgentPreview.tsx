import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { registerAgent } from '../api/agentApi';
import type { AgentSpec } from '../api/agentApi';
import './Pages.css';

type LocationState = {
  spec: AgentSpec;
  warnings: string[];
};

export default function AgentPreview() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState;
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (!state?.spec) {
    return (
      <div className="page">
        <div className="page-header">
          <h1 className="page-title">No agent draft</h1>
        </div>
        <div className="error-box">
          No agent specification found. Please create an agent first.
        </div>
        <button
          className="btn-primary"
          style={{ marginTop: '16px' }}
          onClick={() => navigate('/create')}
        >
          Create Agent
        </button>
      </div>
    );
  }

  const { spec, warnings } = state;

  const handleRegister = async () => {
    setRegistering(true);
    setError(null);
    try {
      await registerAgent(spec);
      setSuccess(true);
      setTimeout(() => navigate('/agents'), 1500);
    } catch (err: unknown) {
      if (
        err &&
        typeof err === 'object' &&
        'response' in err &&
        err.response &&
        typeof err.response === 'object' &&
        'data' in err.response
      ) {
        const data = (err.response as { data: { detail?: string } }).data;
        setError(data?.detail || 'Agent registration failed.');
      } else {
        setError('Agent registration failed.');
      }
    } finally {
      setRegistering(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Review Specification</h1>
        <p className="page-sub">Validate the configuration before registering it</p>
      </div>

      <div className="preview-box">
        <div className="preview-header">
          <div>
            <div className="preview-name">{spec.name}</div>
            <div className="preview-desc">{spec.description}</div>
          </div>
          <div className="preview-badge success">✓ Validated</div>
        </div>

        <div className="preview-grid">
          <div className="preview-section">
            <div className="preview-section-title">LLM Provider</div>
            <div className="preview-model">
              <div className="model-provider">{spec.model.provider}</div>
              <div className="model-name">{spec.model.model}</div>
            </div>
          </div>

          <div className="preview-section">
            <div className="preview-section-title">Capabilities</div>
            <div className="preview-capabilities">
              {spec.capabilities.map((cap, i) => (
                <div key={i} className="preview-capability">
                  <span className="check">✓</span> {cap}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="preview-section">
          <div className="preview-section-title">Input Schema</div>
          <div className="preview-schema">
            {Object.entries(spec.input_schema).map(([key, value]) => (
              <div key={key} className="schema-row">
                <span className="schema-key">{key}</span>
                <span className="schema-value">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="preview-section">
          <div className="preview-section-title">Output Schema</div>
          <div className="preview-schema">
            {Object.entries(spec.output_schema).map(([key, value]) => (
              <div key={key} className="schema-row">
                <span className="schema-key">{key}</span>
                <span className="schema-value">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="preview-section">
          <div className="preview-section-title">Knowledge Base</div>
          <div style={{ fontSize: '13px', color: spec.knowledge_base_id ? '#22c55e' : '#6b7280' }}>
            {spec.knowledge_base_id
              ? `✓ RAG enabled — knowledge base connected`
              : 'None — standard agent'}
          </div>
        </div>

        <div className="preview-section">
          <div className="preview-section-title">System Prompt</div>
          <div className="preview-prompt">{spec.system_prompt}</div>
        </div>

        {warnings.length > 0 && (
          <div className="warning-box">
            {warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}

        {error && <div className="error-box">{error}</div>}

        {success && (
          <div className="result-box">
            <div style={{ color: '#22c55e', fontSize: '15px' }}>
              ✓ Agent registered successfully! Redirecting...
            </div>
          </div>
        )}

        <div className="preview-actions">
          <button className="btn-secondary" onClick={() => navigate('/create')}>
            ← Back
          </button>
          <button
            className="btn-primary btn-large"
            onClick={handleRegister}
            disabled={registering || success}
          >
            {registering ? 'Registering...' : success ? '✓ Registered' : '✦ Register Agent'}
          </button>
        </div>
      </div>
    </div>
  );
}