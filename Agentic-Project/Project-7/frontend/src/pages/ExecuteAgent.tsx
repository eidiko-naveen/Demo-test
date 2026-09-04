import { useEffect, useRef, useState } from 'react';
import {
  executeRegisteredAgent,
  listAgents,
  getKnowledgeBase,
  uploadKnowledgeDocument,
  listKnowledgeBases,
  createKnowledgeBase,
  updateAgent,
} from '../api/agentApi';

import type {
  RegisteredAgent,
  KnowledgeBase,
} from '../api/agentApi';

import './ExecuteAgent.css';

type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  latency?: number;
  status?: string;
};

type UploadedDoc = {
  filename: string;
  chunks: number;
};

/*
 * Browser-safe message ID generator.
 *
 * We do NOT use crypto.randomUUID() because the application
 * is being accessed through a local network IP such as:
 *
 * http://192.168.1.50:5173
 */
function createMessageId(): string {
  return `${Date.now()}-${Math.random()
    .toString(36)
    .substring(2, 12)}`;
}

const suggestions = [
  'Summarize the key points from the available knowledge.',
  'Explain this topic in simple terms.',
  'Analyze the request and give me a structured answer.',
];

function AgentGlyph({
  agent,
}: {
  agent: RegisteredAgent;
}) {
  return (
    <div className="agent-glyph">
      {(agent.name || 'A').slice(0, 1).toUpperCase()}
    </div>
  );
}

export default function ExecuteAgent() {
  const [agents, setAgents] = useState<RegisteredAgent[]>([]);
  const [selectedAgent, setSelectedAgent] =
    useState<RegisteredAgent | null>(null);

  const [agentPicker, setAgentPicker] = useState(false);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);

  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [showKb, setShowKb] = useState(false);

  const [knowledgeBases, setKnowledgeBases] =
    useState<KnowledgeBase[]>([]);

  const [selectedKbId, setSelectedKbId] = useState('');

  const [kbMode, setKbMode] =
    useState<'existing' | 'new'>('existing');

  const [newKbName, setNewKbName] = useState('');
  const [newKbDescription, setNewKbDescription] =
    useState('');

  const [linking, setLinking] = useState(false);

  const [uploadFile, setUploadFile] =
    useState<File | null>(null);

  const [uploading, setUploading] = useState(false);

  const [uploadedDocs, setUploadedDocs] =
    useState<UploadedDoc[]>([]);

  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  /*
   * Load registered agents.
   */
  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data);

        const activeAgent =
          data.find(
            (agent) => agent.status === 'active'
          ) ||
          data[0] ||
          null;

        setSelectedAgent(activeAgent);
      })
      .catch(() => {
        setError('Unable to load registered agents.');
      })
      .finally(() => {
        setFetching(false);
      });
  }, []);

  /*
   * Reset the conversation whenever the user
   * changes the selected agent.
   */
  useEffect(() => {
    setMessages([]);
    setError(null);
    setShowKb(false);
    setUploadedDocs([]);

    if (selectedAgent?.knowledge_base_id) {
      getKnowledgeBase(
        selectedAgent.knowledge_base_id
      )
        .then(setKb)
        .catch(() => setKb(null));
    } else {
      setKb(null);
    }
  }, [selectedAgent]);

  /*
   * Load knowledge bases when the knowledge
   * drawer is opened.
   */
  useEffect(() => {
    if (!showKb) {
      return;
    }

    listKnowledgeBases()
      .then(setKnowledgeBases)
      .catch(() => setKnowledgeBases([]));
  }, [showKb]);

  /*
   * Automatically scroll to the newest message.
   */
  useEffect(() => {
    endRef.current?.scrollIntoView({
      behavior: 'smooth',
    });
  }, [messages, loading]);

  /*
   * Select an agent from the agent picker.
   */
  const chooseAgent = (
    agent: RegisteredAgent
  ) => {
    setSelectedAgent(agent);
    setAgentPicker(false);
  };

  /*
   * Execute the selected agent.
   */
  const execute = async () => {
    if (
      !input.trim() ||
      !selectedAgent ||
      loading
    ) {
      return;
    }

    const text = input.trim();

    setInput('');
    setError(null);

    /*
     * Add user message.
     *
     * IMPORTANT:
     * createMessageId() replaces crypto.randomUUID()
     * because the application is accessed through a
     * local IP address.
     */
    setMessages((prev) => [
      ...prev,
      {
        id: createMessageId(),
        role: 'user',
        text,
      },
    ]);

    setLoading(true);

    try {
      const response =
        await executeRegisteredAgent(
          selectedAgent.id,
          text
        );

      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId(),
          role: 'assistant',
          text:
            response.output?.result ||
            response.error ||
            'The agent returned no output.',
          latency: response.latency_ms,
          status: response.status,
        },
      ]);
    } catch {
      setError(
        'Execution failed. Check that the backend service is running.'
      );

      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId(),
          role: 'assistant',
          text:
            'I could not complete this execution. Please verify the backend service and try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  /*
   * Submit message from the form.
   */
  const submit = (
    e: React.FormEvent
  ) => {
    e.preventDefault();
    execute();
  };

  /*
   * Link a knowledge base to the selected agent.
   */
  const linkKb = async () => {
    if (!selectedAgent) {
      return;
    }

    setLinking(true);
    setError(null);

    try {
      let id = selectedKbId;

      /*
       * Create a new knowledge base if required.
       */
      if (kbMode === 'new') {
        if (!newKbName.trim()) {
          setError(
            'Enter a knowledge base name.'
          );
          setLinking(false);
          return;
        }

        const created =
          await createKnowledgeBase(
            newKbName,
            newKbDescription
          );

        id = created.id;
      }

      if (!id) {
        setError(
          'Select a knowledge base.'
        );
        setLinking(false);
        return;
      }

      /*
       * Update the selected agent.
       */
      await updateAgent(
        selectedAgent.id,
        {
          knowledge_base_id: id,
        }
      );

      const updated = {
        ...selectedAgent,
        knowledge_base_id: id,
      };

      setSelectedAgent(updated);

      setAgents((currentAgents) =>
        currentAgents.map((agent) =>
          agent.id === updated.id
            ? updated
            : agent
        )
      );

      const linked =
        await getKnowledgeBase(id);

      setKb(linked);

      setSelectedKbId('');
      setNewKbName('');
      setNewKbDescription('');
    } catch {
      setError(
        'Could not update the knowledge base.'
      );
    } finally {
      setLinking(false);
    }
  };

  /*
   * Upload a document to the selected agent's
   * knowledge base.
   */
  const upload = async () => {
    if (
      !uploadFile ||
      !selectedAgent?.knowledge_base_id
    ) {
      return;
    }

    setUploading(true);

    try {
      const doc =
        await uploadKnowledgeDocument(
          selectedAgent.knowledge_base_id,
          uploadFile
        );

      if (doc.status === 'error') {
        setError(
          doc.error_message ||
            'Document upload failed.'
        );
      } else {
        setUploadedDocs((previous) => [
          {
            filename: doc.filename,
            chunks: doc.chunk_count,
          },
          ...previous,
        ]);

        setUploadFile(null);

        if (fileRef.current) {
          fileRef.current.value = '';
        }

        const refreshed =
          await getKnowledgeBase(
            selectedAgent.knowledge_base_id
          );

        setKb(refreshed);
      }
    } catch {
      setError(
        'Upload failed. Check the backend service.'
      );
    } finally {
      setUploading(false);
    }
  };

  /*
   * Loading state.
   */
  if (fetching) {
    return (
      <div className="execute-shell loading-screen">
        <div className="loader" />
        <span>
          Loading agents…
        </span>
      </div>
    );
  }

  /*
   * No agents available.
   */
  if (!selectedAgent) {
    return (
      <div className="execute-shell empty-execute">
        <div className="empty-icon">
          ✦
        </div>

        <h2>
          No agents available
        </h2>

        <p>
          Create and register an agent before
          opening the execution workspace.
        </p>
      </div>
    );
  }

  return (
    <div className="execute-shell">

      {/* ================================
          TOP BAR
          ================================ */}

      <header className="execute-topbar">

        <div className="execute-title">

          <div className="topbar-icon">
            ✦
          </div>

          <div>
            <h1>
              Execute Agent
            </h1>

            <span>
              Interactive agent workspace
            </span>
          </div>

        </div>

        <div className="topbar-actions">

          {/* Knowledge Base */}

          <button
            className="kb-button"
            onClick={() =>
              setShowKb(true)
            }
          >
            <span>
              ▣
            </span>

            {kb
              ? 'Knowledge connected'
              : 'Knowledge base'}

            {kb && <i />}
          </button>

          {/* Agent Selector */}

          <div className="agent-selector-wrap">

            <button
              className="selected-agent-button"
              onClick={() =>
                setAgentPicker(
                  (value) => !value
                )
              }
            >

              <AgentGlyph
                agent={selectedAgent}
              />

              <span>
                <small>
                  AGENT
                </small>

                <strong>
                  {selectedAgent.name}
                </strong>
              </span>

              <b>
                ⌄
              </b>

            </button>

            {agentPicker && (
              <>
                <div
                  className="picker-backdrop"
                  onClick={() =>
                    setAgentPicker(false)
                  }
                />

                <div className="agent-picker">

                  <div className="picker-head">

                    <div>
                      <strong>
                        Select an agent
                      </strong>

                      <span>
                        Choose which registered
                        agent should handle this chat.
                      </span>
                    </div>

                    <button
                      onClick={() =>
                        setAgentPicker(false)
                      }
                    >
                      ×
                    </button>

                  </div>

                  <div className="agent-options">

                    {agents.map((agent) => (
                      <button
                        key={agent.id}
                        className={`agent-option ${
                          selectedAgent.id ===
                          agent.id
                            ? 'chosen'
                            : ''
                        }`}
                        onClick={() =>
                          chooseAgent(agent)
                        }
                      >

                        <AgentGlyph
                          agent={agent}
                        />

                        <div>

                          <strong>
                            {agent.name}
                          </strong>

                          <span>
                            {agent.description ||
                              'Registered AI agent'}
                          </span>

                          <div className="option-meta">

                            <em
                              className={
                                agent.status ===
                                'active'
                                  ? 'live'
                                  : ''
                              }
                            >
                              {agent.status}
                            </em>

                            <label>
                              {agent.model?.model ||
                                'AI model'}
                            </label>

                          </div>

                        </div>

                        {selectedAgent.id ===
                          agent.id && (
                          <b>
                            ✓
                          </b>
                        )}

                      </button>
                    ))}

                  </div>

                </div>
              </>
            )}

          </div>

        </div>

      </header>

      {/* ================================
          CHAT AREA
          ================================ */}

      <main className="chat-area">

        {messages.length === 0 ? (

          <div className="welcome">

            <div className="welcome-avatar">
              <AgentGlyph
                agent={selectedAgent}
              />
            </div>

            <div className="welcome-eyebrow">
              READY TO EXECUTE
            </div>

            <h2>
              Chat with{' '}
              <span>
                {selectedAgent.name}
              </span>
            </h2>

            <p>
              {selectedAgent.description ||
                'Ask this agent anything and receive a response powered by your configured model.'}
            </p>

            <div className="suggestion-grid">

              {suggestions.map(
                (suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() =>
                      setInput(
                        suggestion
                      )
                    }
                  >
                    {suggestion}

                    <span>
                      ↗
                    </span>
                  </button>
                )
              )}

            </div>

          </div>

        ) : (

          <div className="conversation">

            {messages.map((message) => (

              <div
                key={message.id}
                className={`message-row ${message.role}`}
              >

                <div className="message-avatar">

                  {message.role === 'user'
                    ? 'You'
                    : (
                      <AgentGlyph
                        agent={selectedAgent}
                      />
                    )}

                </div>

                <div className="message-content">

                  <div className="message-author">
                    {message.role === 'user'
                      ? 'You'
                      : selectedAgent.name}
                  </div>

                  <div className="message-bubble">
                    {message.text}
                  </div>

                  {message.role ===
                    'assistant' &&
                    message.latency !==
                      undefined && (
                      <div className="message-meta">
                        {message.status ||
                          'completed'}
                        {' · '}
                        {message.latency}
                        {' ms'}
                      </div>
                    )}

                </div>

              </div>

            ))}

            {loading && (
              <div className="message-row assistant">

                <div className="message-avatar">
                  <AgentGlyph
                    agent={selectedAgent}
                  />
                </div>

                <div className="message-content">

                  <div className="message-author">
                    {selectedAgent.name}
                  </div>

                  <div className="thinking">
                    <i />
                    <i />
                    <i />
                  </div>

                </div>

              </div>
            )}

            <div ref={endRef} />

          </div>

        )}

        {error && (
          <div className="execution-error">

            {error}

            <button
              onClick={() =>
                setError(null)
              }
            >
              ×
            </button>

          </div>
        )}

      </main>

      {/* ================================
          CHAT COMPOSER
          ================================ */}

      <footer className="composer-area">

        <form
          className="composer"
          onSubmit={submit}
        >

          <textarea
            value={input}
            onChange={(event) =>
              setInput(event.target.value)
            }
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.shiftKey
              ) {
                event.preventDefault();
                execute();
              }
            }}
            placeholder={`Message ${selectedAgent.name}…`}
            rows={1}
          />

          <div className="composer-bottom">

            <div className="composer-hint">
              Enter to send · Shift + Enter
              for new line
            </div>

            <button
              type="submit"
              disabled={
                !input.trim() ||
                loading
              }
              className="send-button"
            >
              {loading ? (
                <span className="send-loader" />
              ) : (
                <span>
                  ↑
                </span>
              )}
            </button>

          </div>

        </form>

        <div className="composer-note">
          Agent responses may be generated
          from the selected model and connected
          knowledge base.
        </div>

      </footer>

      {/* ================================
          KNOWLEDGE BASE DRAWER
          ================================ */}

      {showKb && (
        <>
          <div
            className="drawer-backdrop"
            onClick={() =>
              setShowKb(false)
            }
          />

          <aside className="kb-drawer">

            <div className="drawer-header">

              <div>
                <span>
                  KNOWLEDGE
                </span>

                <h3>
                  {kb?.name ||
                    'Knowledge Base'}
                </h3>
              </div>

              <button
                onClick={() =>
                  setShowKb(false)
                }
              >
                ×
              </button>

            </div>

            {kb ? (

              <>
                <div className="kb-summary">

                  <div>
                    <strong>
                      {kb.document_count}
                    </strong>

                    <span>
                      documents
                    </span>
                  </div>

                  <div>
                    <strong>
                      {kb.status}
                    </strong>

                    <span>
                      status
                    </span>
                  </div>

                </div>

                <div className="upload-card">

                  <h4>
                    Add documents
                  </h4>

                  <p>
                    Upload source material for
                    this agent's retrieval workflow.
                  </p>

                  <input
                    ref={fileRef}
                    type="file"
                    onChange={(event) =>
                      setUploadFile(
                        event.target.files?.[0] ||
                          null
                      )
                    }
                  />

                  <button
                    onClick={upload}
                    disabled={
                      !uploadFile ||
                      uploading
                    }
                  >
                    {uploading
                      ? 'Uploading…'
                      : 'Upload document'}
                  </button>

                  {uploadedDocs.map(
                    (document) => (
                      <div
                        className="uploaded-doc"
                        key={document.filename}
                      >
                        ✓{' '}
                        {document.filename}

                        <span>
                          {document.chunks}
                          {' chunks'}
                        </span>
                      </div>
                    )
                  )}

                </div>

                <button
                  className="switch-kb"
                  onClick={() => {
                    setKb(null);
                    setSelectedKbId('');
                  }}
                >
                  Change knowledge base
                </button>

              </>

            ) : (

              <div className="kb-setup">

                <div className="setup-icon">
                  ▣
                </div>

                <h4>
                  Connect a knowledge base
                </h4>

                <p>
                  Attach an existing knowledge
                  base or create one for this agent.
                </p>

                <div className="mode-tabs">

                  <button
                    className={
                      kbMode === 'existing'
                        ? 'active'
                        : ''
                    }
                    onClick={() =>
                      setKbMode('existing')
                    }
                  >
                    Existing
                  </button>

                  <button
                    className={
                      kbMode === 'new'
                        ? 'active'
                        : ''
                    }
                    onClick={() =>
                      setKbMode('new')
                    }
                  >
                    Create new
                  </button>

                </div>

                {kbMode === 'existing' ? (

                  <select
                    value={selectedKbId}
                    onChange={(event) =>
                      setSelectedKbId(
                        event.target.value
                      )
                    }
                  >
                    <option value="">
                      Select knowledge base
                    </option>

                    {knowledgeBases.map(
                      (knowledgeBase) => (
                        <option
                          key={knowledgeBase.id}
                          value={
                            knowledgeBase.id
                          }
                        >
                          {knowledgeBase.name}
                        </option>
                      )
                    )}
                  </select>

                ) : (

                  <>
                    <input
                      placeholder="Knowledge base name"
                      value={newKbName}
                      onChange={(event) =>
                        setNewKbName(
                          event.target.value
                        )
                      }
                    />

                    <textarea
                      placeholder="Description (optional)"
                      value={
                        newKbDescription
                      }
                      onChange={(event) =>
                        setNewKbDescription(
                          event.target.value
                        )
                      }
                    />
                  </>

                )}

                <button
                  className="connect-button"
                  onClick={linkKb}
                  disabled={linking}
                >
                  {linking
                    ? 'Connecting…'
                    : 'Connect knowledge base'}
                </button>

              </div>

            )}

          </aside>
        </>
      )}

    </div>
  );
}