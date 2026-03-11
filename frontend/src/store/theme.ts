import { defineStore } from 'pinia'
import { ref } from 'vue'
import { storage } from '@/utils/storage'

// 主题配置接口
export interface ThemeConfig {
  // 主色调
  primaryColor: string
  primaryColorHover: string
  primaryColorActive: string
  
  // 强调色
  accentColor: string
  accentColorLight: string
  
  // 背景色
  darkBg: string
  darkBgAlt: string
  lightBg: string
  lightBgGray: string
  lightBgHover: string
  
  // 文字颜色
  textPrimary: string
  textSecondary: string
  textTertiary: string
  
  // 边框颜色
  borderColor: string
  borderColorLight: string
  
  // 状态颜色
  successColor: string
  warningColor: string
  errorColor: string
  infoColor: string
}

// 默认主题配置
const defaultTheme: ThemeConfig = {
  primaryColor: '#1890ff',
  primaryColorHover: '#40a9ff',
  primaryColorActive: '#096dd9',
  accentColor: '#00d4ff',
  accentColorLight: '#40a9ff',
  darkBg: '#001529',
  darkBgAlt: '#0a1929',
  lightBg: '#ffffff',
  lightBgGray: '#f5f5f5',
  lightBgHover: '#e6f7ff',
  textPrimary: '#262626',
  textSecondary: '#333333',
  textTertiary: '#8c8c8c',
  borderColor: '#e8e8e8',
  borderColorLight: '#f0f0f0',
  successColor: '#52c41a',
  warningColor: '#faad14',
  errorColor: '#ff4d4f',
  infoColor: '#1890ff'
}

// 预设主题
export const presetThemes: Record<string, ThemeConfig> = {
  default: defaultTheme,
  blue: {
    ...defaultTheme,
    primaryColor: '#1890ff',
    accentColor: '#00d4ff'
  },
  green: {
    ...defaultTheme,
    primaryColor: '#52c41a',
    primaryColorHover: '#73d13d',
    primaryColorActive: '#389e0d',
    accentColor: '#95de64',
    accentColorLight: '#73d13d'
  },
  purple: {
    ...defaultTheme,
    primaryColor: '#722ed1',
    primaryColorHover: '#9254de',
    primaryColorActive: '#531dab',
    accentColor: '#b37feb',
    accentColorLight: '#9254de'
  },
  orange: {
    ...defaultTheme,
    primaryColor: '#fa8c16',
    primaryColorHover: '#ffa940',
    primaryColorActive: '#d46b08',
    accentColor: '#ffc53d',
    accentColorLight: '#ffa940'
  },
  aiFinance: {
    ...defaultTheme,
    // 主色调：深蓝紫色，体现稳健和专业（金融行业）
    primaryColor: '#1a237e',        // 深蓝紫色 - 稳健、专业（更深）
    primaryColorHover: '#3f51b5',   // 亮蓝紫色 - 悬停效果（更鲜明）
    primaryColorActive: '#0d47a1',  // 深蓝色 - 激活状态（更有对比）
    // 强调色：鲜艳的青色/蓝绿色，体现智能和科技感（AI科技感）
    accentColor: '#00e5ff',          // 亮青色 - 智能、科技感（更亮）
    accentColorLight: '#b2ebf2',    // 浅青色 - 轻盈、灵动（更柔和）
    // 背景色：微调以配合主题
    darkBg: '#0a0e27',              // 深蓝黑背景 - 专业稳重（更深）
    darkBgAlt: '#1a1f3a',           // 稍亮的深蓝灰（更有层次）
    lightBgHover: '#e0f7fa',        // 浅青色悬停背景 - 呼应强调色（更亮）
    // 信息色：使用更鲜明的蓝色
    infoColor: '#2196f3'             // 亮蓝色 - 更鲜明
  }
}

export const useThemeStore = defineStore('theme', () => {
  const currentTheme = ref<ThemeConfig>(
    storage.get<ThemeConfig>('theme') || defaultTheme
  )
  const currentPreset = ref<string>(
    storage.get<string>('themePreset') || 'default'
  )

  // 应用主题到 DOM
  function applyTheme(theme: ThemeConfig) {
    const root = document.documentElement
    
    // 主色调
    root.style.setProperty('--primary-color', theme.primaryColor)
    root.style.setProperty('--primary-color-hover', theme.primaryColorHover)
    root.style.setProperty('--primary-color-active', theme.primaryColorActive)
    
    // 强调色
    root.style.setProperty('--accent-color', theme.accentColor)
    root.style.setProperty('--accent-color-light', theme.accentColorLight)
    
    // 背景色
    root.style.setProperty('--dark-bg', theme.darkBg)
    root.style.setProperty('--dark-bg-alt', theme.darkBgAlt)
    root.style.setProperty('--light-bg', theme.lightBg)
    root.style.setProperty('--light-bg-gray', theme.lightBgGray)
    root.style.setProperty('--light-bg-hover', theme.lightBgHover)
    
    // 文字颜色
    root.style.setProperty('--text-primary', theme.textPrimary)
    root.style.setProperty('--text-secondary', theme.textSecondary)
    root.style.setProperty('--text-tertiary', theme.textTertiary)
    
    // 边框颜色
    root.style.setProperty('--border-color', theme.borderColor)
    root.style.setProperty('--border-color-light', theme.borderColorLight)
    
    // 状态颜色
    root.style.setProperty('--success-color', theme.successColor)
    root.style.setProperty('--warning-color', theme.warningColor)
    root.style.setProperty('--error-color', theme.errorColor)
    root.style.setProperty('--info-color', theme.infoColor)
  }

  // 设置主题
  function setTheme(theme: ThemeConfig, preset?: string) {
    currentTheme.value = theme
    if (preset) {
      currentPreset.value = preset
      storage.set('themePreset', preset)
    }
    storage.set('theme', theme)
    applyTheme(theme)
  }

  // 使用预设主题
  function usePresetTheme(presetName: string) {
    const preset = presetThemes[presetName]
    if (preset) {
      setTheme(preset, presetName)
    }
  }

  // 重置为默认主题
  function resetTheme() {
    setTheme(defaultTheme, 'default')
  }

  // 初始化时应用主题
  applyTheme(currentTheme.value)

  return {
    currentTheme,
    currentPreset,
    presetThemes,
    setTheme,
    usePresetTheme,
    resetTheme,
    applyTheme
  }
})
