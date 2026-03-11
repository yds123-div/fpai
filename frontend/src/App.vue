<template>
  <a-config-provider :theme="antdTheme" :locale="locale">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/store/theme'
import zhCN from 'ant-design-vue/es/locale/zh_CN'

const themeStore = useThemeStore()

// Ant Design Vue 主题配置
const antdTheme = computed(() => {
  const theme = themeStore.currentTheme
  return {
    token: {
      colorPrimary: theme.primaryColor,
      colorSuccess: theme.successColor,
      colorWarning: theme.warningColor,
      colorError: theme.errorColor,
      colorInfo: theme.infoColor
    }
  }
})

// Ant Design Vue 全局配置 - 使用中文语言包
const locale = zhCN
</script>

<style scoped lang="scss">
// App 样式
</style>
