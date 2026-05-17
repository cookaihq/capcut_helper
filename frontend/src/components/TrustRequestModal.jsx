import { Alert, Button, Modal, message } from 'antd'
import { useEffect, useState } from 'react'
import { approveOrigin, getConfig } from '../api/client.js'

// native 层（mac NSAppleEventManager / Windows main.py sys.argv handler /
// internal handle-url）收到 capcut-helper://trust?origin=... 后，会通过
// main.py 的 evaluate_js dispatch 这个 CustomEvent，detail = { origin }
const TRUST_EVENT = 'capcut-helper:trust-request'

export default function TrustRequestModal() {
  const [origin, setOrigin] = useState(null)
  const [alreadyTrusted, setAlreadyTrusted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const onTrustRequest = async (e) => {
      const requested = e?.detail?.origin
      if (!requested) return
      // 先查 config 判断是否已被信任，避免对已授权 origin 二次决策骚扰
      try {
        const cfg = await getConfig()
        setAlreadyTrusted(cfg.cors_origins.includes(requested))
      } catch {
        setAlreadyTrusted(false)
      }
      setOrigin(requested)
    }
    window.addEventListener(TRUST_EVENT, onTrustRequest)
    return () => window.removeEventListener(TRUST_EVENT, onTrustRequest)
  }, [])

  const close = () => {
    setOrigin(null)
    setAlreadyTrusted(false)
  }

  const onApprove = async () => {
    setSubmitting(true)
    try {
      await approveOrigin(origin)
      message.success(`已允许 ${origin} 接入剪映助手`)
      close()
    } catch (err) {
      message.error('授权失败：' + (err?.message || '未知错误'))
    } finally {
      setSubmitting(false)
    }
  }

  if (!origin) return null

  if (alreadyTrusted) {
    return (
      <Modal
        open
        title="该网站已被允许"
        onCancel={close}
        footer={[<Button key="ok" type="primary" onClick={close}>知道了</Button>]}
      >
        <p style={{ margin: 0 }}>
          <code style={originBoxStyle}>{origin}</code> 已在 CORS 白名单中，无需重复授权。
        </p>
        <p style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
          可以在「设置 → CORS 白名单」里查看或移除已允许的网站。
        </p>
      </Modal>
    )
  }

  return (
    <Modal
      open
      title="外部网站请求接入剪映助手"
      onCancel={close}
      footer={[
        <Button key="deny" onClick={close} disabled={submitting}>拒绝</Button>,
        <Button key="ok" type="primary" loading={submitting} onClick={onApprove}>
          允许接入
        </Button>,
      ]}
      maskClosable={false}
    >
      <p style={{ marginTop: 0, marginBottom: 12, color: '#666' }}>
        以下网站请求添加到剪映助手的 CORS 白名单：
      </p>
      <div style={originBoxStyle}>{origin}</div>
      <p style={{ marginBottom: 8 }}>允许后，该网站可以通过本机服务：</p>
      <ul style={{ marginTop: 0, marginBottom: 16, paddingLeft: 20, color: '#666' }}>
        <li>查看你的剪映草稿列表</li>
        <li>创建新的剪映草稿（含下载该网站提供的素材到草稿文件夹）</li>
        <li>读取剪映助手当前配置</li>
      </ul>
      <Alert
        type="warning"
        showIcon
        message="仅在你信任该网站时才允许接入"
        description="授权后随时可以在「设置 → CORS 白名单」里移除。如果你不认识这个网站，请点拒绝。"
      />
    </Modal>
  )
}

const originBoxStyle = {
  display: 'block',
  padding: '12px 14px',
  background: '#f5f5f7',
  border: '1px solid #e5e5ea',
  borderRadius: 6,
  marginTop: 0,
  marginBottom: 16,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  fontSize: 13,
  color: '#1d1d1f',
  wordBreak: 'break-all',
}
