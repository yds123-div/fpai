# 前端进度反馈事件修复

## 问题描述

用户在前端没有看到进度反馈事件，导致在等待 AI 响应时缺少状态提示。

## 根本原因

后端发送的是 `status` 事件，但前端只监听了 `message`、`citation`、`done`、`error` 事件，没有处理 `status` 事件。

### 后端实现（已存在）

在 `backend/api/routes/chat.py` 中：

```python
async def _progress(stage: str, **kwargs):
    """接收编排器的进度事件"""
    message = kwargs.get("message", "")
    await _emit("status", {"stage": stage, "message": message})

# SSE 流中发送
if ev == "status":
    # 进度事件（前端可选显示；不影响现有 message/citation/done 处理）
    yield _sse_event("status", payload).encode("utf-8")
```

### 前端问题（修复前）

在 `frontend/src/api/chat.ts` 中：

```typescript
// 只处理了这些事件
if (currentEvent === 'message') onMessage?.(data)
else if (currentEvent === 'citation') onCitation?.(data)
else if (currentEvent === 'done') onDone?.(data)
else if (currentEvent === 'error') onError?.(...)
// ❌ 缺少 status 事件处理
```

## 解决方案

### 1. 修改 API 层（chat.ts）

#### 添加 onStatus 回调

```typescript
export interface ChatStreamCallbacks {
  onMessage?: (data: unknown) => void
  onCitation?: (data: unknown) => void
  onStatus?: (data: { stage?: string; message?: string }) => void  // ✅ 新增
  onDone?: (data: unknown) => void
  onError?: (data: { code?: number; message?: string }) => void
}
```

#### 处理 status 事件

```typescript
export function postChatStream(
  body: Record<string, unknown>,
  { onMessage, onCitation, onStatus, onDone, onError }: ChatStreamCallbacks = {}
): () => void {
  // ...
  if (currentEvent === 'message') onMessage?.(data)
  else if (currentEvent === 'citation') onCitation?.(data)
  else if (currentEvent === 'status') onStatus?.(data as { stage?: string; message?: string })  // ✅ 新增
  else if (currentEvent === 'done') onDone?.(data)
  else if (currentEvent === 'error') onError?.(...)
}
```

### 2. 修改视图层（ChatView.vue）

#### 添加进度状态变量

```javascript
const progressStatus = ref('')
```

#### 监听 status 事件

```javascript
abortStream = postChatStream(body, {
  onStatus(data) {
    const stage = data?.stage || ''
    const message = data?.message || ''
    progressStatus.value = message || stage
  },
  onMessage(ev) {
    // ...
  },
  onDone(data) {
    progressStatus.value = ''  // 清空进度状态
    // ...
  }
})
```

#### 显示进度状态

```vue
<div v-if="loading && !streamingContent" class="message-row assistant">
  <div class="message-bubble">
    <a-spin />
    <span v-if="progressStatus" style="margin-left: 8px; color: #999;">
      {{ progressStatus }}
    </span>
  </div>
</div>
```

## 进度事件类型

后端发送的进度事件（stage）包括：

| Stage | 说明 |
|-------|------|
| `accepted` | 请求已接受 |
| `coordinator_skill_fetching` | 任务规划器正在获取技能数据 |
| `coordinator_planning` | 任务规划中 |
| `skill_fetching` | Agent 正在获取技能数据 |
| `llm_generating` | LLM 正在生成回复 |

## 效果展示

### 修复前

```
用户: 000010和000013的对比
[转圈加载，无任何提示]
```

###修复后

```
用户: 000010和000013的对比
[转圈加载] 任务规划中...
[转圈加载] LLM 正在生成回复...
AI: [开始流式输出内容]
```

## 其他视图的修复

类似的修复也应该应用到其他使用流式 API 的视图：

### CompareView.vue

```typescript
export interface CompareStreamCallbacks {
  onMessage?: (data: { text?: string }) => void
  onStatus?: (data: { stage?: string; message?: string }) => void  // 新增
  onDone?: (data: unknown) => void
  onError?: (data: { code?: number; message?: string }) => void
}
```

### RecommendView.vue

```typescript
export interface RecommendStreamCallbacks {
  onMessage?: (data: { text?: string }) => void
  onStatus?: (data: { stage?: string; message?: string }) => void  // 新增
  onDone?: (data: unknown) => void
  onError?: (data: { code?: number; message?: string }) => void
}
```

### KnowledgeView (admin)

```typescript
// 知识库测试页面也需要类似修复
```

## 验证步骤

### 1. 启动服务

```bash
# 后端
cd backend
uvicorn main:app --reload

# 前端
cd frontend
npm run dev
```

### 2. 测试进度显示

1. 打开聊天页面
2. 输入问题："000010和000013的对比"
3. 观察加载状态下方是否显示进度提示

### 3. 检查控制台

打开浏览器开发者工具，查看 Network 标签中的 SSE 事件：

```
event: status
data: {"stage":"coordinator_planning","message":""}

event: status
data: {"stage":"llm_generating","message":""}

event: message
data: {"text":"根据"}

event: done
data: {"sessionId":"...","answerId":"..."}
```

## 影响范围

### 修改的文件

- `frontend/src/api/chat.ts` - 添加 status 事件处理
- `frontend/src/views/fpai/ChatView.vue` - 显示进度状态
- `docs/progress_event_fix.md` - 本文档

### 待修改的文件（建议）

- `frontend/src/api/compare.ts` - 对比页面
- `frontend/src/api/recommend.ts` - 推荐页面
- `frontend/src/api/knowledge.ts` - 知识库测试页面
- `frontend/src/views/fpai/CompareView.vue`
- `frontend/src/views/fpai/RecommendView.vue`
- `frontend/src/views/admin/knowledge/index.vue`

## 后续优化建议

### 1. 国际化进度消息

将 stage 映射为用户友好的中文提示：

```typescript
const STAGE_MESSAGES: Record<string, string> = {
  'accepted': '请求已接受',
  'coordinator_skill_fetching': '正在准备数据...',
  'coordinator_planning': '正在规划任务...',
  'skill_fetching': '正在获取相关信息...',
  'llm_generating': '正在生成回复...',
}

onStatus(data) {
  const stage = data?.stage || ''
  progressStatus.value = STAGE_MESSAGES[stage] || data?.message || stage
}
```

### 2. 进度条动画

使用 Ant Design 的 Progress 组件显示更友好的进度：

```vue
<a-progress 
  v-if="progressStatus" 
  :percent="progressPercent" 
  :status="'active'"
  :show-info="false"
  size="small"
/>
<span>{{ progressStatus }}</span>
```

### 3. 超时提示

如果某个阶段停留时间过长，给出友好提示：

```typescript
let progressTimer: NodeJS.Timeout | null = null

onStatus(data) {
  if (progressTimer) clearTimeout(progressTimer)
  progressStatus.value = data?.message || data?.stage
  
  progressTimer = setTimeout(() => {
    if (progressStatus.value) {
      progressStatus.value += '（处理中，请稍候...）'
    }
  }, 10000) // 10秒后提示
}
```

## 相关资源

- [SSE 规范](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Ant Design Progress](https://antdv.com/components/progress-cn)
- [后端 SSE 实现](../backend/api/routes/chat.py)

## 更新日期

2026-04-10
