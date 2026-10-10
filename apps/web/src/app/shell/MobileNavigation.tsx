import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useShell } from '@/app/providers/ShellProvider'
import { SidebarNavigation } from './AppSidebar'
export function MobileNavigation() {
  const { mobileOpen, setMobileOpen } = useShell()
  return (
    <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
      <DialogContent
        className="navigation-sheet"
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          document.querySelector<HTMLButtonElement>('[aria-label="Open navigation"]')?.focus()
        }}
      >
        <DialogTitle>Workspace</DialogTitle>
        <DialogDescription className="sr-only">Navigate ARYN Studio</DialogDescription>
        <SidebarNavigation onNavigate={() => setMobileOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}
