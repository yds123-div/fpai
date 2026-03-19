import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

export type AgentType = 'builtin' | 'custom'

export interface AgentProfile {
  agent_key: string
  name: string
  type: AgentType | string
  enabled: number
  system_prompt: string
  skill_keys?: string[] | string
  model_id: number | null
  updated_by?: string
  updated_at?: string | null
  deleted_at?: string | null
}

export interface AgentUpsertBody {
  agent_key: string
  name: string
  type?: AgentType | string
  enabled: boolean
  system_prompt: string
  skill_keys?: string[]
  model_id?: number | null
}

export function listAgents(includeDeleted = false): Promise<ApiResponse<{ items: AgentProfile[] }>> {
  return request.get<{ items: AgentProfile[] }>('/agents', { params: { includeDeleted } })
}

export function getAgent(agentKey: string): Promise<ApiResponse<AgentProfile>> {
  return request.get<AgentProfile>(`/agents/${encodeURIComponent(agentKey)}`)
}

export function createAgent(body: AgentUpsertBody): Promise<ApiResponse<{ ack: boolean }>> {
  return request.post<{ ack: boolean }>('/agents', body)
}

export function updateAgent(agentKey: string, body: AgentUpsertBody): Promise<ApiResponse<{ ack: boolean }>> {
  return request.put<{ ack: boolean }>(`/agents/${encodeURIComponent(agentKey)}`, body)
}

export function deleteAgent(agentKey: string): Promise<ApiResponse<{ ack: boolean }>> {
  return request.delete<{ ack: boolean }>(`/agents/${encodeURIComponent(agentKey)}`)
}

