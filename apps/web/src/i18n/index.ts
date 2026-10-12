import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { id, en } from './resources'
import { uiIds } from './ui'
import { extraIds } from './extra'
import { projectsId, projectsEn } from './projects'
import { agentsId, agentsEn } from './agents'
import { studioId, studioEn } from './studio'

void i18n.use(initReactI18next).init({
  resources: {
    'id-ID': { translation: { ...id, projects: projectsId, agents: agentsId, studio: studioId } },
    'en-US': { translation: { ...en, projects: projectsEn, agents: agentsEn, studio: studioEn } },
  },
  lng: 'id-ID',
  fallbackLng: 'id-ID',
  supportedLngs: ['id-ID', 'en-US'],
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
})
export default i18n
export const translate = (key: string, values?: Record<string, unknown>) => i18n.t(key, values)
export function labelText(text: string) {
  const key = uiIds[text] ?? extraIds[text]
  return key ? i18n.t('ui.' + key) : text
}
