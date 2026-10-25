import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useCopy, useIntelligenceContext } from './hooks'
import { Field, MutationDialog, Notice, QueryState } from './IntelligenceUI'
import { base, request, scoped, bindingCatalogSchema } from '@/features/intelligence/api'

export function TrustedBindingRegistration({
  project,
  kind,
  onClose,
}: {
  project: string
  kind: 'evidence' | 'target'
  onClose: () => void
}) {
  const c = useCopy(),
    w = useWorkspace(),
    permission = useIntelligenceContext(project),
    cache = useQueryClient(),
    [binding, setBinding] = useState(''),
    [name, setName] = useState('')
  const path = kind === 'evidence' ? '/brief/connection-bindings' : '/relay/target-bindings'
  const query = useQuery({
    queryKey: [
      'intelligence-bindings',
      w.context?.user.id,
      w.context?.organization.id,
      project,
      kind,
    ],
    enabled: !!permission.data?.permissions['tool:register'],
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + path, bindingCatalogSchema, { signal }),
        w.context!.organization.id,
        project,
      ),
  })
  const available = !query.error && query.data?.items.some((item) => item.binding_id === binding)
  return (
    <MutationDialog
      title={c(kind === 'evidence' ? 'registerConnection' : 'registerTarget')}
      description={c('trustedBindingHelp')}
      project={project}
      path={kind === 'evidence' ? '/brief/connections' : '/relay/targets'}
      body={{ binding_id: binding, name: name.trim() }}
      allowed={!!permission.data?.permissions['tool:register'] && !!available && !!name.trim()}
      onClose={onClose}
      onSuccess={async () => {
        await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
      }}
    >
      <QueryState query={query} empty={!query.data?.items.length} />
      {query.data && !query.data.configured && <Notice warning>{c('bindingsUnavailable')}</Notice>}
      <Field label={c('approvedConnection')}>
        <select value={binding} onChange={(event) => setBinding(event.target.value)}>
          <option value="">{c('select')}</option>
          {!query.error &&
            query.data?.items.map((item) => (
              <option key={item.binding_id} value={item.binding_id}>
                {item.binding_id}
                {item.kind ? ` · ${item.kind}` : ''}
              </option>
            ))}
        </select>
      </Field>
      <Field label={c('title')}>
        <input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Notice>{c('trustedBindingHelp')}</Notice>
    </MutationDialog>
  )
}
