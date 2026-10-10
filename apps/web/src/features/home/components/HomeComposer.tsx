import { useLayoutEffect, useRef } from 'react'
import { ArrowUp, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
export function HomeComposer({
  compact,
  value,
  onChange,
  followUp = false,
  onContinue,
}: {
  compact: boolean
  value: string
  onChange: (value: string) => void
  followUp?: boolean
  onContinue: (goal: string) => void
}) {
  const input = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const node = input.current
    if (!node) return
    function resize() {
      if (!node) return
      node.style.height = 'auto'
      const style = getComputedStyle(node)
      const minimum = parseFloat(style.minHeight) || 72
      const maximum = parseFloat(style.maxHeight) || 200
      node.style.height = `${Math.max(minimum, Math.min(node.scrollHeight, maximum))}px`
      node.style.overflowY = node.scrollHeight > maximum ? 'auto' : 'hidden'
    }
    resize()
    let width = node.clientWidth
    const observer =
      typeof ResizeObserver === 'undefined'
        ? undefined
        : new ResizeObserver(() => {
            if (node.clientWidth !== width) {
              width = node.clientWidth
              resize()
            }
          })
    observer?.observe(node)
    window.addEventListener('resize', resize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [value, compact, followUp])
  function submit() {
    if (!followUp && value.trim()) onContinue(value.trim())
  }
  return (
    <form
      className={`home-composer ${compact ? 'is-compact' : ''}`}
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
      aria-labelledby="composer-title"
    >
      <h2 id="composer-title">
        <Sparkles size={20} aria-hidden="true" />
        {followUp ? 'Continue the conversation' : 'What would you like to build?'}
      </h2>
      <label className="sr-only" htmlFor="home-goal">
        {followUp ? 'Follow-up message' : 'Describe the agent or workflow you want to build'}
      </label>
      <textarea
        id="home-goal"
        ref={input}
        rows={2}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={1200}
        placeholder={
          followUp
            ? 'Prepare a follow-up… Sending is currently unavailable.'
            : 'Describe what you’d like to build or ask a question…'
        }
        aria-describedby="composer-help"
        onKeyDown={(event) => {
          if (
            !event.nativeEvent.isComposing &&
            (event.ctrlKey || event.metaKey) &&
            event.key === 'Enter'
          ) {
            event.preventDefault()
            submit()
          }
        }}
      />
      <div className="home-composer-footer">
        <p id="composer-help">
          {followUp
            ? 'Sending requires an ARYN conversation API. Nothing is sent or saved.'
            : 'AI chat is unavailable on this server. Continue to review your message.'}
        </p>
        <Button
          type="submit"
          size="sm"
          disabled={followUp || !value.trim()}
          aria-describedby="composer-help"
          aria-keyshortcuts="Control+Enter Meta+Enter"
        >
          {followUp ? 'Send' : 'Continue'}
          <ArrowUp size={15} aria-hidden="true" />
        </Button>
      </div>
    </form>
  )
}
