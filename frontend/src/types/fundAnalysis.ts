/**
 * 基金分析多模态输出类型定义。
 *
 * 与 Python 侧 backend/pkg/fund_types.py 保持一致。
 */

// ---------------------------------------------------------------------------
// 置顶卡片
// ---------------------------------------------------------------------------

export interface InfoCard {
  id: string
  title: string
  type: 'basic' | 'performance' | 'risk' | 'fee'
  data: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// 分析模块（Section）
// ---------------------------------------------------------------------------

export interface TableDef {
  headers: string[]
  rows: Array<Record<string, unknown>>
  highlight?: string[]
  /**
   * Optional per-cell rendering metadata.
   * - classes: map key `${rowIndex}|${header}` -> className
   * - tooltips: map key `${rowIndex}|${header}` -> tooltip text
   */
  cell?: {
    classes?: Record<string, string>
    tooltips?: Record<string, string>
  }
}

export interface TableSection {
  id: string
  title: string
  type: 'table'
  description?: string
  table: TableDef
}

export interface TextSection {
  id: string
  title: string
  type: 'text'
  content: string
  tags?: string[]
}

export type AnalysisSection = TableSection | TextSection

// ---------------------------------------------------------------------------
// 图表配置
// ---------------------------------------------------------------------------

export interface PieChartData {
  labels: string[]
  values: number[]
  colors?: string[]
}

export interface LineSeries {
  name: string
  data: Array<number | null>
  color?: string
  style?: 'solid' | 'dashed'
}

export interface LineChartData {
  xAxis: string[]
  series: LineSeries[]
}

export interface RadarIndicator {
  name: string
  max: number
}

export interface RadarSeries {
  name: string
  data: number[]
  color?: string
}

export interface RadarChartData {
  indicators: RadarIndicator[]
  series: RadarSeries[]
}

export interface ChartConfig {
  id: string
  title: string
  type: 'pie' | 'donut' | 'line' | 'bar' | 'radar'
  description?: string
  data: PieChartData | LineChartData | RadarChartData | Record<string, unknown>
  options?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// 顶层输出
// ---------------------------------------------------------------------------

export interface FundAnalysisOutput {
  type: 'fund_analysis'
  mode: 'single' | 'compare'
  summary: string
  cards: InfoCard[]
  sections: AnalysisSection[]
  charts: ChartConfig[]
  text: string
}
