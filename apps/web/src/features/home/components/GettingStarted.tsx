import { useTranslation } from 'react-i18next'
export function GettingStarted() {
  const { t } = useTranslation()
  return (
    <section className="home-section home-start" aria-labelledby="getting-started-heading">
      <div>
        <h2 id="getting-started-heading">{t('home.start')}</h2>
        <p>{t('home.startHelp')}</p>
      </div>
    </section>
  )
}
