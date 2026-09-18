import axios from 'axios';

const BACKEND_URL = 'http://192.168.1.85:9000';
const AI_LAYER_URL = 'http://192.168.1.50:8000';

const backendApi = axios.create({
  baseURL: BACKEND_URL,
  headers: { 'Content-Type': 'application/json' },
});

const aiLayerApi = axios.create({
  baseURL: AI_LAYER_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Types
export type AgentHealth = {
  service: string;
  status: string;
};

export type AgentModelConfig = {
  provider: string;
  model: string;
};

export type AgentSpec = {
  name: string;
  description: string;
  capabilities: string[];
  model: AgentModelConfig;
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  system_prompt: string;
  knowledge_base_id?: string;
};

export type BuildResponse = {
  success: boolean;
  spec: AgentSpec;
  warnings: string[];
};

export type RegisteredAgent = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  current_version: number;
  system_prompt: string;
  capabilities: string[];
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  is_rag: boolean;
  knowledge_base_id: string | null;
  model: AgentModelConfig;
};

export type ExecutionResult = {
  execution_id: string;
  agent_id: string;
  status: string;
  output: { result: string } | null;
  error: string | null;
  latency_ms: number;
};

export type ExecutionRecord = {
  id: string;
  agent_id: string;
  user_id: number;
  input_payload: string;
  output_payload: string | null;
  status: string;
  start_time: string;
  end_time: string | null;
  latency_ms: number;
  error_message: string | null;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  status: string;
};

export type KnowledgeDocument = {
  id: string;
  kb_id: string;
  filename: string;
  status: string;
  chunk_count: number;
  error_message: string | null;
};

export type KnowledgeSearchResult = {
  text: string;
  score: number;
};

// Auth (removed - no auth required)
export const isLoggedIn = (): boolean => true;
export const logout = () => {};

// AI Layer APIs
export const getHealth = async (): Promise<AgentHealth> => {
  const response = await aiLayerApi.get('/health');
  return response.data;
};

export const buildAgent = async (
  prompt: string,
  provider: string = 'gemini',
  model: string = 'gemini-3.5-flash-lite'
): Promise<BuildResponse> => {
  const response = await aiLayerApi.post('/api/agents/build', {
    prompt,
    provider,
    model,
  });
  return response.data;
};

// Backend Agent APIs
export const registerAgent = async (
  spec: AgentSpec
): Promise<RegisteredAgent> => {
  const payload = {
    name: spec.name,
    description: spec.description,
    system_prompt: spec.system_prompt,
    capabilities: spec.capabilities,
    input_schema: spec.input_schema,
    output_schema: spec.output_schema,
    knowledge_base_id: spec.knowledge_base_id || null,
    model: {
      provider: spec.model.provider,
      model: spec.model.model,
    },
  };
  const response = await backendApi.post('/api/agents', payload);
  return response.data;
};

export const listAgents = async (): Promise<RegisteredAgent[]> => {
  const response = await backendApi.get('/api/agents');
  return response.data;
};

// Partial update to an EXISTING agent (e.g. attaching a knowledge_base_id
// after the fact). Uses PUT, unlike registerAgent() which always CREATES
// a new agent -- these must never be used interchangeably.
export const updateAgent = async (
  agentId: string,
  updates: Partial<{
    description: string;
    system_prompt: string;
    capabilities: string[];
    input_schema: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    knowledge_base_id: string | null;
    is_rag: boolean;
  }>
): Promise<RegisteredAgent> => {
  const response = await backendApi.put(`/api/agents/${agentId}`, updates);
  return response.data;
};

export const executeRegisteredAgent = async (
  agentId: string,
  input: string
): Promise<ExecutionResult> => {
  const response = await backendApi.post(`/api/agents/${agentId}/execute`, {
    input: input,
    parameters: null,
  });
  return response.data;
};

export const deleteAgent = async (agentId: string): Promise<void> => {
  await backendApi.delete(`/api/agents/${agentId}`);
};

export const toggleAgentStatus = async (
  agentId: string,
  status: 'active' | 'inactive'
): Promise<RegisteredAgent> => {
  const response = await backendApi.patch(`/api/agents/${agentId}/status`, {
    status,
  });
  return response.data;
};

export const discoverAgents = async (
  capability?: string
): Promise<RegisteredAgent[]> => {
  const url = capability
    ? `/api/agents/discover?capability=${capability}`
    : '/api/agents/discover';
  const response = await backendApi.get(url);
  return response.data;
};

// Execution APIs
export const getExecutions = async (): Promise<ExecutionRecord[]> => {
  const response = await backendApi.get('/api/executions');
  return response.data;
};

// Knowledge Base APIs
export const listKnowledgeBases = async (): Promise<KnowledgeBase[]> => {
  const response = await backendApi.get('/api/knowledge-bases');
  return response.data;
};

export const createKnowledgeBase = async (
  name: string,
  description: string
): Promise<KnowledgeBase> => {
  const response = await backendApi.post('/api/knowledge-bases', {
    name,
    description,
  });
  return response.data;
};

export const getKnowledgeBase = async (
  knowledgeBaseId: string
): Promise<KnowledgeBase> => {
  const response = await backendApi.get(`/api/knowledge-bases/${knowledgeBaseId}`);
  return response.data;
};

export const uploadKnowledgeDocument = async (
  knowledgeBaseId: string,
  file: File
): Promise<KnowledgeDocument> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await backendApi.post(
    `/api/knowledge-bases/${knowledgeBaseId}/upload`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return response.data;
};

export const searchKnowledgeBase = async (
  knowledgeBaseId: string,
  query: string,
  topK: number = 5
): Promise<KnowledgeSearchResult[]> => {
  const response = await backendApi.get(
    `/api/knowledge-bases/${knowledgeBaseId}/search?q=${encodeURIComponent(query)}&top_k=${topK}`
  );
  return response.data;
};