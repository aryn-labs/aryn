import { useEffect } from 'react'
import i18n from './index'
import { useChatScope } from '@/features/chat/hooks/useChat'
import { useLocalePreference } from '@/features/chat/hooks/useChatSettings'
export function LocalePreference() {
  const scope = useChatScope()
  const preference = useLocalePreference(scope)
  const locale = preference.data?.locale ?? (scope.user && scope.project ? 'id-ID' : i18n.language)
  useEffect(() => {
    void i18n.changeLanguage(locale)
    document.documentElement.lang = locale
  }, [locale, scope.user, scope.organization])
  return null
}
