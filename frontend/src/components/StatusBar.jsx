import { useEffect, useState } from 'react'
import { getHealth } from '../api/client.js'
import { relativeTime } from '../utils/time.js'

export default function StatusBar() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const load = () => getHealth().then(setHealth).catch(() => setHealth(null))
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const online = !!health
  const lastReq = health && health.last_draft_request_at

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 16px',
        background: '#1f1f1f',
        color: '#bbb',
        fontSize: 12,
      }}
    >
      <span>
        <span style={{ color: online ? '#52c41a' : '#ff4d4f' }}>●</span>{' '}
        {online
          ? `服务运行中 · 端口 ${health.port}${health.version ? ` · v${health.version}` : ''}`
          : '连接本地服务中…'}
      </span>
      <span>
        {lastReq
          ? `最近导入请求：${relativeTime(lastReq)}`
          : '尚无导入请求'}
      </span>
    </div>
  )
}
