import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

export interface SkillProfile {
  skill_key: string
  name: string
  type: string
  enabled: number
  module_path: string
  description: string
  updated_by?: string
  updated_at?: string | null
  deleted_at?: string | null
}

export interface SkillUpsertBody {
  skill_key: string
  name: string
  type?: string
  enabled: boolean
  module_path: string
  description?: string
}

export function listSkills(includeDeleted = false): Promise<ApiResponse<{ items: SkillProfile[] }>> {
  return request.get<{ items: SkillProfile[] }>('/skills', { params: { includeDeleted } })
}

export function createSkill(body: SkillUpsertBody): Promise<ApiResponse<{ ack: boolean }>> {
  return request.post<{ ack: boolean }>('/skills', body)
}

export function updateSkill(skillKey: string, body: SkillUpsertBody): Promise<ApiResponse<{ ack: boolean }>> {
  return request.put<{ ack: boolean }>(`/skills/${encodeURIComponent(skillKey)}`, body)
}

export function deleteSkill(skillKey: string): Promise<ApiResponse<{ ack: boolean }>> {
  return request.delete<{ ack: boolean }>(`/skills/${encodeURIComponent(skillKey)}`)
}

