<template>
  <div class="chat-view">
    <div class="chat-head">
      <a-typography-title :level="4" style="margin: 0">智能对话</a-typography-title>
      <a-select
        v-model:value="selectedKnowledgeBase"
        :options="knowledgeBaseOptions"
        placeholder="选择知识库（用于其它问题检索）"
        style="min-width: 260px"
        allow-clear
        show-search
        :filter-option="filterOption"
      />
      <a-select
        v-model:value="selectedModel"
        :options="modelOptions"
        placeholder="选择模型"
        style="min-width: 220px"
        allow-clear
      />
    </div>

    <div class="message-list" ref="listRef">
      <template v-for="msg in messages" :key="msg.id">
        <div :class="['message-row', msg.role]">
          <div class="message-bubble">
            <div class="message-content">
              <template v-if="msg.role === 'assistant' && parseThink(msg.content).think">
                <div class="think-block">
                  <div class="think-header">
                    <a-typography-text type="secondary" style="font-size: 14px">思考过程</a-typography-text>
                    <a-button type="link" size="small" @click="toggleThink(msg.id)">
                      {{ thinkExpanded[msg.id] ? '收起' : '展开' }}
                    </a-button>
                  </div>
                  <div v-show="thinkExpanded[msg.id]" style="white-space: pre-wrap">{{ parseThink(msg.content).think }}</div>
                  <div style="white-space: pre-wrap">{{ parseThink(msg.content).answer }}</div>
                </div>
              </template>
              <template v-else>
                {{ msg.content }}
              </template>
            </div>
            <div v-if="msg.citations?.length" class="citations">
              <a-typography-text type="secondary" style="font-size: 12px">引用：</a-typography-text>
              <div v-for="(c, i) in msg.citations" :key="i" class="citation-item">
                <a-tag v-if="c.source">{{ c.source }}</a-tag>
                <span v-if="c.chunk_text" class="chunk-preview">{{ (c.chunk_text || '').slice(0, 80) }}…</span>
              </div>
            </div>
            <div v-if="msg.suggestedQuestions?.length" class="suggested-questions">
              <a-typography-text type="secondary" style="font-size: 12px">猜你想问：</a-typography-text>
              <div class="suggested-btns">
                <a-button
                  v-for="(q, i) in msg.suggestedQuestions"
                  :key="i"
                  size="small"
                  @click="useSuggestedQuestion(q)"
                >
                  {{ q }}
                </a-button>
              </div>
            </div>
          </div>
        </div>
      </template>
      <div v-if="streamingContent" class="message-row assistant">
        <div class="message-bubble">
          <div class="message-content">
            <template v-if="parseThink(streamingContent).think">
              <div class="think-block">
                <div class="think-header">
                  <a-typography-text type="secondary" style="font-size: 14px">思考过程</a-typography-text>
                  <a-button type="link" size="small" @click="streamingThinkExpanded = !streamingThinkExpanded">
                    {{ streamingThinkExpanded ? '收起' : '展开' }}
                  </a-button>
                </div>
                <div v-show="streamingThinkExpanded" style="white-space: pre-wrap">{{ parseThink(streamingContent).think }}</div>
                <div style="white-space: pre-wrap">{{ parseThink(streamingContent).answer }}</div>
              </div>
            </template>
            <template v-else>
              {{ streamingContent }}
            </template>
          </div>
          <a-spin size="small" style="margin-left: 8px" />
        </div>
      </div>
      <div v-if="loading && !streamingContent" class="message-row assistant">
        <div class="message-bubble">
          <a-spin />
        </div>
      </div>
      <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-top: 8px" />
    </div>

    <div class="input-area">
      <a-textarea
        v-model:value="inputText"
        placeholder="输入您的问题…"
        :auto-size="{ minRows: 2, maxRows: 4 }"
        :disabled="loading"
        @pressEnter="handlePressEnter"
      />
      <a-button type="primary" :loading="loading" @click="send" style="margin-top: 8px">
        发送
      </a-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { postChatStream } from '@/api/chat'
import { listModels } from '@/api/models'
import { listKnowledgeBases } from '@/api/knowledge'

const listRef = ref(null)
const messages = ref([])
const sessionId = ref(null)
const inputText = ref('')
const loading = ref(false)
const errorMsg = ref('')
const streamingContent = ref('')
const streamCitations = ref([])
const selectedModel = ref()
const modelOptions = ref([])
const selectedKnowledgeBase = ref()
const knowledgeBaseOptions = ref([])

// 思考过程折叠：默认折叠，用户可点开
// 注意：本文件未开启 TS 语法，因此这里保持纯 JS 写法
const thinkExpanded = ref({})

// 流式阶段：默认折叠
const streamingThinkExpanded = ref(false)

let abortStream = null

function filterOption(input, option) {
  const v = (input || '').toLowerCase()
  const label = (option?.label || '').toLowerCase()
  const value = (String(option?.value || '')).toLowerCase()
  return label.includes(v) || value.includes(v)
}

async function loadModels() {
  try {
    const res = await listModels(true)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    // 下拉展示配置名，实际传 model_id（后端按该配置创建模型调用）
    modelOptions.value = items.map((m) => ({ label: m.name, value: m.id }))
    if (!selectedModel.value && modelOptions.value.length) selectedModel.value = modelOptions.value[0].value
  } catch (e) {
    console.error(e)
    modelOptions.value = []
  }
}

async function loadKnowledgeBases() {
  try {
    const res = await listKnowledgeBases(true)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    knowledgeBaseOptions.value = items.map((it) => ({ label: it.name, value: it.uuid }))
    if (!selectedKnowledgeBase.value && knowledgeBaseOptions.value.length) {
      selectedKnowledgeBase.value = knowledgeBaseOptions.value[0].value
    }
  } catch (e) {
    console.error(e)
    knowledgeBaseOptions.value = []
  }
}

onMounted(() => {
  loadModels()
  loadKnowledgeBases()
})

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function useSuggestedQuestion(q) {
  inputText.value = typeof q === 'string' ? q : (q?.text || '')
  send()
}

function parseThink(content) {
  const s = (content || '').toString()
  // 1) 标准 thinking：<think>...</think>
  let m = s.match(/<think\s*>\s*([\s\S]*?)\s*<\/think>/i)

  // 2) 当前模型常见包裹：<opt switching>...</opt switching>
  // 注意：这里必须匹配 “opt + 空格 + switching”，避免误伤普通 <opt>。
  if (!m) {
    m = s.match(/<opt\s+switching\s*>\s*([\s\S]*?)\s*<\/opt\s+switching\s*>/i)
  }

  if (!m) return { think: '', answer: s }
  const think = m[1] || ''
  const answer = (s.replace(m[0], '') || '').trim()
  return { think, answer }
}

function toggleThink(id) {
  if (!id) return
  thinkExpanded.value[id] = !thinkExpanded.value[id]
}

function handlePressEnter(e) {
  if (!e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function send() {
  const text = (inputText.value || '').trim()
  if (!text || loading.value) return

  errorMsg.value = ''
  messages.value.push({ id: Date.now(), role: 'user', content: text })
  // a-textarea 的 @pressEnter 触发时机可能早于 v-model 更新；
  // 这里做一次“立即清空 + 下一帧再清空”，确保输入框可见值被清掉。
  inputText.value = ''
  nextTick(() => {
    inputText.value = ''
  })
  scrollToBottom()

  loading.value = true
  streamingContent.value = ''
  streamCitations.value = []

  const body = {
    message: text,
    sessionId: sessionId.value || undefined,
    stream: true,
    model_id: selectedModel.value || undefined,
    knowledge_base_id: selectedKnowledgeBase.value || undefined,
    showThinking: true,
  }

  abortStream = postChatStream(body, {
    onMessage(ev) {
      const t = ev?.text ?? (typeof ev === 'string' ? ev : '')
      if (t) streamingContent.value += t
      scrollToBottom()
    },
    onCitation(c) {
      streamCitations.value.push(c)
    },
    onDone(data) {
      if (data?.sessionId) sessionId.value = data.sessionId
      const fullText = streamingContent.value || ''
      streamingContent.value = ''
      const citations = [...streamCitations.value]
      streamCitations.value = []
      const suggestedQuestions = Array.isArray(data?.suggestedQuestions) ? data.suggestedQuestions : []

      const aid = data?.answerId || String(Date.now())
      thinkExpanded.value[aid] = false
      messages.value.push({
        id: aid,
        role: 'assistant',
        content: fullText,
        citations,
        answerId: data?.answerId,
        suggestedQuestions,
      })
      loading.value = false
      scrollToBottom()
    },
    onError(err) {
      streamingContent.value = ''
      loading.value = false
      errorMsg.value = err?.message || '请求失败，请重试'
    },
  })
}
</script>

<style scoped>
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.chat-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  max-height: 720px;
  margin: 32px;
  padding: 32px;
  background-color: white;
  border-radius: 16px;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}
.message-row {
  display: flex;
  margin-bottom: 12px;
}
.message-row.user {
  justify-content: flex-end;
}
.message-row.assistant {
  justify-content: flex-start;
}
.message-bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 8px;
  background: #f5f5f5;
}
.message-row.user .message-bubble {
  background: #e6f4ff;
}
.message-content {
  white-space: pre-wrap;
  word-break: break-word;
}
.citations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}
.citation-item {
  margin-top: 4px;
  font-size: 12px;
  color: #666;
}
.chunk-preview {
  display: block;
  margin-top: 2px;
}
.suggested-questions {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}
.suggested-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.input-area {
  flex-shrink: 0;
  padding: 12px 0;
  border-top: 1px solid #eee;
}
</style>
