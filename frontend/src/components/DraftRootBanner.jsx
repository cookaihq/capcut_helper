import { Alert, Button, Space } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, putConfig } from '../api/client.js'
import { detectDraftRoot } from '../api/bridge.js'

// draft_root 未配置时显示引导横幅。配好后回调 onConfigured 通知父组件并自行隐藏。
export default function DraftRootBanner({ onGoToSettings, onConfigured }) {
  const [needsSetup, setNeedsSetup] = useState(false)
  const [detected, setDetected] = useState(null)

  useEffect(() => {
    getConfig()
      .then(async (cfg) => {
        if (cfg.draft_root) {
          setNeedsSetup(false)
          return
        }
        setNeedsSetup(true)
        const path = await detectDraftRoot()
        if (path) setDetected(path)
      })
      .catch(() => setNeedsSetup(false))
  }, [])

  if (!needsSetup) return null

  const useDetected = async () => {
    const cfg = await getConfig()
    await putConfig({ ...cfg, draft_root: detected })
    setNeedsSetup(false)
    onConfigured && onConfigured()
  }

  if (detected) {
    return (
      <Alert
        type="info"
        showIcon
        message={`检测到剪映草稿目录：${detected}`}
        action={
          <Space>
            <Button size="small" type="primary" onClick={useDetected}>
              使用
            </Button>
            <Button size="small" onClick={onGoToSettings}>
              手动选择
            </Button>
          </Space>
        }
      />
    )
  }

  return (
    <Alert
      type="warning"
      showIcon
      message="还没设置剪映草稿目录，导入会失败"
      action={
        <Button size="small" onClick={onGoToSettings}>
          去设置
        </Button>
      }
    />
  )
}
