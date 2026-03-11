/**
 * 推荐 API：POST /recommend（T033）
 */
import request from '@/utils/request'

export async function postRecommend(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/recommend', body)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '推荐请求失败')
  }
  return res.data ?? res
}
