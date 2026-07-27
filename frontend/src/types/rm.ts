export type RmCustomerLevel = 'A' | 'B' | 'C'

export type RmRiskPreference = '稳健' | '平衡' | '进取'

export interface RmCustomer {
  id: string
  name: string
  level: RmCustomerLevel
  city: string
  occupation: string
  riskPreference: RmRiskPreference
  investmentHorizon: string
  aumBand: string
  goals: string[]
  tags: string[]
  notes: string
  lastContactAt: string
}

export type RmTodoStatus = 'open' | 'done'

export type RmTodoPriority = 'high' | 'medium' | 'low'

export type RmTodoSource = 'manual' | 'followup'

export interface RmTodo {
  id: string
  customerId: string
  title: string
  status: RmTodoStatus
  priority: RmTodoPriority
  source: RmTodoSource
  dueDate?: string
  createdAt: string
  updatedAt: string
}
