import { NavLink } from 'react-router-dom';
import './Sidebar.css';

const items = [
  { path: '/', label: 'Dashboard', icon: 'grid' },
  { path: '/execute', label: 'Execute Agent', icon: 'chat' },
  { path: '/agents', label: 'Agents', icon: 'bot' },
  { path: '/create', label: 'Create Agent', icon: 'plus' },
  { path: '/history', label: 'Execution History', icon: 'clock' },
  { path: '/knowledge', label: 'Knowledge Base', icon: 'book' },
];

function Icon({name}:{name:string}){
  const common={width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.8,strokeLinecap:'round' as const,strokeLinejoin:'round' as const};
  if(name==='grid') return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
  if(name==='chat') return <svg {...common}><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.8 8.8 0 0 1-3.4-.7L4 20l1.5-3.6A7.2 7.2 0 0 1 4.5 12 7.5 7.5 0 0 1 12 4.5a7.5 7.5 0 0 1 8 7Z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/></svg>;
  if(name==='bot') return <svg {...common}><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></svg>;
  if(name==='plus') return <svg {...common}><path d="M12 5v14M5 12h14"/></svg>;
  if(name==='clock') return <svg {...common}><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/></svg>;
  return <svg {...common}><path d="M5 4.5h10l4 4V20H5z"/><path d="M15 4.5V9h4M8 13h8M8 16h6"/></svg>;
}

export default function Sidebar(){
  return <aside className="sidebar">
    <div className="brand">
      <div className="brand-mark"><span>✦</span></div>
      <div><div className="brand-title">AgentOS</div><div className="brand-subtitle">Agentic AI Platform</div></div>
    </div>
    <div className="nav-heading">WORKSPACE</div>
    <nav className="sidebar-nav">
      {items.map(item=><NavLink key={item.path} to={item.path} end={item.path==='/' } className={({isActive})=>`nav-item ${isActive?'active':''}`}>
        <span className="nav-icon"><Icon name={item.icon}/></span><span>{item.label}</span>
      </NavLink>)}
    </nav>
    <div className="sidebar-bottom">
      <div className="platform-card"><div className="online-dot"/><div><strong>Platform online</strong><span>Services are available</span></div></div>
      <div className="version">AgentOS · v1.0</div>
    </div>
  </aside>;
}
