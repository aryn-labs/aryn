import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useShell } from '@/app/providers/ShellProvider'
import { SidebarNavigation } from './AppSidebar'
export function MobileNavigation() {
  useTranslation()

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
        <DialogTitle>{tr('ui.workspace')}</DialogTitle>
        <DialogDescription className="sr-only">{tr('ui.navigate_aryn_studio')}</DialogDescription>
        <SidebarNavigation onNavigate={() => setMobileOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}
