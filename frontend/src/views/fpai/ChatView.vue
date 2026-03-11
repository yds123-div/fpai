<template>
  <div class="chat-view">
    <a-typography-title :level="4" style="margin-bottom: 16px">智能对话</a-typography-title>

    <div class="message-list" ref="listRef">
      <template v-for="msg in messages" :key="msg.id">
        <div :class="['message-row', msg.role]">
          <div class="message-bubble">
            <div class="message-content">{{ msg.content }}</div>
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
          <div class="message-content">{{ streamingContent }}</div>
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
import { ref, nextTick } from 'vue'
import { postChatStream } from '@/api/chat'

const listRef = ref(null)
const messages = ref([])
const sessionId = ref(null)
const inputText = ref('')
const loading = ref(false)
const errorMsg = ref('')
const streamingContent = ref('')
const streamCitations = ref([])

let abortStream = null

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
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
  inputText.value = ''
  scrollToBottom()

  loading.value = true
  streamingContent.value = ''
  streamCitations.value = []

  const body = {
    message: text,
    sessionId: sessionId.value || undefined,
    stream: true,
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
      messages.value.push({
        id: data?.answerId || Date.now(),
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
