/**
 * API 模块统一导出（T033：对话页与 API 封装）
 * 与后端交互统一使用 @/utils/request
 */
export { login, logout, getUserInfo, type LoginResponse, type UserInfo } from './auth'
export { postChatNonStream, postChatStream, type ChatStreamCallbacks } from './chat'
export { postCompare } from './compare'
export { postRecommend } from './recommend'
export { postReportGenerate } from './report'
export { getEvidence } from './evidence'
export { postFeedback } from './feedback'
export { getProductsSearch, type ProductsSearchResult } from './products'
