<template>
  <div class="home-page">
    <div class="welcome-section">
      <h1 class="welcome-title">Hi，我是金融产品解析智能体</h1>
      <p class="welcome-subtitle">面向客户经理：随问随答、答得准、答得稳、答得合规；快速对比、快速匹配、快速出稿</p>
    </div>
    <div class="assistant-cards">
      <div
        v-for="(card, index) in assistantCards"
        :key="index"
        class="assistant-card"
      >
        <div class="card-header">
          <h3 class="card-title">{{ card.title }}</h3>
          <!-- <a-button type="link" size="small" class="refresh-btn">
            <ReloadOutlined />
            换一换
          </a-button> -->
        </div>
        <div class="card-content">
          <p class="card-description">{{ card.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
interface AssistantCard {
  title: string
  description: string
}

const assistantCards = ref<AssistantCard[]>([
  {
    title: '产品要素解读',
    description: '输入产品名称或具体问题，秒级获取风险等级、期限、费率、投向、业绩基准等结构化要点与通俗解释，并附带引用来源。支持多轮追问与上下文记忆，满足客户面谈、售中答疑、投后解释等场景，做到随问随答、答得准、答得合规。'
  },
  {
    title: '多产品对比与智能推荐',
    description: '选择多只产品一键生成结构化对比表（风险/期限/费率/投向/赎回规则/适配客群等），差异高亮、支持导出与复制；或输入客户期限、流动性、风险偏好与收益目标，从可售产品池中检索 TopN 适配产品及推荐理由，含约束说明与引用依据，实现快速对比、快速匹配。'
  },
  {
    title: '研报·政策·观点摘要',
    description: '输入主题或时间范围，自动检索行业研报、市场观点、监管政策与内部投研报告，输出摘要、要点、关键结论与引用来源（文档标题、段落、时间），支撑「最近市场怎么走、监管有什么新口径、有哪些重点研报观点」等问答与话术准备。'
  },
  {
    title: '周报月报与解读稿生成',
    description: '一键生成财富周报、月报或市场解读稿，模板化分块输出（标题/摘要/要点/风险提示/参考来源），支持在线编辑与复制导出。每次输出可追溯、可审计，满足快速出稿与合规要求，并可对答案进行有用/无用反馈以持续优化。'
  }
])
</script>

<style scoped lang="scss">
.home-page {
  padding: 40px;
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
  z-index: 1;
}

.welcome-section {
  text-align: center;
  margin-bottom: 48px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: -20px;
    left: 50%;
    transform: translateX(-50%);
    width: 120px;
    height: 4px;
    background: linear-gradient(90deg, transparent, $accent-color, transparent);
    border-radius: 2px;
  }

  .welcome-title {
    font-size: 36px;
    font-weight: 600;
    background: linear-gradient(135deg, $text-primary 0%, $primary-color 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 16px;
    position: relative;
  }

  .welcome-subtitle {
    font-size: 16px;
    color: $text-secondary;
    font-weight: 400;
  }
}

.assistant-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.assistant-card {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  border: 1px solid rgba($primary-color, 0.15);
  border-radius: 12px;
  padding: 24px;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, $accent-color, $primary-color);
    opacity: 0;
    transition: opacity 0.3s;
  }

  &:hover {
    border-color: $primary-color;
    box-shadow: 0 8px 24px rgba($primary-color, 0.15);
    transform: translateY(-2px);

    &::before {
      opacity: 1;
    }
  }

  .card-header {
    @include flex-between;
    margin-bottom: 16px;

    .card-title {
      font-size: 16px;
      font-weight: 500;
      color: $text-primary;
      margin: 0;
    }

    .refresh-btn {
      color: $primary-color;
      padding: 0;
    }
  }

  .card-content {
    .card-description {
      margin: 0;
      color: $text-secondary;
      font-size: 14px;
      line-height: 1.7;
      text-align: justify;
    }
  }
}
</style>
