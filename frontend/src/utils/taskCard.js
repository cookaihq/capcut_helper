// 从后端任务对象派生「活动」视图卡片要用的展示状态。

const STATUS_LABEL = {
  pending: '等待中',
  downloading: '下载素材中',
  building: '生成草稿中',
  done: '已完成',
  failed: '失败',
}

const IN_PROGRESS = ['pending', 'downloading', 'building']

export function taskDisplay(task) {
  return {
    label: STATUS_LABEL[task.status] || task.status,
    inProgress: IN_PROGRESS.includes(task.status),
    isDone: task.status === 'done',
    isFailed: task.status === 'failed',
  }
}
