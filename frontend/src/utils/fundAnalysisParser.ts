/**
 * 基金分析结构化输出解析工具。
 *
 * 从后端 SSE done 事件的 structuredOutputs 或 answerBlocks 中
 * 解析 FundAnalysisOutput 对象。
 */
import type { FundAnalysisOutput } from '@/types/fundAnalysis'

export function isFundAnalysis(data: unknown): data is FundAnalysisOutput {
  if (!data || typeof data !== 'object') return false
  const obj = data as Record<string, unknown>
  return (
    obj.type === 'fund_analysis' &&
    (obj.mode === 'single' || obj.mode === 'compare') &&
    Array.isArray(obj.cards) &&
    Array.isArray(obj.sections) &&
    Array.isArray(obj.charts) &&
    typeof obj.text === 'string'
  )
}

export function parseFundAnalysis(raw: string): FundAnalysisOutput | null {
  if (!raw || typeof raw !== 'string') return null
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const obj = JSON.parse(trimmed)
    if (isFundAnalysis(obj)) return obj
  } catch {
    // not valid JSON
  }
  return null
}

/**
 * 从 done 事件的 structuredOutputs 数组中提取第一个有效的
 * FundAnalysisOutput（如果有的话）。
 */
export function extractStructuredOutput(
  structuredOutputs?: unknown[]
): FundAnalysisOutput | null {
  if (!Array.isArray(structuredOutputs) || structuredOutputs.length === 0) {
    return null
  }
  for (const item of structuredOutputs) {
    if (isFundAnalysis(item)) return item
  }
  return null
}

export function mergeFundAnalysis(
  current: FundAnalysisOutput | null,
  incoming: FundAnalysisOutput | null
): FundAnalysisOutput | null {
  if (!incoming) return current
  if (!current) return incoming
  return {
    ...current,
    ...incoming,
    cards: Array.isArray(incoming.cards) && incoming.cards.length ? incoming.cards : (current.cards || []),
    sections: Array.isArray(incoming.sections) && incoming.sections.length ? incoming.sections : (current.sections || []),
    charts: Array.isArray(incoming.charts) && incoming.charts.length ? incoming.charts : (current.charts || []),
    summary: incoming.summary || current.summary || '',
    text: incoming.text || current.text || '',
  }
}
