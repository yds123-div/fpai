/**
 * 系统参数配置 API
 */
import request from '@/utils/request'

// 外部知识库配置
export interface ExternalKBConfig {
  base_url: string
  api_key: string
  api_key_masked?: boolean
  enabled: boolean
  source?: 'database' | 'env' | 'none'
  version?: number
}

/**
 * 获取外部知识库配置
 */
export async function getExternalKBConfig() {
  const res = await request.get<ExternalKBConfig>('/config/external-kb')
  return res
}

/**
 * 保存外部知识库配置
 */
export async function updateExternalKBConfig(config: {
  base_url: string
  api_key: string
  enabled: boolean
}) {
  const res = await request.put('/config/external-kb', config)
  return res
}

/**
 * 测试外部知识库连接
 */
export async function testExternalKBConnection() {
  const res = await request.post<{ url?: string; status_code?: number; success: boolean }>(
    '/config/external-kb/test'
  )
  return res
}
