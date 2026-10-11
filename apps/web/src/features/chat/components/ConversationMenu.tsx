import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { HistoryItem } from '../lib/chat-api'

export type ConversationAction = {
  item: HistoryItem
  mode: 'rename' | 'delete'
  trigger: HTMLElement | null
}
export function ConversationMenu({
  item,
  onAction,
}: {
  item: HistoryItem
  onAction: (action: ConversationAction) => void
}) {
  const { t } = useTranslation()
  const trigger = useRef<HTMLButtonElement>(null)
  if (!item.can_rename && !item.can_delete) return null
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          ref={trigger}
          variant="ghost"
          size="icon"
          aria-label={t('chat.manage', { title: item.title })}
        >
          <MoreHorizontal size={18} aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {item.can_rename && (
          <DropdownMenuItem
            onSelect={() => onAction({ item, mode: 'rename', trigger: trigger.current })}
          >
            <Pencil size={15} aria-hidden="true" /> {t('chat.rename')}
          </DropdownMenuItem>
        )}
        {item.can_delete && (
          <DropdownMenuItem
            className="chat-delete-action"
            onSelect={() => onAction({ item, mode: 'delete', trigger: trigger.current })}
          >
            <Trash2 size={15} aria-hidden="true" /> {t('chat.delete')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
