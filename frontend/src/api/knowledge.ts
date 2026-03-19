import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'
import { storage } from '@/utils/storage'

export interface ExternalKnowledgeItem {
  title?: string
  snippet?: string
  content?: string
  score?: number
  source?: string
  [key: string]: any
}

export interface ExternalKnowledgeRequest {
  model: string
  knowledge_base_id: string
  question: string
  top_k?: number
}

export function externalKnowledgeSearch(
  body: ExternalKnowledgeRequest
): Promise<ApiResponse<{ items: ExternalKnowledgeItem[] }>> {
  return request.post<{ items: ExternalKnowledgeItem[] }>('/knowledge/external-search', body)
}

export interface KnowledgeBaseOption {
  uuid: string
  name: string
  enabled?: number
  updated_at?: string | null
}

export function listKnowledgeBases(enabledOnly = true): Promise<ApiResponse<{ items: KnowledgeBaseOption[] }>> {
  return request.get<{ items: KnowledgeBaseOption[] }>('/knowledge/bases', { params: { enabledOnly } })
}

export function syncKnowledgeBases(): Promise<ApiResponse<{ ok: boolean; count: number; message: string }>> {
  return request.post<{ ok: boolean; count: number; message: string }>('/knowledge/bases/sync')
}

/**
 * 知识库对话（SSE 流式）：后端会先外部检索，再调用 LLM 回答
 */
export function postKnowledgeChatStream(
  body: { model_id?: number; knowledge_base_id: string; message: string; top_k?: number; model?: string },
  {
    onMessage,
    onCitation,
    onDone,
    onError,
  }: {
    onMessage?: (data: unknown) => void
    onCitation?: (data: unknown) => void
    onDone?: (data: unknown) => void
    onError?: (data: { code?: number; message?: string }) => void
  } = {}
): () => void {
  // 复用 chat.ts 的 SSE 解析逻辑，简化重复实现
  const controller = new AbortController()
  const payload = JSON.stringify(body)
  const url = `/api/v1/knowledge/chat`
  // axios 拦截器不会作用于 fetch，这里手动写入 Authorization
  const token = storage.get<string>('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token && typeof token === 'string') {
    headers.Authorization = `Bearer ${token}`
  }

  fetch(url, { method: 'POST', headers, body: payload, signal: controller.signal })
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
          if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
          else if (line.startsWith('data:')) currentData = line.slice(5).trim()
          else if (line === '' && currentEvent && currentData) {
            try {
              const data = JSON.parse(currentData) as unknown
              if (currentEvent === 'message') onMessage?.(data)
              else if (currentEvent === 'citation') onCitation?.(data)
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

