import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getHealth, listAgents } from '../api/agentApi';
import type { RegisteredAgent } from '../api/agentApi';
import './Pages.css';

function AgentMark({name}:{name:string}){return <div className="agent-mark">{(name||'A').slice(0,1).toUpperCase()}</div>}

export default function Dashboard(){
  const navigate=useNavigate();
  const [online,setOnline]=useState(false);
  const [agents,setAgents]=useState<RegisteredAgent[]>([]);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    getHealth().then(()=>setOnline(true)).catch(()=>setOnline(false));
    listAgents().then(setAgents).catch(()=>setAgents([])).finally(()=>setLoading(false));
  },[]);

  const active=agents.filter(a=>a.status==='active').length;

  return <div className="dashboard-page">
    <header className="dashboard-hero">
      <div>
        <div className="page-eyebrow">AGENTOS WORKSPACE</div>
        <h1>Good morning</h1>
        <p>Build, manage and execute intelligent agents from one workspace.</p>
      </div>
      <button className="hero-action" onClick={()=>navigate('/execute')}><span>▶</span> Open execution workspace</button>
    </header>

    <section className="dashboard-metrics">
      <div className="metric-card"><div className="metric-icon purple">✦</div><div><span>AI Layer</span><strong className={online?'green':'red'}>{online?'Online':'Offline'}</strong><small>FastAPI + Gemini service</small></div></div>
      <div className="metric-card"><div className="metric-icon blue">◈</div><div><span>Registered Agents</span><strong>{loading?'—':agents.length}</strong><small>{active} currently active</small></div></div>
      <div className="metric-card"><div className="metric-icon green">✓</div><div><span>Active Agents</span><strong>{loading?'—':active}</strong><small>Ready to execute</small></div></div>
      <div className="metric-card"><div className="metric-icon orange">◎</div><div><span>Default Model</span><strong className="model-value">Gemini</strong><small>gemini-3.5-flash-lite</small></div></div>
    </section>

    <section className="dashboard-section">
      <div className="section-head"><div><h2>Your agents</h2><p>Registered agents ready for execution.</p></div><button onClick={()=>navigate('/agents')}>View all <span>→</span></button></div>
      {agents.length===0&&!loading?<div className="dashboard-empty"><div>◈</div><strong>No agents registered</strong><span>Create your first agent to get started.</span><button onClick={()=>navigate('/create')}>Create agent</button></div>:<div className="dashboard-agent-list">
        {agents.slice(0,5).map(agent=><div className="dashboard-agent" key={agent.id}>
          <AgentMark name={agent.name}/>
          <div className="dashboard-agent-main"><strong>{agent.name}</strong><p>{agent.description||'AI agent configured for your workspace.'}</p><div className="capabilities">{agent.capabilities.slice(0,3).map(c=><span key={c}>{c}</span>)}</div></div>
          <div className="dashboard-agent-side"><span className={`status-pill ${agent.status==='active'?'active':'inactive'}`}><i/>{agent.status}</span><small>{agent.model?.model||'AI model'}</small></div>
          <button className="row-execute" disabled={agent.status!=='active'} onClick={()=>navigate('/execute')}>Execute</button>
        </div>)}
      </div>}
    </section>

    <section className="dashboard-bottom">
      <div className="info-card"><div className="info-icon">▣</div><div><strong>Knowledge-aware execution</strong><p>Connect agents to your document collections for retrieval-based answers.</p></div><button onClick={()=>navigate('/knowledge')}>Manage knowledge →</button></div>
      <div className="info-card"><div className="info-icon">◷</div><div><strong>Execution history</strong><p>Review previous prompts, outputs, latency and execution status.</p></div><button onClick={()=>navigate('/history')}>View history →</button></div>
    </section>
  </div>;
}
