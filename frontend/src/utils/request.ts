import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { message } from 'ant-design-vue'
import { useUserStore } from '@/store/user'

// 响应数据接口
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

// 创建 axios 实例
const service: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const userStore = useUserStore()
    const token = userStore.token

    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }

    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const res = response.data

    // 如果 code 不是 200，则判断为错误
    if (res.code !== 200) {
      message.error(res.message || '请求失败')
      
      // 401: 未授权，清除 token 并跳转到登录页
      // 排除登录接口和登出接口，避免循环调用
      const url = response.config.url || ''
      const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/logout')
      
      if (res.code === 401 && !isAuthEndpoint) {
        const userStore = useUserStore()
        // 只清除本地状态，不调用 logout API（避免循环）
        userStore.clearUserData()
        window.location.href = '/login'
      }

      return Promise.reject(new Error(res.message || '请求失败'))
    }

    // 返回 response，保持 AxiosResponse 类型
    return response
  },
  (error) => {
    console.error('Response error:', error)
    
    if (error.response) {
      const { status, data } = error.response
      const url = error.config?.url || ''
      const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/logout')
      
      switch (status) {
        case 400:
          message.error(data?.message || '请求参数错误')
          break
        case 401:
          // 登录接口失败时不调用 logout，只显示错误信息
          if (isAuthEndpoint && url.includes('/auth/login')) {
            message.error(data?.message || '用户名或密码错误')
          } else {
            message.error('未授权，请重新登录')
            const userStore = useUserStore()
            // 只清除本地状态，不调用 logout API（避免循环）
            userStore.clearUserData()
            window.location.href = '/login'
          }
          break
        case 403:
          message.error(data?.message || '权限不足，拒绝操作')
          break
        case 404:
          message.error(data?.message || '请求的资源不存在')
          break
        case 500:
          message.error(data?.message || '服务器内部错误')
          break
        default:
          message.error(data?.message || '请求失败')
      }
    } else {
      message.error('网络错误，请检查网络连接')
    }

    return Promise.reject(error)
  }
)

// 包装请求方法，自动提取 data
const requestWrapper = {
  get: <T = any>(url: string, config?: any): Promise<ApiResponse<T>> => {
    return service.get(url, config).then((res) => res.data)
  },
  post: <T = any>(url: string, data?: any, config?: any): Promise<ApiResponse<T>> => {
    return service.post(url, data, config).then((res) => res.data)
  },
  put: <T = any>(url: string, data?: any, config?: any): Promise<ApiResponse<T>> => {
    return service.put(url, data, config).then((res) => res.data)
  },
  delete: <T = any>(url: string, config?: any): Promise<ApiResponse<T>> => {
    return service.delete(url, config).then((res) => res.data)
  }
}

export default requestWrapper
