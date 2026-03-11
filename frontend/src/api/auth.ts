import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

// 登录请求参数
export interface LoginParams {
  username: string
  password: string
  captcha?: string
}

// 登录响应数据（与后端一致：data.token、data.user）
export interface LoginResponse {
  token: string
  user: {
    id: number | string
    account: string
    name: string
    employee_no?: string
    email?: string
  }
}

// 用户信息（登录返回的 user 仅有前四项，getUserInfo 返回完整）
export interface UserInfo {
  id: number
  username: string
  email: string
  phone?: string
  real_name: string
  status?: string
  created_at?: string
}

// 登录
export function login(params: LoginParams): Promise<ApiResponse<LoginResponse>> {
  return request.post('/auth/login', params)
}

// 登出
export function logout(): Promise<ApiResponse> {
  return request.post('/auth/logout')
}

// 修改密码
export function changePassword(params: {
  old_password: string
  new_password: string
}): Promise<ApiResponse> {
  return request.post('/auth/change-password', params)
}

// 获取用户信息
export function getUserInfo(): Promise<ApiResponse<UserInfo>> {
  return request.get('/users/me')
}

// 更新当前用户信息参数
export interface UpdateCurrentUserParams {
  username?: string
  email?: string
  phone?: string
  real_name?: string
}

// 更新当前用户信息
export function updateCurrentUser(params: UpdateCurrentUserParams): Promise<ApiResponse<UserInfo>> {
  return request.put('/users/me', params)
}
