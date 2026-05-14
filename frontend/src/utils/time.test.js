import { describe, expect, it } from 'vitest'
import { relativeTime } from './time.js'

describe('relativeTime', () => {
  const now = 1_000_000 // 任意 now（秒）

  it('shows 刚刚 within a minute', () => {
    expect(relativeTime(now - 30, now)).toBe('刚刚')
  })
  it('shows minutes', () => {
    expect(relativeTime(now - 120, now)).toBe('2 分钟前')
  })
  it('shows hours', () => {
    expect(relativeTime(now - 7200, now)).toBe('2 小时前')
  })
  it('shows days', () => {
    expect(relativeTime(now - 172800, now)).toBe('2 天前')
  })
  it('clamps future timestamps to 刚刚', () => {
    expect(relativeTime(now + 100, now)).toBe('刚刚')
  })
})
