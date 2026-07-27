---
description: Vue3 前端开发规范
inclusion: fileMatch
fileMatchPattern: 'frontend/**/*.{vue,js,ts}'
---

# Vue3 前端开发规范

## 技术栈

- Vue3 Composition API
- Vite 构建工具
- Ant Design Vue 组件库
- ECharts 图表库
- SSE/WebSocket 流式通信

## 代码风格

- 使用 Composition API（setup script）
- 组件命名使用 PascalCase
- 文件命名使用 kebab-case 或 PascalCase
- 使用 camelCase 命名变量和函数

## 项目结构

```
frontend/
├── src/
│   ├── api/             # API 封装
│   ├── views/           # 页面组件
│   ├── components/      # 通用组件
│   ├── composables/     # 组合式函数
│   ├── router/          # 路由配置
│   └── assets/          # 静态资源
└── package.json
```

## API 调用

- 统一使用 axios
- 请求头携带 `Authorization: Bearer <token>`
- 统一处理响应 envelope（code/message/data）
- 错误统一处理和提示

## SSE 流式处理

- 使用 EventSource 或 fetch API
- 支持事件类型：message、citation、done、error
- 支持断线重连
- 使用 X-Request-Id 实现幂等

## 状态管理

- 优先使用 Composition API 的 reactive/ref
- 复杂状态可使用 Pinia
- Token 和用户信息存储在 localStorage

## 用户体验

- 加载状态提示
- 错误友好提示
- 支持快捷操作
- 响应式设计
