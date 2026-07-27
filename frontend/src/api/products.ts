/**
 * 产品列表 API：GET /products/search（T033）
 */
import request from '@/utils/request'

export interface ProductsSearchResult {
  products?: unknown[]
  total?: number
}

export interface ProductsSyncResult {
  limit?: number
  received?: number
  valid?: number
  affected?: number
}

export async function getProductsSearch(
  params: Record<string, unknown> = {}
): Promise<ProductsSearchResult> {
  const res = await request.get<ProductsSearchResult>('/products/search', { params })
  if (res.code !== 200) {
    throw new Error((res.message as string) || '产品列表获取失败')
  }
  return (res.data ?? { products: [], total: 0 }) as ProductsSearchResult
}

export async function syncFundProducts(
  params: Record<string, unknown> = {}
): Promise<ProductsSyncResult> {
  const res = await request.post<ProductsSyncResult>('/products/sync', null, { params })
  if (res.code !== 200) {
    throw new Error((res.message as string) || '基金产品同步失败')
  }
  return (res.data ?? {}) as ProductsSyncResult
}
