import { describe, expect, it } from 'vitest'
import { taskDisplay } from './taskCard.js'

describe('taskDisplay', () => {
  it('marks downloading as in-progress', () => {
    const d = taskDisplay({ status: 'downloading' })
    expect(d.inProgress).toBe(true)
    expect(d.isDone).toBe(false)
    expect(d.isFailed).toBe(false)
    expect(d.label).toBe('下载素材中')
  })
  it('marks done', () => {
    const d = taskDisplay({ status: 'done' })
    expect(d.inProgress).toBe(false)
    expect(d.isDone).toBe(true)
    expect(d.label).toBe('已完成')
  })
  it('marks failed', () => {
    const d = taskDisplay({ status: 'failed' })
    expect(d.isFailed).toBe(true)
    expect(d.label).toBe('失败')
  })
  it('handles pending and building', () => {
    expect(taskDisplay({ status: 'pending' }).inProgress).toBe(true)
    expect(taskDisplay({ status: 'building' }).label).toBe('生成草稿中')
  })
})
