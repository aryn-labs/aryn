import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Check } from 'lucide-react'
import { StudioLibrarySearch } from '@/app/studio/StudioLibrary'
import { kinds, type Graph, type Node } from './api'
import { registry } from './registry'
export function WorkflowLibrary({
  graph,
  onAdd,
  onClose,
}: {
  graph: Graph
  onAdd: (kind: Node['kind']) => void
  onClose: () => void
}) {
  const { t } = useTranslation(),
    [search, setSearch] = useState(''),
    [category, setCategory] = useState('all')
  return (
    <div className="af-library">
      <StudioLibrarySearch
        title={t('workflows.library')}
        closeLabel={t('agents.close')}
        searchLabel={t('workflows.searchNodes')}
        search={search}
        onSearch={setSearch}
        categories={['all', 'execution', 'control'].map((id) => ({
          id,
          label: t('workflows.' + id),
        }))}
        category={category}
        onCategory={setCategory}
        onClose={onClose}
      />
      {kinds
        .filter(
          (kind) =>
            (category === 'all' || registry[kind].category === category) &&
            (t('workflows.' + kind) + t('workflows.' + kind + 'Help'))
              .toLowerCase()
              .includes(search.toLowerCase()),
        )
        .map((kind) => {
          const definition = registry[kind],
            Icon = definition.icon,
            disabled =
              graph.nodes.length >= 24 ||
              (definition.singleton && graph.nodes.some((n) => n.kind === kind))
          return (
            <button
              key={kind}
              className="af-library-node"
              disabled={disabled}
              draggable={!disabled}
              onDragStart={(e) => e.dataTransfer.setData('application/aryn-node', kind)}
              onClick={() => onAdd(kind)}
            >
              <span className="af-node-icon">
                <Icon size={18} />
              </span>
              <span>
                <strong>{t('workflows.' + kind)}</strong>
                <small>{t('workflows.' + kind + 'Help')}</small>
              </span>
              {disabled ? <Check size={14} /> : <Plus size={14} />}
            </button>
          )
        })}
      <p className="af-note">{t('workflows.limits')}</p>
    </div>
  )
}
