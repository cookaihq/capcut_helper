import { Alert, Button, Space, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import { getUpdateInfo } from '../api/client.js'
import { openUrl } from '../api/bridge.js'

const NO_ASSET_TOOLTIP = '该 release 未提供下载资产，请用「查看说明」到 release 页查看'

export default function UpdateBanner() {
  const [info, setInfo] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    getUpdateInfo()
      .then((data) => {
        if (data && data.has_update) setInfo(data)
      })
      .catch(() => {
        // 静默：网络失败或本地端点异常都不打扰用户
      })
  }, [])

  if (!info || dismissed) return null

  const downloadDisabled = !info.download_url
  const downloadBtn = (
    <Button
      size="small"
      type="primary"
      disabled={downloadDisabled}
      onClick={() => openUrl(info.download_url)}
    >
      直接下载
    </Button>
  )

  return (
    <Alert
      type="info"
      showIcon
      closable
      onClose={() => setDismissed(true)}
      message={`发现新版本 v${info.latest_version}（当前 v${info.current_version}）`}
      action={
        <Space>
          <Button size="small" onClick={() => openUrl(info.release_url)}>
            查看说明
          </Button>
          {downloadDisabled ? (
            <Tooltip title={NO_ASSET_TOOLTIP}>{downloadBtn}</Tooltip>
          ) : (
            downloadBtn
          )}
        </Space>
      }
    />
  )
}
