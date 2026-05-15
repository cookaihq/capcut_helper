import { afterEach, describe, expect, it, vi } from 'vitest'
import { getHealth, getTasks, putConfig } from './client.js'

afterEach(() => {
  vi.restoreAllMocks()
})

function mockFetch(body, ok = true) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    json: async () => body,
  })
}

describe('client', () => {
  it('unwraps data on success', async () => {
    mockFetch({ code: 0, message: 'ok', data: { service: 'capcut_helper' } })
    const data = await getHealth()
    expect(data).toEqual({ service: 'capcut_helper' })
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/health', undefined)
  })

  it('throws when code is non-zero', async () => {
    mockFetch({ code: 1003, message: '任务不存在', data: null })
    await expect(getTasks()).rejects.toMatchObject({ message: '任务不存在', code: 1003 })
  })

  it('putConfig sends JSON body', async () => {
    mockFetch({ code: 0, message: 'ok', data: { draft_root: '/x' } })
    await putConfig({ draft_root: '/x', port_range: [9527, 9536], cors_origins: [] })
    const [url, options] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/v1/config')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({
      draft_root: '/x',
      port_range: [9527, 9536],
      cors_origins: [],
    })
  })

  it('getUpdateInfo unwraps update info', async () => {
    mockFetch({
      code: 0,
      message: 'ok',
      data: {
        current_version: '0.1.0',
        latest_version: '0.2.0',
        has_update: true,
        release_url: 'https://x/release',
        download_url: 'https://x/zip',
        notes: 'notes',
        error: null,
      },
    })
    const { getUpdateInfo } = await import('./client.js')
    const data = await getUpdateInfo()
    expect(data.has_update).toBe(true)
    expect(data.latest_version).toBe('0.2.0')
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/update/check', undefined)
  })
})
