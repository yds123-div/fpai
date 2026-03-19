/**
 * 用户与菜单 API
 * 菜单为模拟数据，包含：参数管理、模型管理、知识库
 * 统一使用 utils/request
 */
import request from '@/utils/request'

// 菜单项接口

export interface MenuItem {
  code: string
  name: string
  path?: string
  icon?: string
  children?: MenuItem[]
}

/**
 * 获取用户菜单（后台管理侧栏）
 */
export async function getUserMenus(): Promise<{ code: number; data: MenuItem[] }> {
  const res = await request.get<{ items: MenuItem[] }>('/rbac/menus/me')
  const items = Array.isArray(res.data?.items) ? res.data.items : []
  return { code: 200, data: items }
}

// ---------- 当前用户信息与修改（模拟） ----------
// 用户信息（登录返回的 user 仅有前四项，getUserInfo 返回完整）
export interface UserInfo {
  id: string
  account: string
  email: string
  name: string
  employee_no?: string
  roles?: string[]
}


/**
 * 获取当前用户信息（模拟）
 */
export async function getUserInfo(): Promise<{ data: UserInfo }> {
  try {
    const res = await request.get<{ user?: Record<string, unknown> }>('/auth/me')
    if (res.data?.user) {
      const u = res.data.user as unknown as UserInfo
      return {
        data: {
          id: u.id,
          account: u.account,
          email: u.email,
          employee_no: u.employee_no,
          name: u.name
        }
      }
    }
  } catch {
    // 接口不可用时返回模拟数据
  }
  return {
    data: {
      id: '1',
      account: 'demo',
      email: 'demo@example.com',
      employee_no: '',
      name: '演示用户'
    }
  }
}

/**
 * 更新当前用户信息（模拟）
 */
export async function updateCurrentUser(payload: UserInfo): Promise<void> {
  try {
    await request.put('/auth/me', payload)
  } catch {
    // 模拟成功
  }
}

/**
 * 修改密码（模拟）
 */
export async function changePassword(params: {
  old_password: string
  new_password: string
}): Promise<void> {
  await request.post('/auth/change-password', params)
}

// ---------- 用户管理（对接 /api/v1/users） ----------
export interface User {
  id: string | number
  account: string
  name?: string
  employee_no?: string
  email?: string
  [key: string]: unknown
}

export interface UserListParams {
  page?: number
  page_size?: number
  account?: string
}

export interface UserListResult {
  items: User[]
  total: number
  page: number
  page_size: number
}

function checkEnvelope<T>(res: { code?: number; message?: string; data?: T }): T {
  if (res.code !== 200 && res.code !== 0) {
    throw new Error((res.message as string) || '请求失败')
  }
  return res.data as T
}

export async function getUsersList(params: UserListParams = {}): Promise<UserListResult> {
  const res = await request.get<UserListResult>('/users', { params })
  return checkEnvelope(res) as UserListResult
}

export async function getUserDetail(userId: string | number) {
  const res = await request.get<User>(`/users/${userId}`)
  return { data: checkEnvelope(res) }
}

export async function createUser(body: {
  account: string
  password: string
  name?: string
  employee_no?: string
  email?: string
}) {
  const res = await request.post<User>('/users', body)
  return { data: checkEnvelope(res) }
}

export async function updateUser(
  userId: string | number,
  body: { name?: string; employee_no?: string; email?: string }
) {
  const res = await request.put<User>(`/users/${userId}`, body)
  return { data: checkEnvelope(res) }
}

export async function deleteUser(userId: string | number) {
  const res = await request.delete(`/users/${userId}`)
  checkEnvelope(res)
}

export async function resetUserPassword(userId: string | number, params: { newPassword: string }) {
  const res = await request.post(`/users/${userId}/reset-password`, params)
  checkEnvelope(res)
}

// ---------- 以下为占位导出，供其他页面导入不报错 ----------
export interface UserOrganization {
  id?: number
  [key: string]: unknown
}

export interface UserRole {
  id?: number
  [key: string]: unknown
}

export interface UserPermission {
  [key: string]: unknown
}

export function getUserOrganizations() {
  return Promise.resolve({ data: [] })
}

export function assignOrganization() {
  return Promise.reject(new Error('接口未实现'))
}

export function removeOrganization() {
  return Promise.reject(new Error('接口未实现'))
}

export function getUserRoles() {
  return Promise.resolve({ data: [] })
}

export function assignRoles() {
  return Promise.reject(new Error('接口未实现'))
}

export function revokeRoles() {
  return Promise.reject(new Error('接口未实现'))
}

export function getUserPermissions() {
  return Promise.resolve({ data: [] })
}

export function getUserGroups() {
  return Promise.resolve({ data: [] })
}
