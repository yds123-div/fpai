import type { AnalysisSection } from '@/types/fundAnalysis'

function normalizeSpace(text: string): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}

export function firstSentence(text: string): string {
  const clean = normalizeSpace(text || '')
  if (!clean) return ''
  const m = clean.match(/^(.+?[。！？!?]|.+?$)/)
  return (m?.[1] || clean).trim()
}

export function resolveHeroConclusion(summary?: string, sections?: AnalysisSection[]): string {
  const s = normalizeSpace(summary || '')
  if (s) return s

  const textSections = (sections || []).filter(
    (sec): sec is Extract<AnalysisSection, { type: 'text' }> => sec?.type === 'text'
  )
  for (const sec of textSections) {
    const content = normalizeSpace((sec as { content?: string }).content || '')
    if (content) return content
  }
  return ''
}

