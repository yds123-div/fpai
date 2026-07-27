import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

export interface RoleItem {
  id: number
  code: string
  name: string
  description: string
  enabled: number
  updated_at?: string | null
}

export interface MenuItemRbac {
  id: number
  code: string
  name: string
  path: string
  icon: string
  parent_id: number | null
  sort_order: number
  enabled: number
  updated_at?: string | null
}

export function listRoles(): Promise<ApiResponse<{ items: RoleItem[] }>> {
  return request.get<{ items: RoleItem[] }>('/rbac/roles')
}

export function upsertRole(body: { code: string; name: string; description?: string; enabled: boolean }): Promise<ApiResponse<{ ack: boolean }>> {
  return request.post<{ ack: boolean }>('/rbac/roles', body)
}

export function listMenus(): Promise<ApiResponse<{ items: MenuItemRbac[] }>> {
  return request.get<{ items: MenuItemRbac[] }>('/rbac/menus')
}

export function upsertMenu(body: {
  code: string
  name: string
  path: string
  icon?: string
  parent_id?: number | null
  sort_order?: number
  enabled: boolean
}): Promise<ApiResponse<{ ack: boolean }>> {
  return request.post<{ ack: boolean }>('/rbac/menus', body)
}

export function getUserRoles(userId: string | number): Promise<ApiResponse<{ items: string[] }>> {
  return request.get<{ items: string[] }>(`/rbac/users/${userId}/roles`)
}

export function setUserRoles(userId: string | number, role_codes: string[]): Promise<ApiResponse<{ ack: boolean }>> {
  return request.put<{ ack: boolean }>(`/rbac/users/${userId}/roles`, { role_codes })
}

export function getRoleMenus(roleCode: string): Promise<ApiResponse<{ items: string[] }>> {
  return request.get<{ items: string[] }>(`/rbac/roles/${encodeURIComponent(roleCode)}/menus`)
}

export function setRoleMenus(roleCode: string, menu_codes: string[]): Promise<ApiResponse<{ ack: boolean }>> {
  return request.put<{ ack: boolean }>(`/rbac/roles/${encodeURIComponent(roleCode)}/menus`, { menu_codes })
}

