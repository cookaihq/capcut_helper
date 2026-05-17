import { Button, Form, Input, InputNumber, Select, Space, message } from 'antd'
import { useEffect, useState } from 'react'
import { getConfig, putConfig, restartApp } from '../api/client.js'
import { detectDraftRoot, isBridgeAvailable, pickFolder } from '../api/bridge.js'

export default function SettingsView({ onSaved }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const bridgeOn = isBridgeAvailable()

  useEffect(() => {
    const reload = () =>
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
    reload()
    // 监听 backend 外部触发的 config 变更（如 TrustRequestModal 允许接入后
    // POST /cors-origins）—— 重新拉 config 让设置面板里立刻能看到新增项
    window.addEventListener('capcut-helper:config-changed', reload)
    return () => window.removeEventListener('capcut-helper:config-changed', reload)
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
    } catch (err) {
      message.error(err.message || '保存失败')
      setSaving(false)
      return
    }
    // 保存成功 → 触发后端重启。后端会先返回 200 再 spawn 新实例 + 自杀，
    // 当前窗口随之被销毁；不需要 setSaving(false)，loading 提示持续到进程退出
    message.loading({ content: '已保存，正在重启…', duration: 0 })
    try {
      await restartApp()
      onSaved && onSaved()
    } catch (err) {
      message.destroy()
      message.error(err.message || '重启失败，请手动退出后重新打开')
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
        </Space>
      </Form.Item>
      <Form.Item label="CORS 白名单" name="cors_origins">
        <Select mode="tags" placeholder="输入 origin 后回车，如 http://localhost:3182" />
      </Form.Item>
      <Button type="primary" loading={saving} onClick={onSave}>
        保存并重启生效
      </Button>
    </Form>
  )
}
