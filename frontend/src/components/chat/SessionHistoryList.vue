<template>
  <div class="session-history-list">
    <div class="history-title">历史会话</div>
    <a-spin :spinning="loading">
      <a-empty v-if="!loading && sessions.length === 0" description="暂无历史会话" :image="false" />
      <div v-else class="history-list">
        <div
          v-for="item in sessions"
          :key="item.sessionId"
          class="history-item"
          :class="{ active: currentSessionId === item.sessionId }"
        >
          <button
            type="button"
            class="history-item-main"
            :disabled="chatBusy"
            @click="onSelect(item.sessionId)"
          >
            <div v-if="displayPreview(item.lastMessagePreview)" class="item-preview">
              {{ displayPreview(item.lastMessagePreview) }}
            </div>
            <div class="item-time">{{ formatTime(item.lastMessageAt || item.createdAt) }}</div>
          </button>
          <a-popconfirm
            title="确认删除该历史会话？"
            ok-text="删除"
            cancel-text="取消"
            :disabled="chatBusy || deletingSessionId === item.sessionId"
            @confirm="onDelete(item.sessionId)"
          >
            <button
              type="button"
              class="delete-btn"
              :disabled="chatBusy || deletingSessionId === item.sessionId"
              @click.stop
            >
              {{ deletingSessionId === item.sessionId ? '删除中' : '删除' }}
            </button>
          </a-popconfirm>
        </div>
      </div>
      <div class="history-pagination">
        <a-pagination
          size="small"
          :current="page"
          :page-size="pageSize"
          :total="total"
          :show-size-changer="false"
          @change="onPageChange"
        />
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { deleteSession, listSessions, type SessionListItem } from '@/api/chat'
import { storage } from '@/utils/storage'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const chatBusy = ref(false)
const sessions = ref<SessionListItem[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const deletingSessionId = ref('')
const currentSessionId = computed(() => {
  const sid = String(route.query.sessionId || '')
  return sid || ''
})

async function loadSessions(targetPage = page.value) {
  loading.value = true
  try {
    const data = await listSessions(targetPage, pageSize.value)
    page.value = data.page || targetPage
    pageSize.value = data.pageSize || pageSize.value
    total.value = Number(data.total || 0)
    sessions.value = Array.isArray(data.items) ? data.items : []
  } catch {
    total.value = 0
    sessions.value = []
  } finally {
    loading.value = false
  }
}

function onSelect(sessionId: string) {
  if (chatBusy.value) return
  if (!sessionId) return
  storage.set('chat_session_id', sessionId)
  router.push({ path: '/chat', query: { sessionId } })
}

function onPageChange(p: number) {
  page.value = p
  loadSessions(p)
}

function formatTime(v: string) {
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString()
}

function displayPreview(v: string | null | undefined) {
  const text = String(v || '')
    .replace(/<think>[\s\S]*?<\/think>/gi, ' ')
    .replace(/<think>[\s\S]*$/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text
}

function onChatLoadingChange(ev: Event) {
  const e = ev as CustomEvent<{ loading?: boolean }>
  chatBusy.value = Boolean(e?.detail?.loading)
}

async function onDelete(sessionId: string) {
  if (!sessionId || chatBusy.value) return
  deletingSessionId.value = sessionId
  const started = performance.now()
  try {
    await deleteSession(sessionId)
    const idx = sessions.value.findIndex((x) => x.sessionId === sessionId)
    if (idx >= 0) {
      sessions.value.splice(idx, 1)
    }
    total.value = Math.max(0, total.value - 1)

    const isCurrent = currentSessionId.value === sessionId
    if (isCurrent) {
      storage.remove('chat_session_id')
      await router.replace({ path: '/fpai/chat', query: {} })
    }

    if (sessions.value.length === 0 && page.value > 1 && total.value >= 0) {
      page.value = page.value - 1
      await loadSessions(page.value)
    }
    console.info('[SessionHistoryList] delete session done', {
      sessionId,
      elapsedMs: Math.round(performance.now() - started),
    })
  } catch (e: any) {
    message.error(e?.message || '删除会话失败')
  } finally {
    deletingSessionId.value = ''
  }
}

onMounted(() => {
  // 最稳策略：进入页面后无条件拉取一次历史列表
  loadSessions(page.value)
  window.addEventListener('chat-loading-change', onChatLoadingChange as EventListener)
  window.addEventListener('chat-session-created', onSessionCreated as EventListener)
})

function onSessionCreated() {
  // 新会话首次创建完成后补刷一次列表（保留该优化）
  loadSessions(1)
}

onBeforeUnmount(() => {
  window.removeEventListener('chat-loading-change', onChatLoadingChange as EventListener)
  window.removeEventListener('chat-session-created', onSessionCreated as EventListener)
})
</script>

<style scoped>
.session-history-list {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.history-title {
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
  max-height: 100%;
  padding-right: 2px;
}

.history-item {
  position: relative;
  width: 100%;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.65);
  transition: all 0.2s ease;
  overflow: hidden;
}

.history-item-main {
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item-main:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.history-item:hover {
  background: rgba(24, 144, 255, 0.08);
  border-color: rgba(24, 144, 255, 0.2);
}

.history-item.active {
  background: rgba(24, 144, 255, 0.14);
  border-color: rgba(24, 144, 255, 0.4);
}

.item-preview {
  font-size: 14px;
  line-height: 20px;
  color: rgba(0, 0, 0, 0.85);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-word;
}

.item-time {
  font-size: 12px;
  line-height: 18px;
  color: #8c8c8c;
}

.delete-btn {
  position: absolute;
  right: 8px;
  top: 8px;
  border: none;
  background: rgba(255, 255, 255, 0.92);
  color: #ff4d4f;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.history-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.history-pagination {
  margin-top: 10px;
  display: flex;
  justify-content: center;
}
</style>
