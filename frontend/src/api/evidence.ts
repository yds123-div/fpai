/**
 * 证据 API：GET /evidence/{answerId}（T033）
 */
import request from '@/utils/request'

export async function getEvidence(answerId: string): Promise<unknown> {
  const res = await request.get<unknown>(`/evidence/${encodeURIComponent(answerId)}`)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '获取证据失败')
  }
  return res.data ?? res
}
