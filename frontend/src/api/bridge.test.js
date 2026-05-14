import { afterEach, describe, expect, it, vi } from 'vitest'
import { detectDraftRoot, isBridgeAvailable, pickFolder, revealInOs } from './bridge.js'

afterEach(() => {
  delete window.pywebview
})

describe('bridge', () => {
  it('isBridgeAvailable is false without pywebview', () => {
    expect(isBridgeAvailable()).toBe(false)
  })

  it('pickFolder returns null without bridge', async () => {
    expect(await pickFolder()).toBeNull()
  })

  it('revealInOs is a no-op without bridge', async () => {
    await expect(revealInOs('/x')).resolves.toBeUndefined()
  })

  it('delegates to window.pywebview.api when available', async () => {
    window.pywebview = {
      api: {
        pick_folder: vi.fn().mockResolvedValue('/picked'),
        reveal_in_os: vi.fn().mockResolvedValue(undefined),
        detect_draft_root: vi.fn().mockResolvedValue('/detected'),
      },
    }
    expect(isBridgeAvailable()).toBe(true)
    expect(await pickFolder()).toBe('/picked')
    await revealInOs('/some/path')
    expect(window.pywebview.api.reveal_in_os).toHaveBeenCalledWith('/some/path')
    expect(await detectDraftRoot()).toBe('/detected')
  })
})
