<template>
  <div class="config-management">
    <div class="page-header">
      <h2 class="page-title">系统参数管理</h2>
      <p class="page-desc">配置系统运行参数，包括外部知识库连接等</p>
    </div>

    <a-card title="外部知识库配置" class="config-card">
      <template #extra>
        <a-space>
          <a-tag v-if="configLoaded && config.source === 'database'" color="green">
            数据库配置
          </a-tag>
          <a-tag v-else-if="configLoaded && config.source === 'env'" color="orange">
            环境变量
          </a-tag>
          <a-tag v-else-if="configLoaded && config.source === 'none'" color="red">
            未配置
          </a-tag>
        </a-space>
      </template>

      <a-form
        :model="formState"
        :label-col="{ span: 4 }"
        :wrapper-col="{ span: 16 }"
        @finish="handleSave"
      >
        <a-form-item label="启用状态" name="enabled">
          <a-switch v-model:checked="formState.enabled" />
          <span class="form-hint">关闭后将无法使用外部知识库检索功能</span>
        </a-form-item>

        <a-form-item
          label="服务地址"
          name="base_url"
          :rules="[
            { required: formState.enabled, message: '启用时必须填写服务地址' },
            { type: 'url', message: '请输入有效的 URL' }
          ]"
        >
          <a-input
            v-model:value="formState.base_url"
            placeholder="http://localhost:8080"
            :disabled="!formState.enabled"
          />
          <span class="form-hint">外部知识库服务的基础地址</span>
        </a-form-item>

        <a-form-item label="API 密钥" name="api_key">
          <a-input-password
            v-model:value="formState.api_key"
            placeholder="输入 API Key（留空表示不修改）"
            :disabled="!formState.enabled"
          />
          <span class="form-hint">
            访问外部知识库的鉴权密钥
            <span v-if="config.api_key_masked" style="color: #52c41a; font-weight: 500">
              ✓ 当前已配置密钥
            </span>
            <span v-else style="color: #ff4d4f">
              ✗ 未配置密钥
            </span>
          </span>
        </a-form-item>

        <a-form-item :wrapper-col="{ offset: 4, span: 16 }">
          <a-space>
            <a-button type="primary" html-type="submit" :loading="saving">
              <Icons.SaveOutlined />
              保存配置
            </a-button>
            <a-button @click="handleTest" :loading="testing" :disabled="!formState.enabled">
              <Icons.ApiOutlined />
              测试连接
            </a-button>
            <a-button @click="handleReset">
              <Icons.ReloadOutlined />
              重置
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>

      <a-divider />

      <div class="config-info">
        <h4>配置说明</h4>
        <ul>
          <li>服务地址：外部知识库服务的完整 URL，例如 <code>http://localhost:8080</code></li>
          <li>API 密钥：用于鉴权的密钥，将在请求头 <code>X-API-Key</code> 中发送</li>
          <li>配置保存后立即生效，无需重启服务</li>
          <li>建议先测试连接，确认配置正确后再保存</li>
        </ul>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import * as Icons from '@ant-design/icons-vue'
import {
  getExternalKBConfig,
  updateExternalKBConfig,
  testExternalKBConnection,
  type ExternalKBConfig
} from '@/api/config'

const configLoaded = ref(false)
const saving = ref(false)
const testing = ref(false)

const config = reactive<ExternalKBConfig>({
  base_url: '',
  api_key: '',
  api_key_masked: false,
  enabled: false,
  source: 'none',
  version: 0
})

const formState = reactive({
  base_url: '',
  api_key: '',
  enabled: false
})

// 加载配置
const loadConfig = async () => {
  try {
    const res = await getExternalKBConfig()
    if (res.code === 200 && res.data) {
      Object.assign(config, res.data)
      formState.base_url = config.base_url
      formState.enabled = config.enabled
      formState.api_key = '' // 不显示已保存的密钥
      configLoaded.value = true
    }
  } catch (error) {
    message.error('加载配置失败')
    console.error(error)
  }
}

// 保存配置
const handleSave = async () => {
  // 验证服务地址
  const baseUrl = formState.base_url.trim()
  if (formState.enabled && !baseUrl) {
    message.error('启用时必须填写服务地址')
    return
  }

  // 自动将服务地址修正为基础地址（去除 /api/ 等路径后缀）
  if (baseUrl) {
    try {
      const u = new URL(baseUrl)
      formState.base_url = u.origin
    } catch (_) {
      // 不是合法 URL 则不自动修正，由后端校验
    }
  }

  // 检查是否填写了新密钥
  const newApiKey = formState.api_key.trim()
  if (formState.enabled && !newApiKey && !config.api_key_masked) {
    message.error('启用时必须填写 API 密钥')
    return
  }

  saving.value = true
  try {
    const payload = {
      base_url: baseUrl,
      api_key: newApiKey || config.api_key, // 如果没填新密钥，保持原密钥
      enabled: formState.enabled
    }

    const res = await updateExternalKBConfig(payload)
    if (res.code === 200) {
      message.success('保存成功')
      await loadConfig()
      formState.api_key = '' // 清空密钥输入框
    } else {
      message.error(res.message || '保存失败')
    }
  } catch (error: any) {
    message.error(error.message || '保存失败')
    console.error(error)
  } finally {
    saving.value = false
  }
}

// 测试连接
const handleTest = async () => {
  if (!formState.base_url.trim()) {
    message.warning('请先填写服务地址')
    return
  }

  testing.value = true
  try {
    const res = await testExternalKBConnection()
    if (res.code === 200 && res.data?.success) {
      message.success('连接成功！')
    } else {
      message.error(res.message || '连接失败')
    }
  } catch (error: any) {
    message.error(error.message || '连接失败')
    console.error(error)
  } finally {
    testing.value = false
  }
}

// 重置表单
const handleReset = () => {
  formState.base_url = config.base_url
  formState.enabled = config.enabled
  formState.api_key = ''
  message.info('已重置为当前保存的配置')
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped lang="scss">
.config-management {
  padding: 24px;
  max-width: 1200px;

  .page-header {
    margin-bottom: 24px;

    .page-title {
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 8px;
      color: var(--text-primary, #333);
    }

    .page-desc {
      color: var(--text-secondary, #666);
      font-size: 14px;
      margin: 0;
    }
  }

  .config-card {
    margin-bottom: 24px;

    :deep(.ant-card-head-title) {
      font-weight: 600;
    }

    .form-hint {
      display: block;
      margin-top: 4px;
      font-size: 12px;
      color: var(--text-secondary, #999);
    }

    .config-info {
      padding: 16px;
      background: var(--bg-secondary, #f5f5f5);
      border-radius: 4px;

      h4 {
        margin: 0 0 12px 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary, #333);
      }

      ul {
        margin: 0;
        padding-left: 20px;

        li {
          margin-bottom: 8px;
          font-size: 13px;
          color: var(--text-secondary, #666);
          line-height: 1.6;

          &:last-child {
            margin-bottom: 0;
          }

          code {
            padding: 2px 6px;
            background: rgba(0, 0, 0, 0.06);
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
          }
        }
      }
    }
  }
}
</style>
