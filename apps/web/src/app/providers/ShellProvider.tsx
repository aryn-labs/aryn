import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Selection } from '@/lib/types/workspace'
import { readPreference, savePreference } from '@/lib/utils'
import { useWorkspace } from './WorkspaceProvider'
type Shell = {
  collapsed: boolean
  toggleSidebar: () => void
  searchOpen: boolean
  setSearchOpen: (open: boolean) => void
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
  selection: Selection | null
  inspect: (selection: Selection | null) => void
  theme: 'dark' | 'light'
  toggleTheme: () => void
}
const ShellContext = createContext<Shell | null>(null)
export function ShellProvider({ children }: { children: ReactNode }) {
  const { project, context } = useWorkspace()
  const [collapsed, setCollapsed] = useState(() => readPreference('collapsed') === 'true')
  const [searchOpen, setSearchOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    readPreference('theme') === 'light' ? 'light' : 'dark',
  )
  const visibleSelection = context && selection?.item.project_id === project?.id ? selection : null
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.style.colorScheme = theme
    savePreference('theme', theme)
  }, [theme])
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !event.repeat) {
        event.preventDefault()
        setSelection(null)
        setSearchOpen((open) => !open)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])
  return (
    <ShellContext.Provider
      value={{
        collapsed,
        toggleSidebar() {
          setCollapsed((value) => {
            savePreference('collapsed', String(!value))
            return !value
          })
        },
        searchOpen,
        setSearchOpen,
        mobileOpen,
        setMobileOpen,
        selection: visibleSelection,
        inspect: setSelection,
        theme,
        toggleTheme: () => setTheme((value) => (value === 'dark' ? 'light' : 'dark')),
      }}
    >
      {children}
    </ShellContext.Provider>
  )
}
export function useShell() {
  const context = useContext(ShellContext)
  if (!context) throw new Error('ShellProvider is required')
  return context
}
