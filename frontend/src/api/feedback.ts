/**
 * 反馈 API：POST /feedback（T033）
 */
import request from '@/utils/request'

export async function postFeedback(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/feedback', body)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '反馈提交失败')
  }
  return res.data ?? res
}
