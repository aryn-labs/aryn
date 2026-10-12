import { useEffect, useState } from 'react'

export function useStudioDrawer() {
  const [drawer, setDrawer] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)')
    const change = () => setDrawer(media.matches)
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  return drawer
}
