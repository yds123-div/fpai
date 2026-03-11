<template>
  <div class="login-page">
    <div class="login-left">
      <div class="left-content">
        <div class="system-badge">面向客户经理</div>
        <h1 class="main-title">财富业务全场景「金融产品解析智能体」</h1>
        <p class="description">
          通过 问答交互、意图识别、记忆模块与多智能体协同，在合规约束下为银行客户经理提供实时、可追溯的产品要素解读、产品匹配与对比、研报/政策摘要以及周报月报等专业内容生成能力，显著提升销售沟通效率与客户体验。
        </p>
        <div class="features">
          <div class="feature-item">
            <span class="feature-icon">✓</span>
            <span>理财产品、基金、保险、信托、专户全覆盖</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">✓</span>
            <span>意图识别 + 多智能体协同</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">✓</span>
            <span>合规约束、可追溯引用</span>
          </div>
        </div>
        <div class="feature-cards">
          <div class="feature-card">
            <div class="card-icon">📄</div>
            <h3>产品要素实时解读</h3>
            <p>风险/期限/费率/投向/业绩基准解释，多产品横向对比（结构化对比表），随问随答、答得准。</p>
          </div>
          <div class="feature-card">
            <div class="card-icon">📚</div>
            <h3>产品匹配与推荐</h3>
            <p>按客户需求与风险偏好检索适配产品，快速对比、快速匹配，为销售沟通提供专业支撑。</p>
          </div>
          <div class="feature-card">
            <div class="card-icon">⚙️</div>
            <h3>研报摘要与内容生成</h3>
            <p>自动检索并摘要行业研报、市场观点、监管政策与内部投研报告，自动生成财富周报/月报/市场解读稿。</p>
          </div>
        </div>
      </div>
    </div>
    <div class="login-right">
      <div class="login-form-container">
        <div class="logo-section">
          <div class="logo-circle">X</div>
          <div class="logo-text">
            <div class="logo-title">XXXX公司</div>
            <div class="logo-subtitle">XXXX</div>
          </div>
        </div>
        <h2 class="system-title">金融产品解析智能体</h2>
        <p class="welcome-text">欢迎登录</p>
        <a-form
          :model="formData"
          :rules="rules"
          @finish="handleLogin"
          class="login-form"
        >
          <a-form-item name="username">
            <a-input
              v-model:value="formData.username"
              placeholder="请输入用户名"
              size="large"
            >
              <template #prefix>
                <UserOutlined />
              </template>
            </a-input>
          </a-form-item>
          <a-form-item name="password">
            <a-input-password
              v-model:value="formData.password"
              placeholder="请输入密码"
              size="large"
            >
              <template #prefix>
                <LockOutlined />
              </template>
            </a-input-password>
          </a-form-item>
          <a-form-item>
            <div class="form-options">
              <a-checkbox v-model:checked="rememberPassword">
                记住密码
              </a-checkbox>
              <a href="#" class="forgot-password">忘记密码</a>
            </div>
          </a-form-item>
          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              :loading="loading"
              class="login-button"
            >
              登录
            </a-button>
          </a-form-item>
        </a-form>
        <div class="copyright">
          Copyright ©2025 All Rights Reserved XXXX公司 版权所有
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { UserOutlined, LockOutlined } from '@ant-design/icons-vue'
import { useUserStore } from '@/store/user'
import { message } from 'ant-design-vue'
import { encryptPassword } from '@/utils/crypto'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const rememberPassword = ref(false)

const formData = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  loading.value = true
  try {
    // 加密密码
    const encryptedPassword = await encryptPassword(formData.password)
    
    await userStore.login({
      username: formData.username,
      password: encryptedPassword
    })
    message.success('登录成功')
    const redirect = router.currentRoute.value.query.redirect as string
    router.push(redirect || '/')
  } catch (error) {
    console.error('Login error:', error)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.login-page {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.login-left {
  flex: 1;
  background: linear-gradient(135deg, $dark-bg 0%, $dark-bg-alt 100%);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
      radial-gradient(circle at 20% 50%, rgba($accent-color, 0.1) 0%, transparent 50%),
      radial-gradient(circle at 80% 80%, rgba($accent-color-light, 0.1) 0%, transparent 50%);
    pointer-events: none;
  }

  .left-content {
    padding: 80px 60px;
    height: 100%;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
  }

  .system-badge {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.8);
    margin-bottom: 24px;
  }

  .main-title {
    font-size: 36px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 24px;
    line-height: 1.4;
  }

  .description {
    font-size: 16px;
    color: rgba(255, 255, 255, 0.9);
    line-height: 1.8;
    margin-bottom: 48px;
  }

  .features {
    display: flex;
    gap: 32px;
    margin-bottom: 60px;

    .feature-item {
      display: flex;
      align-items: center;
      gap: 8px;
      color: rgba(255, 255, 255, 0.9);
      font-size: 16px;

      .feature-icon {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background-color: $accent-color;
        color: $dark-bg;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
      }
    }
  }

  .feature-cards {
    display: flex;
    gap: 24px;
    margin-top: auto;

    .feature-card {
      flex: 1;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      padding: 24px;
      backdrop-filter: blur(10px);

      .card-icon {
        font-size: 32px;
        margin-bottom: 12px;
      }

      h3 {
        color: #ffffff;
        font-size: 18px;
        margin-bottom: 12px;
      }

      p {
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        line-height: 1.6;
      }
    }
  }
}

.login-right {
  width: 500px;
  background-color: $light-bg;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.login-form-container {
  width: 100%;
  max-width: 400px;
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;

  .logo-circle {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background-color: #ff4d4f;
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    font-weight: bold;
  }

  .logo-text {
    .logo-title {
      font-size: 20px;
      font-weight: 500;
      color: $text-primary;
    }

    .logo-subtitle {
      font-size: 12px;
      color: $text-tertiary;
    }
  }
}

.system-title {
  font-size: 20px;
  font-weight: 500;
  color: $text-primary;
  margin-bottom: 8px;
}

.welcome-text {
  font-size: 14px;
  color: $text-tertiary;
  margin-bottom: 32px;
}

.login-form {
  .form-options {
    display: flex;
    justify-content: space-between;
    width: 100%;
  }

  .forgot-password {
    color: $primary-color;
    font-size: 14px;
  }

  .login-button {
    width: 100%;
    height: 40px;
  }
}

.copyright {
  margin-top: 32px;
  text-align: center;
  font-size: 12px;
  color: $text-tertiary;
  line-height: 1.6;
}
</style>
