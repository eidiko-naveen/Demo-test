import { useState,useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { buildAgent } from '../api/agentApi';
import axios from 'axios';
import './Pages.css';

const AI_LAYER_URL='http://192.168.1.50:8000';
const examples=['Analyze customer reviews and identify common complaints','Answer questions about SQL databases and optimize queries','Summarize long documents into concise executive key points'];
type ProviderModel={id:string;label:string};
type Providers=Record<string,{label:string;models:ProviderModel[]}>;

export default function CreateAgent(){
 const navigate=useNavigate(); const [prompt,setPrompt]=useState(''); const [loading,setLoading]=useState(false); const [error,setError]=useState<string|null>(null); const [providers,setProviders]=useState<Providers>({}); const [provider,setProvider]=useState('gemini'); const [model,setModel]=useState('gemini-3.5-flash-lite');
 useEffect(()=>{axios.get(`${AI_LAYER_URL}/api/providers`).then(r=>setProviders(r.data)).catch(()=>{});},[]);
 const changeProvider=(p:string)=>{setProvider(p);if(providers[p]?.models?.length)setModel(providers[p].models[0].id);};
 const build=async()=>{if(prompt.trim().length<10||loading)return;setLoading(true);setError(null);try{const response=await buildAgent(prompt,provider,model);navigate('/preview',{state:{spec:{...response.spec,model:{provider,model}},warnings:response.warnings}});}catch(err:unknown){if(axios.isAxiosError(err))setError(typeof err.response?.data?.detail==='string'?err.response.data.detail:'Failed to build agent. Please try again.');else if(err instanceof Error)setError(err.message);else setError('Failed to build agent. Please try again.');}finally{setLoading(false);}};
 return <div className="create-page">
  <header className="create-header"><div><div className="page-eyebrow">AGENT BUILDER</div><h1>Create an agent</h1><p>Describe the outcome you need. The AI builder will generate the agent specification.</p></div><div className="builder-badge"><span>✦</span> AI-assisted configuration</div></header>
  <div className="builder-layout">
   <section className="builder-card main-builder"><div className="builder-card-head"><div className="step-number">01</div><div><h2>Describe your agent</h2><p>Write what the agent should do in natural language.</p></div></div>
    <textarea className="builder-prompt" rows={8} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Example: Create an agent that analyzes customer reviews, identifies recurring complaints, detects sentiment, and produces a concise management report..."/>
    <div className="prompt-meta"><span>{prompt.length} characters</span><span>Be specific about the task and expected output</span></div>
    <div className="examples"><div className="examples-head"><strong>Try an example</strong><span>Click to use</span></div><div className="example-cards">{examples.map(x=><button key={x} onClick={()=>setPrompt(x)}>{x}<span>↗</span></button>)}</div></div>
   </section>
   <aside className="builder-side">
    <section className="builder-card"><div className="builder-card-head"><div className="step-number">02</div><div><h2>Model configuration</h2><p>Select the provider and model.</p></div></div><div className="field"><label>LLM Provider</label><select value={provider} onChange={e=>changeProvider(e.target.value)}>{Object.entries(providers).map(([k,v])=><option key={k} value={k}>{v.label}</option>)}{Object.keys(providers).length===0&&<option value="gemini">Google Gemini</option>}</select></div><div className="field"><label>Model</label><select value={model} onChange={e=>setModel(e.target.value)}>{providers[provider]?.models?.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}{!providers[provider]?.models?.length&&<option value={model}>{model}</option>}</select></div><div className="model-note"><span>●</span> Model settings can be reviewed before registration.</div></section>
    {error&&<div className="page-alert danger">{error}</div>}
    <section className="builder-card build-card"><div className="build-icon">✦</div><h2>Ready to build?</h2><p>The AI layer will generate a structured agent specification from your description.</p><button className="primary-button full" onClick={build} disabled={loading||prompt.trim().length<10}>{loading?<><span className="button-spinner"/> Generating...</>:<>Generate Agent <span>→</span></>}</button><small>Minimum 10 characters</small></section>
   </aside>
  </div>
 </div>;
}
