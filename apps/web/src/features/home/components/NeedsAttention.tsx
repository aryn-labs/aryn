import { HomeResourceRow } from './HomeResourceRow'
import type { AttentionItem, HomeResource } from '../lib/home-state'
import { statusLabel } from '../lib/home-labels'
export function NeedsAttention({
  items,
  onOpen,
}: {
  items: AttentionItem[]
  onOpen: (item: HomeResource) => void
}) {
  if (!items.length) return null
  return (
    <section className="home-section home-attention" aria-labelledby="attention-heading">
      <div className="home-section-heading">
        <h2 id="attention-heading">Needs Your Attention</h2>
        <p>Review the evidence and related resource before deciding what comes next.</p>
      </div>
      <div className="home-panel">
        {items.map((item) => (
          <HomeResourceRow
            key={`${item.kind}:${item.id}`}
            item={item}
            description={`${item.label} · ${item.kind === 'bench' ? statusLabel(item.reason) : item.reason}`}
            onOpen={onOpen}
          />
        ))}
      </div>
      <p className="home-section-note">
        Recent items relevant to your access. Actions remain subject to Core review.
      </p>
    </section>
  )
}
