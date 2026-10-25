import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { useCatalog, useCopy, useIntelligenceContext } from '@/components/intelligence/hooks'
import {
  Badge,
  Facts,
  Field,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
} from '@/components/intelligence/IntelligenceUI'
import { TrustedBindingRegistration } from '@/components/intelligence/TrustedBindingRegistration'
import { connectionSchema } from '@/features/intelligence/api'
import type { z } from '@/lib/types/validation'

type Connection = z.infer<typeof connectionSchema>
export function EvidenceConnectionsPanel({ project }: { project: string }) {
  const c = useCopy(),
    query = useCatalog('/brief/connections', connectionSchema, project),
    permission = useIntelligenceContext(project),
    cache = useQueryClient(),
    [register, setRegister] = useState(false),
    [action, setAction] = useState<{ connection: Connection; kind: 'collect' | 'grant' } | null>(
      null,
    ),
    [selection, setSelection] = useState(''),
    [title, setTitle] = useState(''),
    [revision, setRevision] = useState('')
  const items = query.error ? [] : (query.data?.pages.flatMap((page) => page.items) ?? [])
  return (
    <>
      <Notice>{c('sourceConnectionHelp')}</Notice>
      <div className="intel-actions">
        <Button
          disabled={!project || !permission.data?.permissions['tool:register']}
          onClick={() => setRegister(true)}
        >
          {c('registerConnection')}
        </Button>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          {c('refresh')}
        </Button>
      </div>
      <QueryState query={query} empty={!items.length} />
      <div className="intel-stack">
        {items.map((connection) => (
          <Panel key={connection.id} title={connection.name}>
            <Badge value={connection.enabled ? 'enabled' : 'disabled'} />
            <Facts
              values={[
                [c('sourceKind'), connection.kind],
                [c('reference'), <code>{connection.id}</code>],
                [c('revision'), connection.revision],
                [c('connectionIdentity'), <code>{connection.configuration_hash}</code>],
              ]}
            />
            <div className="intel-actions">
              <Button
                disabled={!connection.enabled || !permission.data?.permissions['version:create']}
                onClick={() => {
                  setSelection('')
                  setTitle('')
                  setRevision('')
                  setAction({ connection, kind: 'collect' })
                }}
              >
                {c('collectSource')}
              </Button>
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['tool:register']}
                onClick={() => setAction({ connection, kind: 'grant' })}
              >
                {c(connection.enabled ? 'revokeGrant' : 'enableGrant')}
              </Button>
            </div>
          </Panel>
        ))}
      </div>
      <More query={query} />
      {register && (
        <TrustedBindingRegistration
          project={project}
          kind="evidence"
          onClose={() => setRegister(false)}
        />
      )}
      {action && (
        <MutationDialog
          project={project}
          title={c(
            action.kind === 'collect'
              ? 'collectSource'
              : action.connection.enabled
                ? 'revokeGrant'
                : 'enableGrant',
          )}
          description={c('sourceConnectionHelp')}
          path={
            action.kind === 'collect'
              ? '/brief/collect'
              : `/brief/connections/${action.connection.id}/grant`
          }
          body={
            action.kind === 'collect'
              ? {
                  connection_id: action.connection.id,
                  file_key: selection,
                  title: title.trim(),
                  git_revision: revision || null,
                }
              : {
                  expected_configuration_hash: action.connection.configuration_hash,
                  enabled: !action.connection.enabled,
                }
          }
          allowed={
            action.kind === 'grant'
              ? !!permission.data?.permissions['tool:register']
              : !!permission.data?.permissions['version:create'] &&
                action.connection.file_keys.includes(selection) &&
                !!title.trim() &&
                (!revision || /^[a-f0-9]{40}$/.test(revision))
          }
          onClose={() => setAction(null)}
          onSuccess={async () => {
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          {action.kind === 'collect' && (
            <>
              <Field label={c('approvedFile')}>
                <select value={selection} onChange={(event) => setSelection(event.target.value)}>
                  <option value="">{c('select')}</option>
                  {action.connection.file_keys.map((key) => (
                    <option key={key}>{key}</option>
                  ))}
                </select>
              </Field>
              <Field label={c('title')}>
                <input
                  value={title}
                  maxLength={160}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              {action.connection.kind === 'git' && (
                <>
                  <Field label={c('gitRevision')}>
                    <input
                      value={revision}
                      maxLength={40}
                      pattern="[a-f0-9]{40}"
                      onChange={(event) => setRevision(event.target.value)}
                    />
                  </Field>
                  <small>{c('gitRevisionHelp')}</small>
                </>
              )}
            </>
          )}
        </MutationDialog>
      )}
    </>
  )
}
