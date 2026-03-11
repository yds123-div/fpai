/**
 * 报告 API：POST /report/generate（T033）
 */
import request from '@/utils/request'

export async function postReportGenerate(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/report/generate', body)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '报告生成失败')
  }
  return res.data ?? res
}
