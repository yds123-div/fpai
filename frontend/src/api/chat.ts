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

export interface SessionMessageItem {
  role: 'user' | 'assistant'
  content_summary: string
  full_content?: string | null
  structured_outputs?: unknown[] | null
  answer_id?: string | null
  citation_count?: number
  created_at?: string
}

export interface SessionMessagesData {
  sessionId: string
  items: SessionMessageItem[]
}

export interface SessionListItem {
  sessionId: string
  createdAt: string
  lastMessageAt: string
  lastMessagePreview?: string | null
}

export interface SessionListData {
  items: SessionListItem[]
  total: number
  page: number
  pageSize: number
}

export interface DeleteSessionData {
  sessionId: string
  deleted: boolean
}

/**
 * 获取会话历史消息（按时间升序），用于页面刷新后恢复对话。
 * 会话不存在时抛出错误，调用方可据此清理本地缓存的 sessionId。
 */
export async function getSessionMessages(sessionId: string, limit = 50): Promise<SessionMessagesData> {
  const res = await request.get<SessionMessagesData>(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    params: { limit },
  })
  if (res.code !== 200) {
    throw new Error((res.message as string) || '请求失败')
  }
  return (res.data as SessionMessagesData) ?? { sessionId, items: [] }
}

/**
 * 获取当前用户会话列表（分页，按 lastMessageAt 倒序）。
 */
export async function listSessions(page = 1, pageSize = 20): Promise<SessionListData> {
  const res = await request.get<SessionListData>('/sessions', {
    params: { page, pageSize },
  })
  if (res.code !== 200) {
    throw new Error((res.message as string) || '请求失败')
  }
  return (res.data as SessionListData) ?? { items: [], total: 0, page, pageSize }
}

/**
 * 删除会话（仅当前用户所属会话）
 */
export async function deleteSession(sessionId: string): Promise<DeleteSessionData> {
  const res = await request.delete<DeleteSessionData>(`/sessions/${encodeURIComponent(sessionId)}`)
  if (res.code !== 200) {
    throw new Error((res.message as string) || '删除会话失败')
  }
  return (res.data as DeleteSessionData) ?? { sessionId, deleted: false }
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
              if (currentEvent === 'message' || currentEvent === 'message_delta') onMessage?.(data)
              else if (currentEvent === 'citation') onCitation?.(data)
              else if (currentEvent === 'status') onStatus?.(data as { stage?: string; message?: string })
              else if (currentEvent === 'done') {
                onDone?.(data)
              }
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
