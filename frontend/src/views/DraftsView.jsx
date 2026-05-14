import { Button, Empty, List } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, getDrafts } from '../api/client.js'
import { revealInOs } from '../api/bridge.js'

export default function DraftsView() {
  const [drafts, setDrafts] = useState([])
  const [draftRoot, setDraftRoot] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([getDrafts(), getConfig()])
      .then(([names, cfg]) => {
        setDrafts(names)
        setDraftRoot(cfg.draft_root)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div>
      <Button size="small" onClick={load} loading={loading} style={{ marginBottom: 8 }}>
        刷新
      </Button>
      {drafts.length === 0 ? (
        <Empty
          description={
            draftRoot ? '草稿根目录下还没有草稿' : '未配置剪映草稿目录'
          }
        />
      ) : (
        <List
          size="small"
          bordered
          dataSource={drafts}
          renderItem={(name) => (
            <List.Item
              actions={[
                <Button
                  key="reveal"
                  size="small"
                  type="link"
                  onClick={() => revealInOs(`${draftRoot}/${name}`)}
                >
                  在访达/资源管理器打开
                </Button>,
              ]}
            >
              {name}
            </List.Item>
          )}
        />
      )}
    </div>
  )
}
