import i18n from '@/i18n'
import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { beforeEach, afterEach, vi } from 'vitest'
configure({ asyncUtilTimeout: 3000 })
// Legacy interaction suites use English receipts; dedicated i18n tests verify the product default.
beforeEach(async () => {
  await i18n.changeLanguage('en-US')
})
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
