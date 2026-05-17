import { Button, Card, Empty, Progress, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { getTasks } from '../api/client.js'
import { revealInOs } from '../api/bridge.js'
import { relativeTime } from '../utils/time.js'
import { taskDisplay } from '../utils/taskCard.js'

export default function ActivityView() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    const load = () => getTasks().then(setTasks).catch(() => {})
    load()
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [])

  if (tasks.length === 0) {
    return (
      <Empty description="还没有导入任务。" />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {tasks.map((task) => {
        const d = taskDisplay(task)
        return (
          <Card key={task.id} size="small">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 600 }}>{task.draft_name}</span>
              <Tag color={d.isDone ? 'success' : d.isFailed ? 'error' : 'processing'}>
                {d.label}
              </Tag>
            </div>
            {d.inProgress && (
              <Progress percent={task.progress} size="small" status="active" />
            )}
            {d.isDone && (
              <div style={{ marginTop: 6, fontSize: 12 }}>
                <span style={{ color: '#999' }}>{task.result}</span>
                <Button
                  size="small"
                  type="link"
                  onClick={() => revealInOs(task.result)}
                >
                  在访达/资源管理器打开
                </Button>
              </div>
            )}
            {d.isFailed && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#ff4d4f' }}>
                {task.error}
              </div>
            )}
            <div style={{ marginTop: 4, fontSize: 12, color: '#999' }}>
              {relativeTime(task.created_at)}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
