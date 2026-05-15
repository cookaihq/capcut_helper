// 封装 pywebview js_api 桥。浏览器开发环境下 window.pywebview 不存在，做特性检测降级。

export function isBridgeAvailable() {
  return typeof window !== 'undefined' && !!(window.pywebview && window.pywebview.api)
}

export async function pickFolder() {
  if (!isBridgeAvailable()) return null
  return window.pywebview.api.pick_folder()
}

export async function revealInOs(path) {
  if (!isBridgeAvailable()) return
  await window.pywebview.api.reveal_in_os(path)
}

export async function detectDraftRoot() {
  if (!isBridgeAvailable()) return null
  return window.pywebview.api.detect_draft_root()
}

export async function openUrl(url) {
  if (!isBridgeAvailable()) {
    // 浏览器开发态降级：vite dev server 跑前端时没有 pywebview
    window.open(url, '_blank')
    return
  }
  await window.pywebview.api.open_url(url)
}
