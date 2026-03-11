/**
 * 获取 CSS 变量值
 * @param varName CSS 变量名（不含 --）
 * @returns CSS 变量值
 */
export function getCSSVariable(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${varName}`).trim()
}

/**
 * 设置 CSS 变量值
 * @param varName CSS 变量名（不含 --）
 * @param value 变量值
 */
export function setCSSVariable(varName: string, value: string): void {
  document.documentElement.style.setProperty(`--${varName}`, value)
}

/**
 * 批量设置 CSS 变量
 * @param variables 变量对象
 */
export function setCSSVariables(variables: Record<string, string>): void {
  Object.entries(variables).forEach(([key, value]) => {
    setCSSVariable(key, value)
  })
}

/**
 * 将十六进制颜色转换为 RGB
 * @param hex 十六进制颜色值（如 #1890ff）
 * @returns RGB 对象 { r, g, b }
 */
export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
      }
    : null
}

/**
 * 创建带透明度的 rgba 颜色字符串
 * @param hex 十六进制颜色值
 * @param alpha 透明度（0-1）
 * @returns rgba 颜色字符串
 */
export function rgba(hex: string, alpha: number): string {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`
}
