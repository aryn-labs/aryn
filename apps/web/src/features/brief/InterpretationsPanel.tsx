import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Button } from '@/components/ui/button'
import { useCatalog, useCopy, useIntelligenceContext } from '@/components/intelligence/hooks'
import {
  DateValue,
  Field,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
  ResourceLink,
} from '@/components/intelligence/IntelligenceUI'
import { base, request, scoped, interpretationSchema } from '@/features/intelligence/api'
import { z } from '@/lib/types/validation'

const agentsSchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  items: z.array(
    z.object({
      assignment_id: z.string(),
      role_name: z.string(),
      version_id: z.string(),
      model: z.string(),
      max_tokens: z.number(),
      max_cost_usd: z.number(),
    }),
  ),
})
export function InterpretationsPanel({ project, bundleId }: { project: string; bundleId: string }) {
  const c = useCopy(),
    w = useWorkspace(),
    cache = useQueryClient(),
    permission = useIntelligenceContext(project),
    query = useCatalog(`/brief/${bundleId}/interpretations`, interpretationSchema, project),
    [open, setOpen] = useState(false),
    [assignment, setAssignment] = useState(''),
    [consent, setConsent] = useState(false),
    [key, setKey] = useState('')
  const agents = useQuery({
    queryKey: [
      'intelligence-interpretation-agents',
      w.context?.user.id,
      w.context?.organization.id,
      project,
    ],
    enabled: open && !!permission.data?.permissions['run:create'],
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/brief/interpretation-agents', agentsSchema, { signal }),
        w.context!.organization.id,
        project,
      ),
  })
  const items = query.error ? [] : (query.data?.pages.flatMap((page) => page.items) ?? [])
  return (
    <Panel title={c('interpretations')}>
      <Notice>{c('interpretationHelp')}</Notice>
      <Button
        variant="secondary"
        disabled={!permission.data?.permissions['run:create']}
        onClick={() => {
          setAssignment('')
          setConsent(false)
          setKey(crypto.randomUUID())
          setOpen(true)
        }}
      >
        {c('interpretEvidence')}
      </Button>
      <QueryState query={query} empty={!items.length} />
      {items.map((item) => (
        <article className="intel-row" key={item.id}>
          <strong>{c('modelInterpretation')}</strong> · <DateValue value={item.created_at} />
          <blockquote className="intel-excerpt">{item.text}</blockquote>
          <ResourceLink project={project} kind="run" id={item.core_run_id} />
          <small>
            {c('capturedEvidenceStatus')}: {item.evidence_status}
          </small>
        </article>
      ))}
      <More query={query} />
      {open && (
        <MutationDialog
          title={c('interpretEvidence')}
          description={c('interpretationHelp')}
          project={project}
          path={`/brief/${bundleId}/interpret`}
          body={{ assignment_id: assignment, allow_remote_model: true, idempotency_key: key }}
          allowed={
            !!permission.data?.permissions['run:create'] &&
            consent &&
            !agents.error &&
            !!agents.data?.items.some((item) => item.assignment_id === assignment)
          }
          onClose={() => setOpen(false)}
          onSuccess={async () => {
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          <QueryState query={agents} empty={!agents.data?.items.length} />
          <Field label={c('interpretationAgent')}>
            <select value={assignment} onChange={(event) => setAssignment(event.target.value)}>
              <option value="">{c('select')}</option>
              {!agents.error &&
                agents.data?.items.map((item) => (
                  <option key={item.assignment_id} value={item.assignment_id}>
                    {item.role_name} · {item.model}
                  </option>
                ))}
            </select>
          </Field>
          {agents.data?.items
            .filter((item) => item.assignment_id === assignment)
            .map((item) => (
              <Notice key={item.assignment_id}>
                {c('usage')}: ≤ {item.max_tokens} · {c('cost')}: ≤ {item.max_cost_usd} USD
              </Notice>
            ))}
          <Field label={c('remoteConsent')}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
          </Field>
        </MutationDialog>
      )}
    </Panel>
  )
}
