import i18n from '@/i18n'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
export function readPreference(key: string, fallback = '') {
  try {
    return localStorage.getItem(`aryn.shell.${key}`) ?? fallback
  } catch {
    return fallback
  }
}
export function savePreference(key: string, value: string) {
  try {
    localStorage.setItem(`aryn.shell.${key}`, value)
  } catch {
    /* Preferences are optional in restricted browsers. */
  }
}
export function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? i18n.t('ui.timestamp_unavailable')
    : new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date)
}
