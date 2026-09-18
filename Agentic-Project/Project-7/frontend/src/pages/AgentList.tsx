import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listAgents, deleteAgent, toggleAgentStatus } from '../api/agentApi';
import type { RegisteredAgent } from '../api/agentApi';
import './Pages.css';

function AgentMark({name}:{name:string}){return <div className="agent-mark">{(name||'A').slice(0,1).toUpperCase()}</div>}

export default function AgentList(){
  const navigate=useNavigate();
  const [agents,setAgents]=useState<RegisteredAgent[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState<string|null>(null);

  const load=()=>{setLoading(true);listAgents().then(setAgents).catch(()=>setError('Unable to load agents.')).finally(()=>setLoading(false));};
  useEffect(()=>{load();},[]);

  const toggle=async(agent:RegisteredAgent)=>{setBusy(agent.id);setError(null);try{const updated=await toggleAgentStatus(agent.id,agent.status==='active'?'inactive':'active');setAgents(prev=>prev.map(a=>a.id===updated.id?updated:a));}catch{setError('Failed to update agent status.');}finally{setBusy(null);}};
  const remove=async(id:string)=>{if(!confirm('Delete this agent? This action cannot be undone.'))return;setBusy(id);try{await deleteAgent(id);setAgents(prev=>prev.filter(a=>a.id!==id));}catch{setError('Failed to delete agent.');}finally{setBusy(null);}};

  return <div className="agents-page">
    <header className="list-header"><div><div className="page-eyebrow">AGENT REGISTRY</div><h1>Agents</h1><p>Manage the intelligent agents registered on your platform.</p></div><button className="primary-button" onClick={()=>navigate('/create')}><span>+</span> Create Agent</button></header>
    <div className="list-summary"><div><strong>{agents.length}</strong><span>Total agents</span></div><div><strong>{agents.filter(a=>a.status==='active').length}</strong><span>Active</span></div><div><strong>{agents.filter(a=>a.is_rag).length}</strong><span>Knowledge aware</span></div></div>
    {error&&<div className="page-alert danger">{error}</div>}
    {loading?<div className="page-loading"><div className="spinner"/>Loading agents...</div>:agents.length===0?<div className="page-empty"><div>◈</div><h2>No agents yet</h2><p>Create an agent and it will appear here after registration.</p><button className="primary-button" onClick={()=>navigate('/create')}>Create your first agent</button></div>:<div className="agent-registry">
      {agents.map(agent=><article className="registry-card" key={agent.id}>
        <AgentMark name={agent.name}/>
        <div className="registry-main"><div className="registry-title"><h2>{agent.name}</h2><span className={`status-pill ${agent.status==='active'?'active':'inactive'}`}><i/>{agent.status}</span></div><p>{agent.description||'No description provided.'}</p><div className="registry-tags">{agent.capabilities.map(c=><span key={c}>{c}</span>)}</div></div>
        <div className="registry-model"><small>MODEL</small><strong>{agent.model?.model||'—'}</strong><span>{agent.model?.provider||'—'}</span></div>
        <div className="registry-actions"><button className="row-execute" disabled={agent.status!=='active'} onClick={()=>navigate('/execute')}>Execute</button><button className="secondary-button" disabled={busy===agent.id} onClick={()=>toggle(agent)}>{busy===agent.id?'...':agent.status==='active'?'Disable':'Enable'}</button><button className="icon-danger" disabled={busy===agent.id} onClick={()=>remove(agent.id)}>Delete</button></div>
      </article>)}
    </div>}
  </div>;
}
