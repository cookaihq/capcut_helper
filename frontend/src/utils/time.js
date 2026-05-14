// 把 epoch 秒数格式化成中文相对时间。now 默认取当前时间（秒），可注入便于测试。
export function relativeTime(epochSeconds, now = Date.now() / 1000) {
  const diff = Math.max(0, now - epochSeconds)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}
