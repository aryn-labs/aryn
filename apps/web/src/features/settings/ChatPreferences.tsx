import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { useChatScope } from '@/features/chat/hooks/useChat'
import { useLocalePreference, useProviderConsent } from '@/features/chat/hooks/useChatSettings'
import { Button } from '@/components/ui/button'
import { QueryError } from '@/components/feedback/DataState'
import './preferences.css'
export function ChatPreferences() {
  const { t } = useTranslation()
  const scope = useChatScope()
  const preference = useLocalePreference(scope)
  const consent = useProviderConsent(scope)
  const providers = [
    ...new Map(
      Object.values(consent.data?.models ?? {}).map((provider) => [provider.provider_id, provider]),
    ).values(),
  ]
  if (!scope.user || !scope.project) return <p className="muted">{t('settings.unavailable')}</p>
  return (
    <div className="preferences-grid">
      <section className="runtime-card" aria-labelledby="preferences-heading">
        <h2 id="preferences-heading">{t('settings.preferences')}</h2>
        {preference.isError ? (
          <QueryError error={preference.error} retry={() => void preference.refetch()} />
        ) : (
          <div className="language-preference">
            <label htmlFor="studio-language">{t('settings.language')}</label>
            <select
              id="studio-language"
              value={preference.data?.locale ?? 'id-ID'}
              disabled={preference.isPending || preference.save.isPending}
              onChange={(event) => preference.save.mutate(event.target.value as 'id-ID' | 'en-US')}
            >
              <option value="id-ID">{tr('ui.bahasa_indonesia')}</option>
              <option value="en-US">{tr('ui.english')}</option>
            </select>
          </div>
        )}
        <p role="status" className="muted">
          {preference.save.isPending
            ? t('settings.saving')
            : preference.save.isError
              ? t('settings.failed')
              : preference.save.isSuccess
                ? t('settings.saved')
                : ''}
        </p>
      </section>
      <section className="runtime-card" aria-labelledby="providers-heading">
        <h2 id="providers-heading">{t('settings.models')}</h2>
        <p className="muted preferences-disclosure">{t('settings.disclosure')}</p>
        {consent.isPending ? (
          <p role="status">{t('common.loading')}</p>
        ) : consent.isError ? (
          <QueryError error={consent.error} retry={() => void consent.refetch()} />
        ) : (
          <>
            {!providers.length && <p className="muted">{t('settings.noConsent')}</p>}
            <ul className="provider-preferences">
              {providers.map((provider) => (
                <li key={provider.provider_id}>
                  <div>
                    <strong>{provider.name}</strong>
                    <span>{t(provider.consented ? 'consent.active' : 'consent.notGranted')}</span>
                  </div>
                  {provider.consented && (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={consent.revoke.isPending}
                      onClick={() => consent.revoke.mutate(provider.provider_id)}
                    >
                      {t('consent.revoke')}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="muted preferences-disclosure">{t('consent.scope')}</p>
        {consent.revoke.isError && (
          <QueryError error={consent.revoke.error} retry={() => void consent.refetch()} />
        )}
        {consent.revoke.isSuccess && <p role="status">{t('consent.revoked')}</p>}
      </section>
    </div>
  )
}
