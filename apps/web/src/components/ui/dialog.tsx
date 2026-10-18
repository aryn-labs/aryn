import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import * as Primitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
export const Dialog = Primitive.Root
export const DialogTitle = Primitive.Title
export const DialogDescription = Primitive.Description
export function DialogContent({
  className,
  children,
  closeDisabled = false,
  ...props
}: ComponentProps<typeof Primitive.Content> & { closeDisabled?: boolean }) {
  useTranslation()

  return (
    <Primitive.Portal>
      <Primitive.Overlay className="dialog-overlay" />
      <Primitive.Content className={cn('dialog-content', className)} {...props}>
        {children}
        <Primitive.Close
          disabled={closeDisabled}
          className="button button-ghost button-icon dialog-close"
          aria-label={tr('ui.close_dialog')}
        >
          <X size={18} />
        </Primitive.Close>
      </Primitive.Content>
    </Primitive.Portal>
  )
}
