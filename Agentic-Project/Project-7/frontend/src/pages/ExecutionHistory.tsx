import { useEffect, useMemo, useState } from 'react';
import { getExecutions } from '../api/agentApi';
import type { ExecutionRecord } from '../api/agentApi';
import './Pages.css';

export default function ExecutionHistory(){
 const [items,setItems]=useState<ExecutionRecord[]>([]); const [loading,setLoading]=useState(true); const [error,setError]=useState<string|null>(null); const [search,setSearch]=useState(''); const [open,setOpen]=useState<string|null>(null);
 useEffect(()=>{getExecutions().then(setItems).catch(()=>setError('Could not load execution history.')).finally(()=>setLoading(false));},[]);
 const filtered=useMemo(()=>{const q=search.trim().toLowerCase();if(!q)return items;return items.filter(x=>[x.input_payload,x.output_payload||'',x.error_message||'',x.status,x.agent_id].join(' ').toLowerCase().includes(q));},[items,search]);
 const success=items.filter(x=>x.status?.toLowerCase()==='success').length; const failed=items.filter(x=>['failed','timeout'].includes(x.status?.toLowerCase())).length; const avg=items.length?items.reduce((a,x)=>a+(x.latency_ms||0),0)/items.length:0;
 const output=(x:ExecutionRecord)=>{if(!x.output_payload)return x.error_message||'No output recorded.';try{const p=JSON.parse(x.output_payload);return typeof p?.result==='string'?p.result:JSON.stringify(p,null,2);}catch{return x.output_payload;}};
 const date=(x:string)=>{const d=new Date(x);return Number.isNaN(d.getTime())?x:d.toLocaleString([],{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});};
 return <div className="history-page">
  <header className="page-hero"><div><div className="page-eyebrow">PLATFORM ACTIVITY</div><h1>Execution History</h1><p>Review prompts, outputs, latency and status for previous agent runs.</p></div><div className="live-badge"><i/> Live records</div></header>
  <div className="history-stats"><div><span>Executions</span><strong>{items.length}</strong><small>All recorded runs</small></div><div><span>Successful</span><strong>{success}</strong><small>Completed successfully</small></div><div><span>Failed</span><strong>{failed}</strong><small>Failed or timed out</small></div><div><span>Avg. latency</span><strong>{avg?`${avg.toFixed(0)} ms`:'—'}</strong><small>Across all executions</small></div></div>
  <section className="history-panel"><div className="panel-toolbar"><div><h2>Recent executions</h2><span>{filtered.length} records</span></div><div className="search-field"><span>⌕</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search executions..."/>{search&&<button onClick={()=>setSearch('')}>×</button>}</div></div>
   {loading?<div className="page-loading"><div className="spinner"/>Loading execution history...</div>:error?<div className="page-alert danger">{error}</div>:filtered.length===0?<div className="page-empty compact"><div>◷</div><h2>{items.length?'No matching executions':'No executions yet'}</h2><p>{items.length?'Try a different search term.':'Execute an agent from the execution workspace to create a record.'}</p></div>:<div className="history-list">{filtered.map(x=>{const status=x.status?.toLowerCase()||'unknown';const ok=status==='success';const expanded=open===x.id;return <article className={`history-item ${expanded?'expanded':''}`} key={x.id}>
    <div className="history-item-head"><div className="history-id"><div className="history-avatar">AI</div><div><strong>Agent execution</strong><span>{x.id.slice(0,10)}...</span></div></div><div className="history-meta"><span className={`status-pill ${ok?'active':status==='timeout'?'warning':'danger'}`}><i/>{status}</span><span>{x.latency_ms?.toFixed(0)} ms</span><span>{date(x.start_time)}</span></div></div>
    <div className="history-columns"><div><label>INPUT</label><div className="payload input">{x.input_payload||'—'}</div></div><div><label>{ok?'OUTPUT':'ERROR'}</label><div className={`payload ${ok?'output':'error'} ${expanded?'full':''}`}>{output(x)}</div></div></div>
    <div className="history-item-foot"><span>Agent <code>{x.agent_id.slice(0,12)}...</code></span><button onClick={()=>setOpen(expanded?null:x.id)}>{expanded?'Collapse':'View full result'} <b>{expanded?'↑':'↓'}</b></button></div>
   </article>})}</div>}
  </section>
 </div>;
}
