/**
 * 推荐 API：POST /recommend（T033）
 */
import request from '@/utils/request'
import { storage } from '@/utils/storage'

const API_BASE = '/api/v1'

function getAuthHeader(): Record<string, string> {
  try {
    const token = storage.get<string>('token')
    return token && typeof token === 'string' ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

export async function postRecommend(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/recommend', body)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '推荐请求失败')
  }
  return res.data ?? res
}

export interface RecommendStreamCallbacks {
  onMessage?: (data: { text?: string }) => void
  onDone?: (data: unknown) => void
  onError?: (data: { code?: number; message?: string }) => void
}

export function postRecommendStream(
  body: Record<string, unknown>,
  { onMessage, onDone, onError }: RecommendStreamCallbacks = {}
): () => void {
  const controller = new AbortController()
  const payload = JSON.stringify(body)
  const url = `${API_BASE}/recommend/stream`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
  }

  fetch(url, {
    method: 'POST',
    headers,
    body: payload,
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        onError?.({ code: res.status, message: res.statusText })
        return
      }
      const ct = (res.headers.get('content-type') || '').toLowerCase()
      if (ct.includes('application/json')) {
        // 鉴权失败/参数校验等会走 envelope JSON（HTTP 200），不能当 SSE 解析
        try {
          const jsonBody = (await res.json()) as { code?: number; message?: string }
          onError?.({ code: jsonBody.code, message: jsonBody.message || '请求失败' })
        } catch {
          onError?.({ code: 500, message: '响应解析失败' })
        }
        return
      }

      const reader = res.body?.getReader()
      if (!reader) {
        onError?.({ code: 500, message: '无响应流' })
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''
      let currentData = ''
      let streamFinished = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() ?? ''
        for (const raw of lines) {
          const line = raw.replace(/\r$/, '')
          if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
          else if (line.startsWith('data:')) currentData = line.slice(5).trim()
          else if (line === '' && currentEvent && currentData) {
            try {
              const data = JSON.parse(currentData) as unknown
              if (currentEvent === 'message') onMessage?.((data as { text?: string }) || {})
              else if (currentEvent === 'done') {
                streamFinished = true
                onDone?.(data)
              } else if (currentEvent === 'error') {
                streamFinished = true
                onError?.(data as { code?: number; message?: string })
              }
            } catch {
              // ignore parse errors
            }
            currentEvent = ''
            currentData = ''
          }
        }
      }

      if (!streamFinished) {
        onError?.({ code: 0, message: '未收到完整流式结果，请检查网络或重新登录后重试' })
      }
    })
    .catch((err: Error & { name?: string }) => {
      if (err.name !== 'AbortError') onError?.({ code: 0, message: err?.message ?? '网络错误' })
    })

  return () => controller.abort()
}
