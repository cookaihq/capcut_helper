import { Button, Form, Input, InputNumber, Select, Space, message } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, putConfig } from '../api/client.js'
import { detectDraftRoot, isBridgeAvailable, pickFolder } from '../api/bridge.js'

export default function SettingsView({ onSaved }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const bridgeOn = isBridgeAvailable()

  useEffect(() => {
    getConfig()
      .then((cfg) =>
        form.setFieldsValue({
          draft_root: cfg.draft_root || '',
          port_start: cfg.port_range[0],
          port_end: cfg.port_range[1],
          cors_origins: cfg.cors_origins,
        }),
      )
      .catch(() => {})
  }, [form])

  const pickDir = async () => {
    const path = await pickFolder()
    if (path) form.setFieldsValue({ draft_root: path })
  }

  const autoDetect = async () => {
    const path = await detectDraftRoot()
    if (path) {
      form.setFieldsValue({ draft_root: path })
      message.success('已探测到剪映草稿目录')
    } else {
      message.warning('未探测到剪映默认草稿目录，请手动选择')
    }
  }

  const onSave = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      await putConfig({
        draft_root: v.draft_root || null,
        port_range: [v.port_start, v.port_end],
        cors_origins: v.cors_origins || [],
      })
      message.success('已保存')
      onSaved && onSaved()
    } catch (err) {
      message.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Form form={form} layout="vertical" style={{ maxWidth: 560 }}>
      <Form.Item label="剪映草稿根目录" name="draft_root">
        <Input
          addonAfter={
            <Space size={4}>
              <a onClick={pickDir} style={{ pointerEvents: bridgeOn ? 'auto' : 'none', opacity: bridgeOn ? 1 : 0.4 }}>
                选择目录
              </a>
              <span style={{ color: '#ddd' }}>|</span>
              <a onClick={autoDetect} style={{ pointerEvents: bridgeOn ? 'auto' : 'none', opacity: bridgeOn ? 1 : 0.4 }}>
                自动探测
              </a>
            </Space>
          }
        />
      </Form.Item>
      {!bridgeOn && (
        <div style={{ marginTop: -16, marginBottom: 12, fontSize: 12, color: '#999' }}>
          （浏览器开发环境下「选择目录 / 自动探测」不可用，请手动输入路径）
        </div>
      )}
      <Form.Item label="端口段">
        <Space>
          <Form.Item name="port_start" noStyle>
            <InputNumber min={1} max={65535} />
          </Form.Item>
          <span>—</span>
          <Form.Item name="port_end" noStyle>
            <InputNumber min={1} max={65535} />
          </Form.Item>
          <span style={{ color: '#999', fontSize: 12 }}>修改端口段需重启应用生效</span>
        </Space>
      </Form.Item>
      <Form.Item label="CORS 白名单" name="cors_origins">
        <Select mode="tags" placeholder="输入 origin 后回车，如 http://localhost:3182" />
      </Form.Item>
      <Button type="primary" loading={saving} onClick={onSave}>
        保存
      </Button>
    </Form>
  )
}
