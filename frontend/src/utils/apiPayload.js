/**
 * API 响应载荷解析工具
 *
 * 后端列表接口存在三种返回结构，前端误将整个分页对象绑定到 v-for
 * 会触发 `TypeError: can't access property "id", p is null`
 * （Vue 会迭代对象 key，从而拿到 next/previous 这种值为 null 的字段）。
 *
 * 在所有列表加载处统一调用 `extractListPayload`，避免再次踩坑。
 *
 * 支持的输入：
 * 1) DRF 默认分页：{ count, next, previous, results: [...] }
 * 2) 项目统一包装：{ success, data: [...] }
 *                  或 { success, data: { count, next, previous, results: [...] } }
 *                  或 { success, data: { items: [...], pagination: {...} } }
 * 3) 直接数组：    [...]
 */
export const extractListPayload = (res) => {
  if (Array.isArray(res)) return res
  if (Array.isArray(res?.results)) return res.results
  if (Array.isArray(res?.data?.results)) return res.data.results
  if (Array.isArray(res?.data?.items)) return res.data.items
  if (Array.isArray(res?.items)) return res.items
  if (Array.isArray(res?.data)) return res.data
  return []
}
