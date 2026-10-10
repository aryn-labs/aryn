import { formatDate } from '@/lib/utils'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useRef } from 'react'
import { Link } from '@tanstack/react-router'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { QueryError } from '@/components/feedback/DataState'
import { request } from '@/lib/api/client'
import { chatKey, chatPath, historySchema, scoped, type ChatScope } from '../lib/chat-api'

export function ChatHistory({
  scope,
  open,
  onClose,
}: {
  scope: ChatScope
  open: boolean
  onClose: () => void
}) {
  useTranslation()

  const returnFocus = useRef<HTMLElement | null>(null)
  const history = useInfiniteQuery({
    queryKey: [...chatKey(scope), 'history'],
    initialPageParam: '',
    queryFn: async ({ signal, pageParam }) =>
      scoped(
        await request(
          chatPath(scope) +
            '/conversations' +
            (pageParam ? `?before=${encodeURIComponent(pageParam)}` : ''),
          historySchema,
          { signal },
        ),
        scope,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: open && Boolean(scope.project && scope.user),
    retry: false,
  })
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose()
      }}
    >
      <DialogContent
        className="chat-history"
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          returnFocus.current?.focus()
        }}
      >
        <DialogTitle>{tr('ui.conversation_history')}</DialogTitle>
        <DialogDescription>
          {tr('ui.saved_conversations_in_this_project_for_your_account')}
        </DialogDescription>
        {history.isPending ? (
          <p role="status">{tr('ui.loading_conversations')}</p>
        ) : history.isError ? (
          <QueryError error={history.error} retry={() => void history.refetch()} />
        ) : (
          <>
            {!history.data.pages[0]?.items.length && (
              <p className="muted">{tr('ui.no_conversations_yet')}</p>
            )}
            <ul>
              {history.data.pages
                .flatMap((page) => page.items)
                .map((item) => (
                  <li key={item.id}>
                    <Link
                      to="/chat/$conversationId"
                      params={{ conversationId: item.id }}
                      onClick={onClose}
                    >
                      <strong>{item.title}</strong>
                      <span>
                        {formatDate(new Date(item.updated_at).toISOString())} · {item.model}
                      </span>
                    </Link>
                  </li>
                ))}
            </ul>
            {history.hasNextPage && (
              <Button
                variant="secondary"
                disabled={history.isFetchingNextPage}
                onClick={() => void history.fetchNextPage()}
              >
                {tr('ui.load_more')}
              </Button>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
