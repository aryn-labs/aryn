import { labelText } from '@/i18n'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Conversation } from '../lib/chat-api'

export function ChatMessages({ conversation }: { conversation: Conversation }) {
  useTranslation()

  const [copyStatus, setCopyStatus] = useState('')
  async function copy(content: string) {
    try {
      await navigator.clipboard.writeText(content)
      setCopyStatus('Response copied.')
    } catch {
      setCopyStatus('Could not copy. Select the response text to copy it manually.')
    }
  }
  return (
    <>
      <ol className="chat-messages" aria-label={tr('ui.conversation_messages')}>
        {conversation.messages.map((message) => (
          <li key={message.id} className={`chat-message chat-message-${message.role}`}>
            <span className="chat-speaker">
              {message.role === 'user' ? tr('chat.you') : 'ARYN'}
            </span>
            {message.role === 'user' ? (
              <p className="chat-user-text">{message.content}</p>
            ) : (
              <>
                <div className="chat-markdown">
                  <Markdown
                    remarkPlugins={[remarkGfm]}
                    skipHtml
                    disallowedElements={['img', 'iframe', 'script', 'style', 'input']}
                    urlTransform={(url) => (/^https?:\/\//i.test(url) ? url : '')}
                    components={{
                      a: ({ href, children }) =>
                        href ? (
                          <a href={href} target="_blank" rel="noopener noreferrer">
                            {children}
                          </a>
                        ) : (
                          <span>{children}</span>
                        ),
                    }}
                  >
                    {message.content}
                  </Markdown>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void copy(message.content)}
                  aria-label={tr('ui.copy_response')}
                >
                  <Copy size={14} aria-hidden="true" /> {tr('ui.copy')}
                </Button>
              </>
            )}
          </li>
        ))}
      </ol>
      <p className="sr-only" role="status">
        {labelText(copyStatus)}
      </p>
    </>
  )
}
