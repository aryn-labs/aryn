import { Outlet, useLocation } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { GlobalSearch } from '@/components/overlays/GlobalSearch'
import { ResourceDetailsDialog } from '@/components/overlays/ResourceDetailsDialog'

/** Shared overlays and navigation focus survive switching between route layouts. */
export function RootLayout() {
  const { pathname } = useLocation()
  const previous = useRef(pathname)
  useEffect(() => {
    if (previous.current === pathname) return
    previous.current = pathname
    const frame = requestAnimationFrame(() =>
      document.getElementById('main-content')?.focus({ preventScroll: true }),
    )
    return () => cancelAnimationFrame(frame)
  }, [pathname])
  return (
    <>
      <Outlet />
      <GlobalSearch />
      <ResourceDetailsDialog />
    </>
  )
}
