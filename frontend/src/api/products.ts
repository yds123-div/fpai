/**
 * 产品列表 API：GET /products/search（T033）
 */
import request from '@/utils/request'

export interface ProductsSearchResult {
  products?: unknown[]
  total?: number
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
