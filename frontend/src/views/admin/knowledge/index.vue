<template>
  <div class="knowledge-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">知识库</h2>
      </div>
      <div class="header-actions">
        <a-button @click="openDialog">外部知识库检索</a-button>
        <a-button type="primary" :loading="syncing" @click="syncBases">同步知识库列表</a-button>
      </div>
    </div>

    <a-card title="已同步知识库列表" style="margin-top: 12px">
      <a-table
        :data-source="knowledgeBaseRows"
        :columns="knowledgeBaseColumns"
        :loading="listLoading"
        row-key="uuid"
        size="small"
        :pagination="{ pageSize: 8, showSizeChanger: false }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'updated_at'">
            {{ record.updated_at || '-' }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button type="link" danger :loading="deletingId === record.uuid" @click="confirmDelete(record)">
              删除
            </a-button>
          </template>
        </template>
      </a-table>
    </a-card>


    <a-card title="知识库对话" style="margin-top: 12px">
      <div class="chat-wrap">
        <div class="chat-config">
          <a-form layout="inline">
            <a-form-item label="模型">
              <a-select v-model:value="chatModel" :options="modelOptions" style="min-width: 180px" />
            </a-form-item>
            <a-form-item label="知识库">
              <a-select
                v-model:value="chatKnowledgeBase"
                :options="knowledgeBaseOptions"
                style="min-width: 360px"
                show-search
                :filter-option="filterOption"
              />
            </a-form-item>
          </a-form>
        </div>

        <div class="chat-body" ref="chatListRef">
          <template v-for="m in chatMessages" :key="m.id">
            <div :class="['chat-row', m.role]">
              <div class="chat-bubble">
                <div class="chat-text" style="white-space: pre-wrap">{{ m.content }}</div>
                <div v-if="m.citations?.length" class="chat-citations">
                  <a-typography-text type="secondary" style="font-size: 12px">引用：</a-typography-text>
                  <div v-for="(c, i) in m.citations" :key="i" class="citation-item">
                    <a-tag v-if="c.source">{{ c.source }}</a-tag>
                    <span class="citation-title">{{ c.title }}</span>
                    <span v-if="c.snippet" class="citation-snippet">{{ String(c.snippet).slice(0, 80) }}…</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <div v-if="chatStreaming" class="chat-row assistant">
            <div class="chat-bubble">
              <div class="chat-text" style="white-space: pre-wrap">{{ chatStreaming }}</div>
              <a-spin size="small" style="margin-left: 8px" />
            </div>
          </div>
        </div>

        <div class="chat-input">
          <a-textarea
            v-model:value="chatInput"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            placeholder="输入问题，回车发送（Shift+Enter 换行）"
            :disabled="chatLoading"
            @pressEnter="handleChatEnter"
          />
          <div class="chat-actions">
            <a-button :disabled="chatLoading" @click="clearChat">清空</a-button>
            <a-button type="primary" :loading="chatLoading" @click="sendChat">发送</a-button>
          </div>
        </div>
      </div>
    </a-card>

    <a-modal
      v-model:open="dialogOpen"
      title="外部知识库检索"
      width="820px"
      :confirm-loading="dialogLoading"
      @ok="handleDialogOk"
      @cancel="handleDialogCancel"
    >
      <div class="dialog-form">
        <a-form layout="vertical">
          <a-form-item label="选择知识库">
            <a-select
              v-model:value="dialogKnowledgeBase"
              :options="knowledgeBaseOptions"
              placeholder="请选择知识库"
              show-search
              :filter-option="filterOption"
            />
          </a-form-item>
          <a-form-item label="提问/检索内容">
            <a-textarea
              v-model:value="dialogQuestion"
              :auto-size="{ minRows: 3, maxRows: 6 }"
              placeholder="请输入要检索的问题或内容"
            />
          </a-form-item>
        </a-form>

        <div v-if="dialogResults.length" class="dialog-result">
          <a-typography-title :level="5">检索结果（{{ dialogResults.length }}）</a-typography-title>
          <div class="dialog-snippets">
            <a-card v-for="(item, index) in dialogResults" :key="index" size="small" class="snippet-card">
              <template #title>
                <span>{{ item.title || `片段 ${index + 1}` }}</span>
              </template>
              <p style="white-space: pre-wrap">{{ item.snippet || item.content || '' }}</p>
              <div class="snippet-meta">
                <a-tag v-if="item.source">{{ item.source }}</a-tag>
                <span v-if="item.score != null">score: {{ item.score }}</span>
              </div>
            </a-card>
          </div>
        </div>
        <a-empty v-else description="暂无检索结果" />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { ExternalKnowledgeItem } from '@/api/knowledge'
import {
  externalKnowledgeSearch,
  listKnowledgeBases,
  syncKnowledgeBases,
  deleteKnowledgeBaseSyncRecord,
  postKnowledgeChatStream
} from '@/api/knowledge'
import { listModels } from '@/api/models'

const syncing = ref(false)
const dialogOpen = ref(false)
const dialogLoading = ref(false)
const dialogModel = ref<string>()
const dialogKnowledgeBase = ref<string>()
const dialogQuestion = ref('')
const dialogResults = ref<ExternalKnowledgeItem[]>([])

const modelOptions = ref<{ label: string; value: string }[]>([])

const knowledgeBaseOptions = ref<{ label: string; value: string }[]>([])
const knowledgeBaseRows = ref<{ uuid: string; name: string; updated_at?: string | null }[]>([])
const listLoading = ref(false)
const deletingId = ref<string>()
const knowledgeBaseColumns = [
  { title: '知识库名称', dataIndex: 'name', key: 'name' },
  { title: '知识库 ID', dataIndex: 'uuid', key: 'uuid' },
  { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 200 },
  { title: '操作', key: 'actions', width: 100 }
]

function filterOption(input: string, option?: { label: string; value: string }) {
  const v = (input || '').toLowerCase()
  const label = (option?.label || '').toLowerCase()
  const value = (option?.value || '').toLowerCase()
  return label.includes(v) || value.includes(v)
}

async function loadKnowledgeBases() {
  listLoading.value = true
  try {
    const res = await listKnowledgeBases(false)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    knowledgeBaseRows.value = items
    // 对话/检索下拉仅展示启用项
    const enabledItems = items.filter((it) => Number(it.enabled ?? 1) === 1)
    knowledgeBaseOptions.value = enabledItems.map((it) => ({ label: it.name, value: it.uuid }))
    if (!dialogKnowledgeBase.value && knowledgeBaseOptions.value.length) {
      dialogKnowledgeBase.value = knowledgeBaseOptions.value[0].value
    }
  } finally {
    listLoading.value = false
  }
}

function confirmDelete(record: { uuid: string; name: string }) {
  Modal.confirm({
    title: '确认删除该同步记录？',
    content: `将仅删除本地同步记录：${record.name}（${record.uuid}），不会删除外部源数据。`,
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      deletingId.value = record.uuid
      try {
        const res = await deleteKnowledgeBaseSyncRecord(record.uuid)
        if (res.data?.deleted) {
          message.success('删除成功')
        } else {
          message.warning('该记录不存在或已删除')
        }
        await loadKnowledgeBases()
      } finally {
        deletingId.value = undefined
      }
    }
  })
}

async function syncBases() {
  syncing.value = true
  try {
    const res = await syncKnowledgeBases()
    const ok = (res.code === 0 || res.code === 200) && res.data?.ok
    if (ok) {
      const cnt = res.data?.count ?? 0
      message.success(`同步成功，共 ${cnt} 条知识库`)
    } else {
      message.error(res.message || res.data?.message || '同步失败')
    }
    await loadKnowledgeBases()
  } finally {
    syncing.value = false
  }
}

function openDialog() {
  dialogOpen.value = true
}

function handleDialogCancel() {
  dialogOpen.value = false
  dialogLoading.value = false
}

async function handleDialogOk() {
  const q = (dialogQuestion.value || '').trim()
  if (!q) return
  dialogLoading.value = true
  dialogResults.value = []
  try {
    const res = await externalKnowledgeSearch({
      model: dialogModel.value || 'default',
      knowledge_base_id: dialogKnowledgeBase.value || '',
      question: q,
      top_k: 5,
    })
    dialogResults.value = Array.isArray(res.data?.items) ? res.data.items : []
  } finally {
    dialogLoading.value = false
  }
}

onMounted(async () => {
  await loadKnowledgeBases()
  try {
    const res = await listModels(true)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    // 下拉展示配置名，实际传 model_id（后端按该配置创建模型调用）
    modelOptions.value = items.map((m) => ({ label: m.name, value: String(m.id) }))
    // 默认选中第一个模型
    if (!chatModel.value && modelOptions.value.length) {
      chatModel.value = modelOptions.value[0].value
    }
  } catch (e) {
    console.error(e)
    modelOptions.value = []
  }
  if (!chatKnowledgeBase.value && knowledgeBaseOptions.value.length) {
    chatKnowledgeBase.value = knowledgeBaseOptions.value[0].value
  }
})

// --------- 知识库对话（流式） ----------
const chatLoading = ref(false)
const chatModel = ref<string>()
const chatKnowledgeBase = ref<string>()
const chatInput = ref('')
const chatMessages = ref<{ id: number | string; role: 'user' | 'assistant'; content: string; citations?: any[] }[]>([])
const chatStreaming = ref('')
const chatCitations = ref<any[]>([])
const chatListRef = ref<HTMLElement | null>(null)
let abortChat: null | (() => void) = null

function scrollChatBottom() {
  requestAnimationFrame(() => {
    if (chatListRef.value) chatListRef.value.scrollTop = chatListRef.value.scrollHeight
  })
}

function clearChat() {
  if (abortChat) {
    try {
      abortChat()
    } catch (_e) {
      // ignore
    } finally {
      abortChat = null
    }
  }
  chatMessages.value = []
  chatStreaming.value = ''
  chatCitations.value = []
}

function handleChatEnter(e: KeyboardEvent) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ev = e as any
  if (!ev.shiftKey) {
    e.preventDefault()
    sendChat()
  }
}

function sendChat() {
  const text = (chatInput.value || '').trim()
  if (!text || chatLoading.value) return
  if (abortChat) {
    try {
      abortChat()
    } catch (_e) {
      // ignore
    } finally {
      abortChat = null
    }
  }
  chatInput.value = ''
  chatMessages.value.push({ id: Date.now(), role: 'user', content: text })
  chatLoading.value = true
  chatStreaming.value = ''
  chatCitations.value = []
  scrollChatBottom()

  abortChat = postKnowledgeChatStream(
    {
      model_id: chatModel.value ? Number(chatModel.value) : undefined,
      knowledge_base_id: chatKnowledgeBase.value || '',
      message: text,
      top_k: 5,
    },
    {
      onCitation(c) {
        chatCitations.value.push(c)
      },
      onMessage(ev) {
        // {text:"..."}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const t = (ev as any)?.text ?? ''
        if (t) chatStreaming.value += t
        scrollChatBottom()
      },
      onDone() {
        const full = chatStreaming.value
        chatStreaming.value = ''
        chatMessages.value.push({
          id: Date.now(),
          role: 'assistant',
          content: full,
          citations: [...chatCitations.value],
        })
        chatCitations.value = []
        chatLoading.value = false
        scrollChatBottom()
      },
      onError(err) {
        chatStreaming.value = ''
        chatCitations.value = []
        chatLoading.value = false
        chatMessages.value.push({
          id: Date.now(),
          role: 'assistant',
          content: err?.message || '请求失败，请重试',
        })
      },
    }
  )
}
</script>

<style scoped lang="scss">
.knowledge-management {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}

.page-desc {
  color: var(--text-secondary, #666);
  font-size: 14px;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.dialog-form {
  .dialog-result {
    margin-top: 16px;
  }
  .dialog-snippets {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 8px;
  }
  .snippet-card {
    .snippet-meta {
      display: flex;
      justify-content: flex-start;
      gap: 8px;
      margin-top: 6px;
      font-size: 12px;
      color: rgba(0, 0, 0, 0.45);
    }
  }
}

.chat-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-config {
  padding: 8px 0;
}

.chat-body {
  height: 360px;
  overflow-y: auto;
  padding: 8px 0;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
}

.chat-row {
  display: flex;
  padding: 8px 12px;
}
.chat-row.user {
  justify-content: flex-end;
}
.chat-row.assistant {
  justify-content: flex-start;
}
.chat-bubble {
  max-width: 85%;
  padding: 10px 12px;
  border-radius: 8px;
  background: #ffffff;
}
.chat-row.user .chat-bubble {
  background: #e6f4ff;
}
.chat-citations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}
.citation-item {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
}
.citation-title {
  margin-left: 6px;
}
.citation-snippet {
  display: block;
  color: rgba(0, 0, 0, 0.45);
  margin-top: 2px;
}

.chat-input {
  border-top: 1px solid #f0f0f0;
  padding-top: 8px;
}
.chat-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
