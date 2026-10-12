import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { id, en } from './resources'
import { uiIds } from './ui'
import { extraIds } from './extra'
import { projectsId, projectsEn } from './projects'
import { agentsId, agentsEn } from './agents'
import { studioId, studioEn } from './studio'
import { workflowsId, workflowsEn } from './workflows'
import { operationsId, operationsEn } from './operations'
import { intelligenceId, intelligenceEn } from './intelligence'

void i18n.use(initReactI18next).init({
  resources: {
    'id-ID': {
      translation: {
        ...id,
        projects: projectsId,
        agents: agentsId,
        studio: studioId,
        workflows: workflowsId,
        operations: operationsId,
        intelligence: intelligenceId,
      },
    },
    'en-US': {
      translation: {
        ...en,
        projects: projectsEn,
        agents: agentsEn,
        studio: studioEn,
        workflows: workflowsEn,
        operations: operationsEn,
        intelligence: intelligenceEn,
      },
    },
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
