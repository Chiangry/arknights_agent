// 统一的后端地址与请求封装
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string) || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function parseJson(res: Response) {
  const text = await res.text()
  try {
    return text ? JSON.parse(text) : {}
  } catch {
    return { raw: text }
  }
}

export async function request<T = any>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json', ...(init.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await parseJson(res)
    throw new ApiError(res.status, body.detail || body.message || `请求失败 ${res.status}`)
  }
  return parseJson(res) as Promise<T>
}
