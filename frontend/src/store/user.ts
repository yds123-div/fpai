import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login, logout } from '@/api/auth'
import { UserInfo, getUserInfo } from '@/api/user'
import { storage } from '@/utils/storage'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(storage.get('token') || '')
  const userInfo = ref<UserInfo | null>(storage.get('userInfo') || null)

  // 登录：后端返回 data.token、data.user，仅使用单一 token
  async function loginAction(params: { username: string; password: string; captcha?: string }) {
    try {
      const res = await login(params)
      const { token: backendToken, user } = res.data

      const t = (backendToken ?? '').trim()
      token.value = t
      userInfo.value = user as unknown as UserInfo | null

      storage.set('token', t)
      storage.set('userInfo', user)

      return res
    } catch (error) {
      throw error
    }
  }

  // 清除用户数据（不调用 API）
  function clearUserData() {
    token.value = ''
    userInfo.value = null
    storage.remove('token')
    storage.remove('userInfo')
  }

  // 登出
  async function logoutAction() {
    try {
      // 如果有 token，尝试调用登出 API
      if (token.value) {
        await logout()
      }
    } catch (error) {
      console.error('Logout error:', error)
      // 即使 API 调用失败，也要清除本地数据
    } finally {
      clearUserData()
    }
  }

  // 获取用户信息
  async function fetchUserInfo() {
    try {
      const res = await getUserInfo()
      userInfo.value = res.data as UserInfo | null
      storage.set('userInfo', res.data)
      return res.data
    } catch (error) {
      throw error
    }
  }

  return {
    token,
    userInfo,
    login: loginAction,
    logout: logoutAction,
    clearUserData,
    fetchUserInfo
  }
})
