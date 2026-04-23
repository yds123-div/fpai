<template>
  <div class="chat-view">
    <div class="chat-head">
      <a-typography-title :level="4" style="margin: 0">智能对话</a-typography-title>
      <a-select
        v-model:value="selectedModel"
        :options="modelOptions"
        placeholder="选择模型"
        style="min-width: 150px"
        allow-clear
      />
    </div>

    <div class="message-list" ref="listRef" @scroll="onListScroll">
      <template v-for="msg in messages" :key="msg.id">
        <div :class="['message-row', msg.role]">
          <div class="message-bubble">
            <details
              v-if="msg.role === 'assistant' && msg.thinking"
              class="thinking-panel"
            >
              <summary>
                <span class="thinking-title">模型思考过程</span>
                <span class="thinking-hint">（点击展开/折叠）</span>
              </summary>
              <div class="thinking-content">{{ msg.thinking }}</div>
            </details>
            <div class="message-content">
              <template v-if="msg.role === 'assistant' && msg.fundAnalysis">
                <FundAnalysis :analysis="msg.fundAnalysis" />
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
      <div v-if="streamingRaw" class="message-row assistant">
        <div class="message-bubble">
          <details
            v-if="streamingThinking"
            class="thinking-panel"
            :open="streamingOpenThinking"
          >
            <summary @click.prevent="streamingOpenThinking = !streamingOpenThinking">
              <span class="thinking-title">模型思考中…</span>
              <span class="thinking-hint">（点击展开/折叠）</span>
            </summary>
            <div class="thinking-content">{{ streamingThinking }}</div>
          </details>
          <div v-if="streamingAnswer" class="message-content">
            {{ streamingAnswer }}
          </div>
          <a-spin size="small" style="margin-left: 8px" />
        </div>
      </div>
      <div v-if="loading && !streamingRaw" class="message-row assistant">
        <div class="message-bubble">
          <a-spin />
          <span v-if="progressStatus" style="margin-left: 8px; color: #999;">{{ progressStatus }}</span>
        </div>
      </div>
      <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-top: 8px" />
    </div>

    <div class="input-area">
      
      <a-textarea
        v-model:value="inputText"
        placeholder="请输入您的问题…"
        :auto-size="{ minRows: 2, maxRows: 4 }"
        :disabled="loading"
        @pressEnter="handlePressEnter"
        class="composer-input"
      />
        
      <div class="composer">
        <div class="composer-actions-start">
          <a-select
            v-model:value="selectedKnowledgeBase"
            :options="knowledgeBaseOptions"
            placeholder="选择知识库"
            allow-clear
            show-search
            :filter-option="filterOption"
            class="composer-kb"
          />
        </div>
        <div class="composer-actions-end">
          <a-button type="primary" :loading="loading" @click="send" class="composer-send">
            发送
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { postChatStream, getSessionMessages } from '@/api/chat'
import { listModels } from '@/api/models'
import { listKnowledgeBases } from '@/api/knowledge'
import FundAnalysis from '@/components/fund/FundAnalysis.vue'
import { extractStructuredOutput, parseFundAnalysis } from '@/utils/fundAnalysisParser'
import { storage } from '@/utils/storage'

const SESSION_STORAGE_KEY = 'chat_session_id'

const listRef = ref(null)
const messages = ref([])
const sessionId = ref(null)
const inputText = ref('')
const loading = ref(false)
const errorMsg = ref('')
// streamingRaw 保存当前流式返回的原始文本（包含 <think>...</think>），
// 由 computed 派生出思考区与正文区，供折叠面板与正文分别展示。
const streamingRaw = ref('')
const streamingOpenThinking = ref(true)
const streamCitations = ref([])
const progressStatus = ref('')
// 用户是否贴近底部（用于智能滚动）：贴近则自动滚动，上滑查看则不打扰
const pinnedToBottom = ref(true)

// 进度状态中文映射
const PROGRESS_MESSAGES = {
  'accepted': '请求已接受',
  'coordinator_skill_fetching': '正在准备数据...',
  'coordinator_planning': '正在规划任务...',
  'skill_fetching': '正在获取相关信息...',
  'llm_generating': '正在生成回复...',
}

const selectedModel = ref()
const modelOptions = ref([])
const selectedKnowledgeBase = ref()
const knowledgeBaseOptions = ref([])

let abortStream = null

function extractFundCodes(text) {
  const s = (text || '').toString()
  const m = s.match(/\b\d{6}\b/g)
  if (!m) return []
  // 去重并保持顺序
  const seen = new Set()
  const out = []
  for (const code of m) {
    if (seen.has(code)) continue
    seen.add(code)
    out.push(code)
  }
  return out
}

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
  restoreSession()
})

/**
 * 从原始文本中拆分出 <think>...</think> 推理段与正文段。
 * - 完整闭合的 think 块 → 进入 thinking
 * - 未闭合的 <think> 到结尾 → 也视为 thinking（流式过程中展示）
 * 其他部分 → 正文 answer
 */
function splitThink(raw) {
  const text = String(raw || '')
  if (!text) return { answer: '', thinking: '' }
  let answer = ''
  const thinkingParts = []
  let i = 0
  while (i < text.length) {
    const j = text.indexOf('<think>', i)
    if (j === -1) {
      answer += text.slice(i)
      break
    }
    answer += text.slice(i, j)
    const k = text.indexOf('</think>', j + 7)
    if (k === -1) {
      thinkingParts.push(text.slice(j + 7))
      break
    }
    thinkingParts.push(text.slice(j + 7, k))
    i = k + 8
  }
  return { answer: answer, thinking: thinkingParts.join('\n\n').trim() }
}

const streamingParsed = computed(() => splitThink(streamingRaw.value))
const streamingAnswer = computed(() => streamingParsed.value.answer)
const streamingThinking = computed(() => streamingParsed.value.thinking)

function onListScroll() {
  const el = listRef.value
  if (!el) return
  pinnedToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom(force = false) {
  nextTick(() => {
    const el = listRef.value
    if (!el) return
    if (force || pinnedToBottom.value) {
      el.scrollTop = el.scrollHeight
      pinnedToBottom.value = true
    }
  })
}

async function restoreSession() {
  const saved = storage.get(SESSION_STORAGE_KEY)
  if (!saved || typeof saved !== 'string') return
  try {
    const data = await getSessionMessages(saved, 50)
    const items = Array.isArray(data?.items) ? data.items : []
    const restored = items
      .filter((it) => it && (it.role === 'user' || it.role === 'assistant'))
      .map((it, idx) => {
        const content = String(it.full_content || it.content_summary || '')
        if (it.role === 'assistant') {
          const { answer, thinking } = splitThink(content)
          return {
            id: it.answer_id || `hist-${idx}`,
            role: 'assistant',
            content: answer,
            thinking,
            answerId: it.answer_id || undefined,
          }
        }
        return { id: `hist-${idx}`, role: 'user', content }
      })
    messages.value = restored
    sessionId.value = saved
    scrollToBottom(true)
  } catch (e) {
    // 会话已失效或后端异常：清理本地缓存，不打扰用户
    storage.remove(SESSION_STORAGE_KEY)
  }
}

function useSuggestedQuestion(q) {
  inputText.value = typeof q === 'string' ? q : (q?.text || '')
  send()
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
  // 用户刚发送消息：强制滚动到底部
  scrollToBottom(true)

  loading.value = true
  streamingRaw.value = ''
  streamCitations.value = []
  progressStatus.value = ''
  streamingOpenThinking.value = true

  const body = {
    message: text,
    sessionId: sessionId.value || undefined,
    stream: true,
    // 若用户在问题中直接输入基金代码，则自动填充 productIds，
    // 以触发后端的基金分析结构化输出（cards/sections/charts）。
    productIds: extractFundCodes(text) || undefined,
    model_id: selectedModel.value || undefined,
    knowledge_base_id: selectedKnowledgeBase.value || undefined,
    // 打开思考过程输出：前端通过折叠面板展示，不影响正文答案。
    showThinking: true,
  }

  abortStream = postChatStream(body, {
    onStatus(data) {
      const stage = data?.stage || ''
      const message = data?.message || ''
      // 优先使用 message，否则使用映射的中文，最后才用原始 stage
      progressStatus.value = message || PROGRESS_MESSAGES[stage] || stage
    },
    onMessage(ev) {
      const t = ev?.text ?? (typeof ev === 'string' ? ev : '')
      if (t) streamingRaw.value += t
      scrollToBottom()
    },
    onCitation(c) {
      streamCitations.value.push(c)
    },
    onDone(data) {
      progressStatus.value = ''
      if (data?.sessionId) {
        sessionId.value = data.sessionId
        storage.set(SESSION_STORAGE_KEY, data.sessionId)
      }
      const fullRaw = streamingRaw.value || ''
      streamingRaw.value = ''
      const { answer: answerText, thinking: thinkingText } = splitThink(fullRaw)
      const citations = [...streamCitations.value]
      streamCitations.value = []
      const suggestedQuestions = Array.isArray(data?.suggestedQuestions) ? data.suggestedQuestions : []

      const structured = extractStructuredOutput(data?.structuredOutputs)
      const parsedFromText = structured ? null : parseFundAnalysis(answerText)
      const fundAnalysis = structured || parsedFromText

      const aid = data?.answerId || String(Date.now())
      messages.value.push({
        id: aid,
        role: 'assistant',
        content: answerText,
        thinking: thinkingText,
        citations,
        answerId: data?.answerId,
        suggestedQuestions,
        fundAnalysis,
      })
      loading.value = false
      scrollToBottom()
    },
    onError(err) {
      streamingRaw.value = ''
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
.thinking-panel {
  margin-bottom: 8px;
  padding: 6px 10px;
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
}
.thinking-panel > summary {
  cursor: pointer;
  outline: none;
  user-select: none;
  color: #666;
  font-size: 12px;
}
.thinking-title {
  font-weight: 500;
  margin-right: 6px;
}
.thinking-hint {
  color: #999;
}
.thinking-content {
  margin-top: 6px;
  padding: 6px 4px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #555;
  font-size: 12px;
  max-height: 260px;
  overflow-y: auto;
  border-top: 1px dashed #e8e8e8;
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

.composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.composer-input {
  flex: 1;
}
.composer-actions-start {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  justify-content: flex-start;
  flex-shrink: 0;
}

.composer-actions-end {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  justify-content: flex-end;
  flex-shrink: 0;
}

.composer-kb {
  min-width: 10%;
}

.composer-send {
  min-width: 92px;
}

@media (max-width: 768px) {
  .composer {
    flex-direction: column;
    align-items: stretch;
  }
  .composer-actions {
    width: 100%;
    justify-content: space-between;
  }
  .composer-kb {
    min-width: 0;
    flex: 1;
  }
}
</style>
