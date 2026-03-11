<template>
  <div class="theme-settings">
    <div class="page-header">
      <h2 class="page-title">主题样式设置</h2>
    </div>
    <div class="settings-content">
      <a-card title="主题配置" class="theme-card">
        <a-tabs v-model:activeKey="activeTab">
          <a-tab-pane key="preset" tab="预设主题">
            <div class="preset-themes">
              <div
                v-for="(theme, name) in themeStore.presetThemes"
                :key="name"
                class="preset-theme-item"
                :class="{ active: selectedPreset === name }"
                @click="selectedPreset = name"
              >
                <div class="theme-preview">
                  <div
                    class="preview-primary"
                    :style="{ backgroundColor: theme.primaryColor }"
                  ></div>
                  <div
                    class="preview-accent"
                    :style="{ backgroundColor: theme.accentColor }"
                  ></div>
                  <div
                    class="preview-bg"
                    :style="{ backgroundColor: theme.lightBgGray }"
                  ></div>
                </div>
                <div class="theme-name">{{ getThemeName(name) }}</div>
                <CheckOutlined v-if="selectedPreset === name" class="check-icon" />
              </div>
            </div>
            <div class="preset-actions">
              <a-button @click="handleApplyPreset">应用</a-button>
            </div>
          </a-tab-pane>
          <a-tab-pane key="custom" tab="自定义主题">
            <a-form :model="customTheme" layout="vertical" class="custom-theme-form">
              <a-row :gutter="24">
                <a-col :span="12">
                  <h3 class="section-title">主色调</h3>
                  <a-form-item label="主色">
                    <a-input
                      v-model:value="customTheme.primaryColor"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.primaryColor"
                      style="margin-top: 8px"
                      placeholder="#1890ff"
                    />
                  </a-form-item>
                  <a-form-item label="主色（悬停）">
                    <a-input
                      v-model:value="customTheme.primaryColorHover"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.primaryColorHover"
                      style="margin-top: 8px"
                      placeholder="#40a9ff"
                    />
                  </a-form-item>
                  <a-form-item label="主色（激活）">
                    <a-input
                      v-model:value="customTheme.primaryColorActive"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.primaryColorActive"
                      style="margin-top: 8px"
                      placeholder="#096dd9"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <h3 class="section-title">强调色</h3>
                  <a-form-item label="强调色">
                    <a-input
                      v-model:value="customTheme.accentColor"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.accentColor"
                      style="margin-top: 8px"
                      placeholder="#00d4ff"
                    />
                  </a-form-item>
                  <a-form-item label="强调色（浅）">
                    <a-input
                      v-model:value="customTheme.accentColorLight"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.accentColorLight"
                      style="margin-top: 8px"
                      placeholder="#40a9ff"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-row :gutter="24" style="margin-top: 24px">
                <a-col :span="12">
                  <h3 class="section-title">背景色</h3>
                  <a-form-item label="深色背景">
                    <a-input
                      v-model:value="customTheme.darkBg"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.darkBg"
                      style="margin-top: 8px"
                      placeholder="#001529"
                    />
                  </a-form-item>
                  <a-form-item label="浅色背景">
                    <a-input
                      v-model:value="customTheme.lightBg"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.lightBg"
                      style="margin-top: 8px"
                      placeholder="#ffffff"
                    />
                  </a-form-item>
                  <a-form-item label="浅灰背景">
                    <a-input
                      v-model:value="customTheme.lightBgGray"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.lightBgGray"
                      style="margin-top: 8px"
                      placeholder="#f5f5f5"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <h3 class="section-title">文字颜色</h3>
                  <a-form-item label="主要文字">
                    <a-input
                      v-model:value="customTheme.textPrimary"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.textPrimary"
                      style="margin-top: 8px"
                      placeholder="#262626"
                    />
                  </a-form-item>
                  <a-form-item label="次要文字">
                    <a-input
                      v-model:value="customTheme.textSecondary"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.textSecondary"
                      style="margin-top: 8px"
                      placeholder="#333333"
                    />
                  </a-form-item>
                  <a-form-item label="辅助文字">
                    <a-input
                      v-model:value="customTheme.textTertiary"
                      type="color"
                      :style="{ width: '100%', height: '40px' }"
                    />
                    <a-input
                      v-model:value="customTheme.textTertiary"
                      style="margin-top: 8px"
                      placeholder="#8c8c8c"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <div class="form-actions">
                <a-button @click="handleReset">重置</a-button>
                <a-button @click="handleApplyCustom">应用</a-button>
              </div>
            </a-form>
          </a-tab-pane>
        </a-tabs>
      </a-card>
      
      <a-card title="预览效果" class="preview-card">
        <div class="theme-preview-area">
          <div class="preview-header" :style="{ backgroundColor: previewTheme.primaryColor }">
            <span style="color: white">预览标题</span>
          </div>
          <div class="preview-content" :style="{ backgroundColor: previewTheme.lightBgGray }">
            <a-button 
              type="primary" 
              style="margin-right: 8px"
              :style="{ backgroundColor: previewTheme.primaryColor, borderColor: previewTheme.primaryColor }"
            >
              主要按钮
            </a-button>
            <a-button>次要按钮</a-button>
            <div style="margin-top: 16px">
              <a-tag :color="previewTheme.successColor">成功</a-tag>
              <a-tag :color="previewTheme.warningColor">警告</a-tag>
              <a-tag :color="previewTheme.errorColor">错误</a-tag>
            </div>
          </div>
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { message } from 'ant-design-vue'
import { CheckOutlined } from '@ant-design/icons-vue'
import { useThemeStore, presetThemes, type ThemeConfig } from '@/store/theme'

const themeStore = useThemeStore()
const activeTab = ref('preset')
const selectedPreset = ref<string>(themeStore.currentPreset)

const customTheme = reactive<ThemeConfig>({
  ...themeStore.currentTheme
})

// 预览主题：根据当前选中的标签页和预设主题返回预览用的主题配置
const previewTheme = computed<ThemeConfig>(() => {
  if (activeTab.value === 'preset' && selectedPreset.value) {
    // 预设主题标签页：使用选中的预设主题
    return presetThemes[selectedPreset.value] || themeStore.currentTheme
  } else {
    // 自定义主题标签页：使用自定义主题配置
    return customTheme
  }
})

// 监听当前主题变化，同步到自定义表单
watch(
  () => themeStore.currentTheme,
  (newTheme) => {
    Object.assign(customTheme, newTheme)
  },
  { deep: true }
)

const getThemeName = (name: string): string => {
  const names: Record<string, string> = {
    default: '默认主题',
    blue: '蓝色主题',
    green: '绿色主题',
    purple: '紫色主题',
    orange: '橙色主题',
    aiFinance: 'AI金融科技主题'
  }
  return names[name] || name
}

const handleApplyPreset = () => {
  if (!selectedPreset.value) {
    message.warning('请先选择一个主题')
    return
  }
  themeStore.usePresetTheme(selectedPreset.value)
  message.success(`已切换到${getThemeName(selectedPreset.value)}`)
}

// 监听当前预设主题变化，同步选中状态
watch(
  () => themeStore.currentPreset,
  (newPreset) => {
    selectedPreset.value = newPreset
  }
)

const handleApplyCustom = () => {
  themeStore.setTheme({ ...customTheme })
  message.success('自定义主题已应用')
}

const handleReset = () => {
  themeStore.resetTheme()
  Object.assign(customTheme, themeStore.currentTheme)
  message.success('已重置为默认主题')
}
</script>

<style scoped lang="scss">
.theme-settings {
  padding: 24px;
  background: transparent;
  min-height: 100%;
}

.page-header {
  margin-bottom: 24px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  padding: 20px 24px;
  border-radius: 8px;
  border: 1px solid rgba($primary-color, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(180deg, $accent-color, $primary-color);
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(135deg, $text-primary 0%, $primary-color 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
  }
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.theme-card,
.preview-card {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  border: 1px solid rgba($primary-color, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.preset-themes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
  padding: 16px 0;
}

.preset-theme-item {
  position: relative;
  padding: 16px;
  border: 2px solid $border-color;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background-color: $light-bg;

  &:hover {
    border-color: $primary-color;
    box-shadow: 0 4px 12px rgba($primary-color, 0.2);
    transform: translateY(-2px);
  }

  &.active {
    border-color: $primary-color;
    box-shadow: 0 4px 12px rgba($primary-color, 0.3);
    background: linear-gradient(135deg, rgba($primary-color, 0.05) 0%, rgba($accent-color, 0.02) 100%);
  }

  .theme-preview {
    display: flex;
    gap: 4px;
    margin-bottom: 12px;
    height: 60px;
    border-radius: 4px;
    overflow: hidden;

    .preview-primary {
      flex: 2;
    }

    .preview-accent {
      flex: 1;
    }

    .preview-bg {
      flex: 1;
    }
  }

  .theme-name {
    text-align: center;
    font-weight: 500;
    color: $text-primary;
  }

  .check-icon {
    position: absolute;
    top: 8px;
    right: 8px;
    color: $primary-color;
    font-size: 18px;
  }
}

.custom-theme-form {
  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid rgba($primary-color, 0.1);
  }
}

.preset-actions {
  margin-top: 24px;
  text-align: right;
  padding-top: 24px;
  border-top: 1px solid $border-color;
}

.form-actions {
  margin-top: 24px;
  text-align: right;
  padding-top: 24px;
  border-top: 1px solid $border-color;

  button {
      margin-left: 8px;
    }
}

.theme-preview-area {
  border: 1px solid $border-color;
  border-radius: 8px;
  overflow: hidden;

  .preview-header {
    padding: 16px;
    color: white;
    font-weight: 500;
  }

  .preview-content {
    padding: 24px;
    background-color: $light-bg-gray;
  }
}
</style>
