import type { Draft } from './api'

// Local change detection only. Executable digests and integrity belong to Core.
export function draftSnapshot(draft: Draft): string {
  function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered)
    if (value !== null && typeof value === 'object')
      return Object.fromEntries(
        Object.entries(value)
          .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
          .map(([key, item]) => [key, ordered(item)]),
      )
    return value
  }
  return JSON.stringify(
    ordered({
      ...draft,
      positions: [...draft.positions].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)),
    }),
  )
}
