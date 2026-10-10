import { useTranslation } from 'react-i18next'
import { HomeResourceRow } from './HomeResourceRow'
import type { AttentionItem, HomeResource } from '../lib/home-state'
export function NeedsAttention({
  items,
  onOpen,
}: {
  items: AttentionItem[]
  onOpen: (item: HomeResource) => void
}) {
  const { t } = useTranslation()
  if (!items.length) return null
  return (
    <section className="home-section home-attention" aria-labelledby="attention-heading">
      <div className="home-section-heading">
        <h2 id="attention-heading">{t('home.attention')}</h2>
      </div>
      <div className="home-panel">
        {items.slice(0, 3).map((item) => (
          <HomeResourceRow key={item.kind + item.id} item={item} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}
