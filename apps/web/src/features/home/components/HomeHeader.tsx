import { greetingPeriod } from '../lib/home-state'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
export function HomeHeader() {
  const { t } = useTranslation()
  const [period, setPeriod] = useState(() => greetingPeriod(new Date().getHours()))
  useEffect(() => {
    const update = () => setPeriod(greetingPeriod(new Date().getHours()))
    const interval = window.setInterval(update, 60_000)
    window.addEventListener('focus', update)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', update)
    }
  }, [])
  return (
    <div className="home-header">
      <h1>{t(`greeting.${period}`)}</h1>
    </div>
  )
}
