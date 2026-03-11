<template>
  <div class="knowledge-view">
    <h1 class="page-title">知识库检索</h1>

    <div class="search-section">
      <a-input
        v-model:value="searchKeyword"
        class="search-input"
        placeholder="请输入检索内容"
        allow-clear
        @pressEnter="handleSearch"
      />
      <a-button type="primary" class="search-btn" :loading="loading" @click="handleSearch">
        <SearchOutlined />
        搜索
      </a-button>
    </div>

    <div class="filter-section">
      <a-select
        v-model:value="knowledgeSource"
        class="filter-select"
        placeholder="知识来源"
        :options="sourceOptions"
        allow-clear
      />
      <a-select
        v-model:value="updateTime"
        class="filter-select"
        placeholder="更新时间"
        :options="updateTimeOptions"
        allow-clear
      />
      <a-select
        v-model:value="sortBy"
        class="filter-select"
        placeholder="最高相关排序"
        :options="sortOptions"
      />
      <a-button class="reset-btn" @click="handleReset">
        <ReloadOutlined />
        重置
      </a-button>
    </div>

    <div v-if="searched" class="results-section">
      <a-empty v-if="!loading && !resultList.length" description="暂无检索结果" />
      <div v-else-if="resultList.length" class="result-list">
        <a-card
          v-for="(item, index) in resultList"
          :key="index"
          size="small"
          class="result-card"
        >
          <template #title>
            <span class="result-title">{{ item.title || '未命名文档' }}</span>
          </template>
          <p class="result-snippet">{{ item.snippet || item.content || '' }}</p>
          <div v-if="item.source" class="result-meta">
            <a-tag>{{ item.source }}</a-tag>
            <span v-if="item.updateTime" class="result-time">{{ item.updateTime }}</span>
          </div>
        </a-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { SearchOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons-vue'

const searchKeyword = ref('')
const loading = ref(false)
const searched = ref(false)
const selectedKnowledgeBase = ref<string | null>(null)
const knowledgeSource = ref<string | undefined>(undefined)
const updateTime = ref<string | undefined>(undefined)
const sortBy = ref('relevance')
const resultList = ref<{ title?: string; snippet?: string; content?: string; source?: string; updateTime?: string }[]>([])

const selectedKnowledgeBaseLabel = ref('全部知识库')

const sourceOptions = [
  { label: '全部来源', value: undefined },
  { label: '产品说明书', value: 'manual' },
  { label: '研报', value: 'report' },
  { label: '监管政策', value: 'policy' },
  { label: '内部文档', value: 'internal' }
]

const updateTimeOptions = [
  { label: '全部时间', value: undefined },
  { label: '最近一天', value: '1d' },
  { label: '最近一周', value: '7d' },
  { label: '最近一月', value: '30d' },
  { label: '最近三月', value: '90d' }
]

const sortOptions = [
  { label: '最高相关排序', value: 'relevance' },
  { label: '最新优先', value: 'time_desc' },
  { label: '最早优先', value: 'time_asc' }
]

function handleSearch() {
  if (!searchKeyword.value?.trim()) return
  searched.value = true
  loading.value = true
  resultList.value = []
  // TODO: 对接知识库检索 API
  setTimeout(() => {
    loading.value = false
    resultList.value = []
  }, 500)
}

function handleReset() {
  searchKeyword.value = ''
  selectedKnowledgeBase.value = null
  selectedKnowledgeBaseLabel.value = '全部知识库'
  knowledgeSource.value = undefined
  updateTime.value = undefined
  sortBy.value = 'relevance'
  resultList.value = []
  searched.value = false
}
</script>

<style scoped lang="scss">
.knowledge-view {
  min-height: 100%;
  padding: 40px 24px;
  background: linear-gradient(180deg, #f0f8ff 0%, #ffffff 30%);
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.85);
  text-align: center;
  margin-bottom: 32px;
}

.search-section {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;

  .search-input {
    flex: 1;
    height: 44px;
    border-radius: 8px;
  }

  .search-btn {
    height: 44px;
    padding-left: 20px;
    padding-right: 20px;
    border-radius: 8px;
  }
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;

  .filter-segment {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    background: #f5f5f5;
    border-radius: 6px;
    border: 1px solid #e8e8e8;

    .filter-label {
      margin-right: 8px;
      color: rgba(0, 0, 0, 0.85);
      font-size: 14px;
    }

    .filter-tag {
      margin: 0;
      background: #fafafa;
      border-left: 1px solid #e8e8e8;
      padding-left: 8px;
      margin-left: 4px;
    }
  }

  .filter-select {
    min-width: 140px;
  }

  .reset-btn {
    color: rgba(0, 0, 0, 0.85);
    background: #f5f5f5;
    border-color: #e8e8e8;
    border-radius: 6px;
  }
}

.results-section {
  max-width: 900px;
  margin: 0 auto;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-card {
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);

  .result-title {
    font-weight: 500;
  }

  .result-snippet {
    color: rgba(0, 0, 0, 0.65);
    font-size: 14px;
    line-height: 1.6;
    margin-bottom: 8px;
  }

  .result-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: rgba(0, 0, 0, 0.45);

    .result-time {
      margin-left: auto;
    }
  }
}
</style>
