import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChatCapability } from '../lib/chat-api'
export function ModelPicker({
  capability,
  model,
  onModel,
  fixed = false,
  disabled = false,
}: {
  capability?: ChatCapability
  model: string
  onModel: (value: string) => void
  fixed?: boolean
  disabled?: boolean
}) {
  const id = useId()
  const { t } = useTranslation()
  return (
    <div className="chat-model-choice">
      <label className="sr-only" htmlFor={id}>
        {t('composer.model')}
      </label>
      <select
        id={id}
        value={model}
        onChange={(event) => onModel(event.target.value)}
        disabled={fixed || disabled || !capability?.can_send}
      >
        {fixed ? (
          <option value={model}>{model}</option>
        ) : (
          <>
            <option value="">
              {t(capability?.can_send ? 'composer.choose' : 'composer.noModel')}
            </option>
            {capability?.models
              .filter((item) => item.available || item.verifiable)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </>
        )}
      </select>
    </div>
  )
}
