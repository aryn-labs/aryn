import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useConversationChange } from '../hooks/useConversationChange'
import type { ChatScope } from '../lib/chat-api'
import type { ConversationAction } from './ConversationMenu'

export function ConversationActionDialog({
  action,
  scope,
  onClose,
  onDeleted,
  fallbackFocus,
}: {
  action: ConversationAction
  scope: ChatScope
  onClose: () => void
  onDeleted: (id: string) => void
  fallbackFocus: () => void
}) {
  const { t } = useTranslation()
  const [title, setTitle] = useState(action.item.title)
  const cancel = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const change = useConversationChange(scope, onDeleted)
  const deleting = action.mode === 'delete'
  const valid =
    title.trim().length > 0 && title.trim().length <= 120 && !/[\p{Cc}\p{Cf}]/u.test(title)
  const submit = () =>
    change.mutate(
      {
        id: action.item.id,
        method: deleting ? 'DELETE' : 'PATCH',
        input: {
          expected_metadata_revision: action.item.metadata_revision,
          ...(deleting ? {} : { title: title.trim() }),
        },
      },
      { onSuccess: onClose },
    )
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !change.isPending) onClose()
      }}
    >
      <DialogContent
        className="chat-action-dialog"
        closeDisabled={change.isPending}
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          if (deleting) cancel.current?.focus()
          else {
            input.current?.focus()
            input.current?.select()
          }
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (action.trigger?.isConnected) action.trigger.focus()
          else fallbackFocus()
        }}
      >
        <DialogTitle>{t(deleting ? 'chat.delete' : 'chat.rename')}</DialogTitle>
        <DialogDescription>
          {deleting ? t('chat.deleteDisclosure') : t('chat.renameHelp')}
        </DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (
              !change.isPending &&
              !change.uncertain &&
              (deleting || (valid && title.trim() !== action.item.title))
            )
              submit()
          }}
        >
          {deleting ? (
            <p className="chat-delete-title">{action.item.title}</p>
          ) : (
            <label className="chat-title-field">
              {t('chat.title')}
              <input
                ref={input}
                maxLength={120}
                value={title}
                readOnly={change.uncertain}
                disabled={change.isPending}
                onChange={(event) => setTitle(event.target.value)}
                required
                aria-describedby="chat-title-help"
              />
              <span id="chat-title-help">{t('chat.titleLimit')}</span>
            </label>
          )}
          {change.isError && (
            <p className="chat-error" role="alert">
              {change.error.message}
            </p>
          )}
          <div className="chat-action-buttons">
            <Button
              ref={cancel}
              type="button"
              variant="secondary"
              disabled={change.isPending}
              onClick={onClose}
            >
              {t('common.cancel')}
            </Button>
            {change.uncertain ? (
              <Button
                type="button"
                disabled={change.isPending}
                onClick={() => change.retryOriginal({ onSuccess: onClose })}
              >
                {t('chat.retry')}
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={
                  change.isPending || (!deleting && (!valid || title.trim() === action.item.title))
                }
              >
                {change.isPending
                  ? t('settings.saving')
                  : t(deleting ? 'chat.deleteConfirm' : 'chat.saveTitle')}
              </Button>
            )}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
