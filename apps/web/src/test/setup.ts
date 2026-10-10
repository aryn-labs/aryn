import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
configure({ asyncUtilTimeout: 3000 })
afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.className = 'dark'
})
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn((query: string) => ({
    matches: query.includes('1280'),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })),
})
Object.defineProperty(window, 'ResizeObserver', {
  value: class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
})
HTMLElement.prototype.scrollIntoView = vi.fn()
window.scrollTo = vi.fn()
