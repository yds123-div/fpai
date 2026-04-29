import type { RmTodo, RmTodoPriority } from '@/types/rm'

const STORAGE_KEY = 'rm_todos_v1'

function createTodoId() {
  return `todo_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

function normalizeTodo(raw: unknown): RmTodo | null {
  if (!raw || typeof raw !== 'object') return null
  const item = raw as Record<string, unknown>
  const status = item.status === 'done' ? 'done' : 'open'
  const priority = normalizePriority(item.priority)
  const source = item.source === 'followup' ? 'followup' : 'manual'
  const id = String(item.id || '').trim()
  const customerId = String(item.customerId || '').trim()
  const title = String(item.title || '').trim()
  const createdAt = String(item.createdAt || '').trim()
  const updatedAt = String(item.updatedAt || '').trim()
  const dueDate = typeof item.dueDate === 'string' && item.dueDate.trim() ? item.dueDate.trim() : undefined

  if (!id || !customerId || !title || !createdAt || !updatedAt) return null

  return {
    id,
    customerId,
    title,
    status,
    priority,
    source,
    dueDate,
    createdAt,
    updatedAt,
  }
}

function normalizePriority(value: unknown): RmTodoPriority {
  if (value === 'high' || value === 'low') return value
  return 'medium'
}

function safeParseTodos(raw: string | null): RmTodo[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeTodo).filter((item): item is RmTodo => Boolean(item))
  } catch {
    return []
  }
}

export function getAllRmTodos(): RmTodo[] {
  return safeParseTodos(window.localStorage.getItem(STORAGE_KEY))
}

export function getRmTodosByCustomerId(customerId: string): RmTodo[] {
  const id = String(customerId || '').trim()
  if (!id) return []
  return getAllRmTodos().filter((todo) => todo.customerId === id)
}

export function saveAllRmTodos(todos: RmTodo[]): void {
  const list = Array.isArray(todos) ? todos : []
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

export function addRmTodo(input: {
  customerId: string
  title: string
  priority?: RmTodoPriority
  dueDate?: string
}): RmTodo {
  const now = new Date().toISOString()
  const todo: RmTodo = {
    id: createTodoId(),
    customerId: String(input.customerId || '').trim(),
    title: String(input.title || '').trim(),
    status: 'open',
    priority: normalizePriority(input.priority),
    source: 'manual',
    dueDate: input.dueDate?.trim() || undefined,
    createdAt: now,
    updatedAt: now,
  }
  const todos = getAllRmTodos()
  const next = [todo, ...todos]
  saveAllRmTodos(next)
  return todo
}

export function toggleRmTodoStatus(todoId: string): RmTodo[] {
  const id = String(todoId || '').trim()
  const now = new Date().toISOString()
  const next: RmTodo[] = getAllRmTodos().map((todo) => {
    if (todo.id !== id) return todo
    return {
      ...todo,
      status: todo.status === 'done' ? 'open' : 'done',
      updatedAt: now,
    }
  })
  saveAllRmTodos(next)
  return next
}

export function deleteRmTodo(todoId: string): RmTodo[] {
  const id = String(todoId || '').trim()
  const next = getAllRmTodos().filter((todo) => todo.id !== id)
  saveAllRmTodos(next)
  return next
}
