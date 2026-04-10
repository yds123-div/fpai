/**
 * 对话 API：POST /chat 非流式与 SSE 流式（T033）
 * 统一使用 utils/request；SSE 使用 fetch + storage token
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

export interface ChatStreamCallbacks {
  onMessage?: (data: unknown) => void
  onCitation?: (data: unknown) => void
  onStatus?: (data: { stage?: string; message?: string }) => void
  onDone?: (data: unknown) => void
  onError?: (data: { code?: number; message?: string }) => void
}

/**
 * 非流式发送：返回 envelope data（sessionId, answerId, answerBlocks, citations, compliance, trace, suggestedQuestions）
 */
export async function postChatNonStream(body: Record<string, unknown>): Promise<unknown> {
  const res = await request.post<unknown>('/chat', { ...body, stream: false })
  if (res.code !== 200) {
    throw new Error((res.message as string) || '请求失败')
  }
  return res.data ?? res
}

/**
 * 流式发送（SSE）：通过 onMessage/onCitation/onStatus/onDone/onError 回调推送
 */
export function postChatStream(
  body: Record<string, unknown>,
  { onMessage, onCitation, onStatus, onDone, onError }: ChatStreamCallbacks = {}
): () => void {
  const controller = new AbortController()
  const payload = JSON.stringify({ ...body, stream: true })
  const url = `${API_BASE}/chat`
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
      const reader = res.body?.getReader()
      if (!reader) {
        onError?.({ code: 500, message: '无响应流' })
        return
      }
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''
      let currentData = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            currentData = line.slice(5).trim()
          } else if (line === '' && currentEvent && currentData) {
            try {
              const data = JSON.parse(currentData) as unknown
              if (currentEvent === 'message') onMessage?.(data)
              else if (currentEvent === 'citation') onCitation?.(data)
              else if (currentEvent === 'status') onStatus?.(data as { stage?: string; message?: string })
              else if (currentEvent === 'done') onDone?.(data)
              else if (currentEvent === 'error') onError?.(data as { code?: number; message?: string })
            } catch {
              // ignore
            }
            currentEvent = ''
            currentData = ''
          }
        }
      }
    })
    .catch((err: Error & { name?: string }) => {
      if (err.name !== 'AbortError') onError?.({ code: 0, message: err?.message ?? '网络错误' })
    })

  return () => controller.abort()
}
