// 本地存储工具类

const prefix = 'fpai_'

export const storage = {
  set(key: string, value: any): void {
    try {
      const data = JSON.stringify(value)
      localStorage.setItem(prefix + key, data)
    } catch (error) {
      console.error('Storage set error:', error)
    }
  },

  get<T = any>(key: string): T | null {
    try {
      const data = localStorage.getItem(prefix + key)
      return data ? JSON.parse(data) : null
    } catch (error) {
      console.error('Storage get error:', error)
      return null
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(prefix + key)
    } catch (error) {
      console.error('Storage remove error:', error)
    }
  },

  clear(): void {
    try {
      localStorage.clear()
    } catch (error) {
      console.error('Storage clear error:', error)
    }
  }
}
