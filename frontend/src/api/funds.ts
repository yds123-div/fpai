import request from '@/utils/request'

export type FundNavPeriod = '近1月' | '近3月' | '近1年' | '成立以来'

export interface FundNavChartData {
  xAxis: string[]
  series: Array<{
    name: string
    data: Array<number | null>
    color?: string
    style?: 'solid' | 'dashed'
  }>
}

export interface FundNavByPeriodResponse {
  symbol: string
  period: FundNavPeriod
  start: string
  end: string
  points: number
  chart: {
    id: string
    title: string
    description?: string
    data: FundNavChartData
    options?: Record<string, unknown>
  }
}

export async function getFundNavByPeriod(
  symbol: string,
  period: FundNavPeriod,
  opts?: { signal?: AbortSignal }
) {
  const res = await request.get<FundNavByPeriodResponse>(`/funds/${symbol}/nav`, {
    params: { period },
    signal: opts?.signal,
  })
  return res.data
}

