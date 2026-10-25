import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { useCatalog, useCopy, useIntelligenceContext } from '@/components/intelligence/hooks'
import {
  Badge,
  DateValue,
  Facts,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
} from '@/components/intelligence/IntelligenceUI'
import { TrustedBindingRegistration } from '@/components/intelligence/TrustedBindingRegistration'
import { targetSchema } from '@/features/intelligence/api'
import type { z } from '@/lib/types/validation'

type Target = z.infer<typeof targetSchema>
export function OperationalTargetsPanel({ project }: { project: string }) {
  const c = useCopy(),
    query = useCatalog('/relay/targets', targetSchema, project),
    permission = useIntelligenceContext(project),
    cache = useQueryClient(),
    [register, setRegister] = useState(false),
    [action, setAction] = useState<{ target: Target; kind: 'observe' | 'signal' | 'grant' } | null>(
      null,
    )
  const items = query.error ? [] : (query.data?.pages.flatMap((page) => page.items) ?? [])
  return (
    <>
      <Notice>{c('operationalBoundary')}</Notice>
      <div className="intel-actions">
        <Button
          disabled={!project || !permission.data?.permissions['tool:register']}
          onClick={() => setRegister(true)}
        >
          {c('registerTarget')}
        </Button>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          {c('refresh')}
        </Button>
      </div>
      <QueryState query={query} empty={!items.length} />
      <div className="intel-stack">
        {items.map((target) => (
          <Panel key={target.id} title={target.name}>
            <div className="intel-actions">
              <Badge value={target.enabled ? 'enabled' : 'disabled'} />
              <Badge
                value={
                  target.probe ? (target.probe.healthy ? 'healthy' : 'unhealthy') : 'unavailable'
                }
              />
            </div>
            <Facts
              values={[
                [c('target'), <code>{target.id}</code>],
                [c('revision'), target.revision],
                [c('connectionIdentity'), <code>{target.configuration_hash}</code>],
                [c('latency'), target.probe?.latency_ms ?? null],
                [c('updated'), <DateValue value={target.updated_at} />],
              ]}
            />
            <Notice>{c('measurementCheckpoint')}</Notice>
            <div className="intel-actions">
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['run:create']}
                onClick={() => setAction({ target, kind: 'observe' })}
              >
                {c('observeTarget')}
              </Button>
              <Button
                disabled={!permission.data?.permissions['run:create']}
                onClick={() => setAction({ target, kind: 'signal' })}
              >
                {c('collectSignal')}
              </Button>
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['tool:register']}
                onClick={() => setAction({ target, kind: 'grant' })}
              >
                {c(target.enabled ? 'revokeGrant' : 'enableGrant')}
              </Button>
            </div>
          </Panel>
        ))}
      </div>
      <More query={query} />
      {register && (
        <TrustedBindingRegistration
          project={project}
          kind="target"
          onClose={() => setRegister(false)}
        />
      )}
      {action && (
        <MutationDialog
          project={project}
          title={c(
            action.kind === 'observe'
              ? 'observeTarget'
              : action.kind === 'signal'
                ? 'collectSignal'
                : action.target.enabled
                  ? 'revokeGrant'
                  : 'enableGrant',
          )}
          description={c('operationalBoundary')}
          path={
            action.kind === 'signal'
              ? '/relay/signals'
              : `/relay/targets/${action.target.id}/${action.kind}`
          }
          body={
            action.kind === 'observe'
              ? {}
              : action.kind === 'signal'
                ? {
                    target_id: action.target.id,
                    dedup_key: 'observed_target_state',
                    severity: 'high',
                  }
                : {
                    expected_configuration_hash: action.target.configuration_hash,
                    enabled: !action.target.enabled,
                  }
          }
          allowed={
            !!permission.data?.permissions[action.kind === 'grant' ? 'tool:register' : 'run:create']
          }
          onClose={() => setAction(null)}
          onSuccess={async () => {
            await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
          }}
        >
          <code>{action.target.id}</code>
          {action.kind === 'signal' && <Notice>{c('signalDedupHelp')}</Notice>}
        </MutationDialog>
      )}
    </>
  )
}
