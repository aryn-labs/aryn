import { useId, useLayoutEffect, useRef, type ReactNode } from 'react'
import { ArrowRight, LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
export function HomeComposer({
  compact,
  value,
  onChange,
  followUp = false,
  onContinue,
  disabled = false,
  pending = false,
  readOnly = false,
  help,
  controls,
}: {
  disabled?: boolean
  pending?: boolean
  readOnly?: boolean
  help?: string
  controls?: ReactNode
  compact: boolean
  value: string
  onChange: (value: string) => void
  followUp?: boolean
  onContinue: (goal: string) => void
}) {
  const input = useRef<HTMLTextAreaElement>(null)
  const { t } = useTranslation()
  const helpId = useId()
  useLayoutEffect(() => {
    const node = input.current
    if (!node) return
    function resize() {
      if (!node) return
      node.style.height = 'auto'
      const style = getComputedStyle(node)
      const minimum = parseFloat(style.minHeight) || 48
      const maximum = parseFloat(style.maxHeight) || 154
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
    if (!disabled && !pending && value.trim()) onContinue(value.trim())
  }
  return (
    <form
      className={`home-composer ${compact ? 'is-compact' : ''}`}
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
      aria-label={t('composer.label')}
    >
      <label className="sr-only" htmlFor={followUp ? 'chat-message' : 'home-goal'}>
        {t('composer.label')}
      </label>
      <textarea
        id={followUp ? 'chat-message' : 'home-goal'}
        ref={input}
        rows={1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={4000}
        readOnly={pending || readOnly}
        placeholder={t('composer.placeholder')}
        aria-describedby={help ? helpId : undefined}
        onKeyDown={(event) => {
          if (
            !event.nativeEvent.isComposing &&
            !event.shiftKey &&
            event.keyCode !== 229 &&
            event.key === 'Enter'
          ) {
            event.preventDefault()
            submit()
          }
        }}
      />
      <div className="home-composer-footer">
        <div className="composer-controls">{controls}</div>
        {help && (
          <span id={helpId} className="sr-only">
            {help}
          </span>
        )}
        <Button
          type="submit"
          size="sm"
          disabled={disabled || pending || !value.trim()}
          aria-label={t(pending ? 'composer.sending' : 'composer.send')}
          aria-describedby={help ? helpId : undefined}
          aria-keyshortcuts="Enter"
        >
          {pending ? (
            <LoaderCircle className="animate-spin" size={19} aria-hidden="true" />
          ) : (
            <ArrowRight size={19} aria-hidden="true" />
          )}
        </Button>
      </div>
    </form>
  )
}
