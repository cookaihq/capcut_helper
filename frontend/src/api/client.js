const BASE = '/api/v1'

async function request(path, options) {
  const resp = await fetch(BASE + path, options)
  const body = await resp.json()
  if (body.code !== 0) {
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    err.data = body.data
    throw err
  }
  return body.data
}

export const getHealth = () => request('/health')
export const getTasks = () => request('/tasks')
export const getDrafts = () => request('/drafts')
export const getConfig = () => request('/config')
export const putConfig = (cfg) =>
  request('/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
export const getUpdateInfo = () => request('/update/check')
export const approveOrigin = (origin) =>
  request('/cors-origins', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin }),
  })
export const restartApp = () => request('/system/restart', { method: 'POST' })
