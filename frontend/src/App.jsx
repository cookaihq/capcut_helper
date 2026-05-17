import { Tabs } from 'antd'
import { useEffect, useState } from 'react'
import StatusBar from './components/StatusBar.jsx'
import DraftRootBanner from './components/DraftRootBanner.jsx'
import UpdateBanner from './components/UpdateBanner.jsx'
import TrustRequestModal from './components/TrustRequestModal.jsx'
import ActivityView from './views/ActivityView.jsx'
import DraftsView from './views/DraftsView.jsx'
import SettingsView from './views/SettingsView.jsx'

export default function App() {
  const [activeTab, setActiveTab] = useState('activity')
  // bannerKey 变化时强制 DraftRootBanner 重挂载（保存配置后重新评估是否还要显示）
  const [bannerKey, setBannerKey] = useState(0)

  // 被外部 capcut-helper://trust 唤起时，主面板自动切到「设置」tab，让用户
  // 直接看到 CORS 白名单。Modal 弹出后用户允许，能立刻在背景里看到白名单
  // 新增一项；用户拒绝时也能直接看到当前白名单做对比。
  useEffect(() => {
    const onTrustRequest = () => setActiveTab('settings')
    window.addEventListener('capcut-helper:trust-request', onTrustRequest)
    return () => window.removeEventListener('capcut-helper:trust-request', onTrustRequest)
  }, [])

  const items = [
    { key: 'activity', label: '活动', children: <ActivityView /> },
    { key: 'drafts', label: '草稿', children: <DraftsView /> },
    {
      key: 'settings',
      label: '设置',
      children: <SettingsView onSaved={() => setBannerKey((k) => k + 1)} />,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <StatusBar />
      <DraftRootBanner
        key={bannerKey}
        onGoToSettings={() => setActiveTab('settings')}
        onConfigured={() => setBannerKey((k) => k + 1)}
      />
      <UpdateBanner />
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
      </div>
      <TrustRequestModal />
    </div>
  )
}
