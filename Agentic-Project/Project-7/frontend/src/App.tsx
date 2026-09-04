import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import AgentList from './pages/AgentList';
import ExecuteAgent from './pages/ExecuteAgent';
import CreateAgent from './pages/CreateAgent';
import AgentPreview from './pages/AgentPreview';
import Login from './pages/Login';
import Register from './pages/Register';
import ExecutionHistory from './pages/ExecutionHistory';
import KnowledgeBase from './pages/KnowledgeBase';
import './App.css';

function AppLayout() {
  const location = useLocation();
  const fullBleed = location.pathname === '/execute';

  return (
    <div className="app">
      <Sidebar />
      <main className={`main-content ${fullBleed ? 'full-bleed' : ''}`}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/agents" element={<AgentList />} />
            <Route path="/create" element={<CreateAgent />} />
            <Route path="/preview" element={<AgentPreview />} />
            <Route path="/execute" element={<ExecuteAgent />} />
            <Route path="/history" element={<ExecutionHistory />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
          </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}
