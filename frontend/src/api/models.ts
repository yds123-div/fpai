import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

export type ModelSource = 'ollama' | 'remote'

export interface AiModelItem {
  id: number
  name: string
  source: ModelSource
  vendor: string
  model_name: string
  base_url: string
  enabled: number
  has_api_key: boolean
  updated_at?: string | null
}

export interface ModelUpsertBody {
  id?: number
  source: ModelSource
  vendor: string
  model_name: string
  base_url: string
  api_key?: string
  enabled: boolean
}

export function listModels(enabledOnly = true): Promise<ApiResponse<{ items: AiModelItem[] }>> {
  return request.get<{ items: AiModelItem[] }>('/models', { params: { enabledOnly } })
}

export function upsertModel(body: ModelUpsertBody): Promise<ApiResponse<{ id: number }>> {
  return request.post<{ id: number }>('/models', body)
}

export function deleteModel(id: number): Promise<ApiResponse<{ ack: boolean }>> {
  return request.delete<{ ack: boolean }>(`/models/${id}`)
}

export function testModelConnection(body: {
  source: ModelSource
  vendor: string
  model_name: string
  base_url: string
  api_key?: string
}): Promise<ApiResponse<{ reachable: boolean; sample?: string[] }>> {
  return request.post<{ reachable: boolean; sample?: string[] }>('/models/test', body)
}

