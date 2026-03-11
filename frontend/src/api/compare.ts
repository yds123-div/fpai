/**
 * 对比 API：POST /compare（T033）
 */
import request from '@/utils/request'

export async function postCompare(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/compare', body)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '对比请求失败')
  }
  return res.data ?? res
}
