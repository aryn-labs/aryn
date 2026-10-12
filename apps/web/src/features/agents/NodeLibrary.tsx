import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LockKeyhole, Plus, Check, BookOpen, Brain, Wrench } from 'lucide-react'
import { StudioLibrarySearch } from '@/app/studio/StudioLibrary'
import type { Graph, NodeType } from './api'
import { nodeRegistry } from './registry'

export function NodeLibrary({
  graph,
  onAdd,
  onClose,
}: {
  graph: Graph
  onAdd: (type: NodeType) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const definitions = Object.values(nodeRegistry).filter(
    (item) =>
      (category === 'all' || item.category === category) &&
      (t('agents.' + item.label) + t('agents.' + item.description))
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  )
  return (
    <aside className="af-library" aria-label={t('agents.library')}>
      <StudioLibrarySearch
        title={t('agents.library')}
        closeLabel={t('agents.close')}
        searchLabel={t('agents.searchNodes')}
        search={search}
        onSearch={setSearch}
        categories={['all', 'core', 'policy'].map((id) => ({
          id,
          label: id === 'all' ? t('projects.all') : t('agents.' + id),
        }))}
        category={category}
        onCategory={setCategory}
        onClose={onClose}
      />
      <div className="af-library-list">
        {!definitions.length && <p>{t('agents.noMatchingNodes')}</p>}
        {definitions.map((item) => {
          const Icon = item.icon,
            present = graph.nodes.some((node) => node.type === item.type)
          return (
            <button
              className="af-library-node"
              key={item.type}
              disabled={present}
              draggable={!present}
              onDragStart={(event) => {
                event.dataTransfer.setData('application/aryn-node', item.type)
                event.dataTransfer.effectAllowed = 'copy'
              }}
              onClick={() => onAdd(item.type)}
            >
              <span className="af-node-icon">
                <Icon size={18} />
              </span>
              <span>
                <strong>{t('agents.' + item.label)}</strong>
                <small>
                  {present ? t('agents.alreadyAdded') : t('agents.' + item.description)}
                </small>
              </span>
              {present ? <Check size={14} /> : <Plus size={15} />}
            </button>
          )
        })}
      </div>
      <div className="af-library-future">
        <span className="af-kicker">{t('agents.future')}</span>
        {[
          [Wrench, 'tools'],
          [BookOpen, 'knowledge'],
          [Brain, 'memory'],
        ].map(([Icon, label]) => {
          const Symbol = Icon as typeof Wrench
          return (
            <div key={String(label)}>
              <Symbol size={16} />
              <span>{t('agents.' + label)}</span>
              <LockKeyhole size={12} />
              <small>{t('agents.unavailable')}</small>
            </div>
          )
        })}
        <p>{t('agents.toolUnavailable')}</p>
      </div>
    </aside>
  )
}
