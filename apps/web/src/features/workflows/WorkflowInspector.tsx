import { cloneElement, useId, useState, type ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useQuery } from '@tanstack/react-query'
import { DataState, QueryError } from '@/components/feedback/DataState'
import { resourceSchema } from '@/lib/types/workspace'
import {
  base,
  request,
  scoped,
  schemas,
  type Graph,
  type Issue,
  type Node,
  type Run,
  type Target,
} from './api'
import { registry } from './registry'
export function WorkflowInspector({
  node,
  graph,
  targets,
  hasMoreTargets,
  loadingTargets,
  onMoreTargets,
  project,
  readOnly,
  issues,
  run,
  onChange,
  onDelete,
  onConnect,
  onRemoveEdge,
  onArtifact,
}: {
  node?: Node
  graph: Graph
  targets: Target[]
  hasMoreTargets: boolean
  loadingTargets: boolean
  onMoreTargets: () => void
  project: string
  readOnly: boolean
  issues: Issue[]
  run?: Run
  onChange: (node: Node) => void
  onDelete: () => void
  onConnect: (source_port: string, target: string) => void
  onRemoveEdge: (id: string) => void
  onArtifact: (id: string) => void
}) {
  const { t } = useTranslation(),
    fieldPrefix = useId(),
    [sourcePort, setSourcePort] = useState('value'),
    [target, setTarget] = useState('')
  if (!node) return <p className="af-note">{t('agents.select')}</p>
  const Icon = registry[node.kind].icon,
    task = run?.tasks.find((item) => item.node_id === node.id)
  const eligible = targets.filter((item) => item.eligible)
  const assignment = targets.find((item) => item.id === node.assignment_id)
  const published = assignment?.version_id === node.agent_version_id ? assignment : null
  const blueprintId = assignment?.blueprint_id ?? null
  const pinValid = eligible.some(
    (item) => item.id === node.assignment_id && item.version_id === node.agent_version_id,
  )
  const field = (label: string, value: ReactElement<{ 'aria-labelledby'?: string }>) => (
    <label className="af-field">
      <span id={fieldPrefix + label}>{t('workflows.' + label)}</span>
      {cloneElement(value, { 'aria-labelledby': fieldPrefix + label })}
    </label>
  )
  return (
    <div className="af-inspector-content">
      <header className="af-inspector-title">
        <span className="af-node-icon">
          <Icon size={19} />
        </span>
        <div>
          <h2>{t('workflows.' + node.kind)}</h2>
          <p>{t('workflows.' + node.kind + 'Help')}</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          disabled={readOnly}
          aria-label={t('workflows.remove')}
          onClick={onDelete}
        >
          <Trash2 size={15} />
        </Button>
      </header>
      <fieldset className="af-fields" disabled={readOnly}>
        {field(
          'label',
          <input
            value={node.label}
            maxLength={120}
            required
            onChange={(e) => onChange({ ...node, label: e.target.value })}
          />,
        )}
        {field('nodeId', <input readOnly value={node.id} />)}
        {node.kind === 'agent' && (
          <>
            {field(
              'target',
              <select
                value={node.renderer ?? 'agent'}
                onChange={(e) =>
                  onChange({
                    ...node,
                    renderer: e.target.value === 'agent' ? null : 'static-document-v1',
                    assignment_id: null,
                    agent_version_id: null,
                    input_schema: e.target.value === 'agent' ? 'text' : 'content',
                    output_schema: e.target.value === 'agent' ? 'text' : 'website',
                  })
                }
              >
                <option value="agent">{t('workflows.governedAgent')}</option>
                <option value="static-document-v1">{t('workflows.renderer')}</option>
              </select>,
            )}
            {node.renderer ? (
              <p className="af-note">{t('workflows.rendererHelp')}</p>
            ) : (
              <>
                {field(
                  'assignment',
                  <select
                    value={
                      node.assignment_id && !pinValid ? '__stale__' : (node.assignment_id ?? '')
                    }
                    onChange={(e) => {
                      const item = eligible.find((a) => a.id === e.target.value)
                      onChange({
                        ...node,
                        assignment_id: item?.id ?? null,
                        agent_version_id: item?.version_id ?? null,
                      })
                    }}
                  >
                    <option value="">{t('workflows.chooseAgent')}</option>
                    {node.assignment_id &&
                      !eligible.some(
                        (a) =>
                          a.id === node.assignment_id && a.version_id === node.agent_version_id,
                      ) && (
                        <option value="__stale__" disabled>
                          {t('workflows.agentMissing')}
                        </option>
                      )}
                    {eligible.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} · {a.role_name} · {a.version_number} · {a.id.slice(-6)}
                      </option>
                    ))}
                  </select>,
                )}
                {hasMoreTargets && (
                  <Button variant="secondary" disabled={loadingTargets} onClick={onMoreTargets}>
                    {t('workflows.more')}
                  </Button>
                )}
                {!eligible.length && <p className="af-note">{t('workflows.noAgents')}</p>}
                {field('pinnedVersion', <input readOnly value={node.agent_version_id ?? ''} />)}
                {published && (
                  <p className="af-note">
                    {published.model} · {published.version_number}
                  </p>
                )}
                {blueprintId && (
                  <Button variant="secondary" asChild>
                    <Link
                      to="/agents/$projectId/$blueprintId"
                      params={{ projectId: project, blueprintId }}
                    >
                      {t('workflows.openAgent')}
                    </Link>
                  </Button>
                )}
              </>
            )}
          </>
        )}
        {field(
          'inputSchema',
          <select
            value={node.input_schema}
            disabled={node.kind === 'start' || !!node.renderer}
            onChange={(e) =>
              onChange({
                ...node,
                input_schema: e.target.value as Node['input_schema'],
                ...(node.kind !== 'agent'
                  ? { output_schema: e.target.value as Node['output_schema'] }
                  : {}),
              })
            }
          >
            {schemas.map((schema) => (
              <option
                key={schema}
                disabled={
                  schema === 'website' &&
                  (node.kind === 'condition' || (node.kind === 'agent' && !node.renderer))
                }
              >
                {schema}
              </option>
            ))}
          </select>,
        )}
        {field(
          'outputSchema',
          <select
            value={node.output_schema}
            disabled={node.kind !== 'agent' || !!node.renderer}
            onChange={(e) =>
              onChange({ ...node, output_schema: e.target.value as Node['output_schema'] })
            }
          >
            {schemas.map((schema) => (
              <option key={schema} disabled={schema === 'website' && !node.renderer}>
                {schema}
              </option>
            ))}
          </select>,
        )}
        {node.kind === 'condition' && (
          <>
            {field(
              'operator',
              <select
                value={node.predicate?.operator ?? 'nonempty'}
                onChange={(e) =>
                  onChange({
                    ...node,
                    predicate: {
                      operator: e.target.value as 'contains' | 'equals' | 'nonempty',
                      literal: node.predicate?.literal ?? '',
                    },
                  })
                }
              >
                {['contains', 'equals', 'nonempty'].map((operator) => (
                  <option key={operator}>{operator}</option>
                ))}
              </select>,
            )}
            {field(
              'literal',
              <input
                value={node.predicate?.literal ?? ''}
                disabled={node.predicate?.operator === 'nonempty'}
                maxLength={100}
                onChange={(e) =>
                  onChange({
                    ...node,
                    predicate: {
                      operator: node.predicate?.operator ?? 'contains',
                      literal: e.target.value,
                    },
                  })
                }
              />,
            )}
          </>
        )}
      </fieldset>
      {issues
        .filter((issue) => issue.subject === node.id || issue.subject === 'graph')
        .map((issue) => (
          <p className="af-error" key={issue.subject + issue.code}>
            {t('workflows.issue.' + issue.code, { defaultValue: t('workflows.invalid') })}
          </p>
        ))}
      {task && (
        <section>
          <h3>{t('workflows.trace')}</h3>
          <p>{t('workflows.' + task.status)}</p>
          {task.core_run_id && run && (
            <TaskEvidence
              project={project}
              run={run}
              nodeId={node.id}
              coreRunId={task.core_run_id}
              status={task.status}
            />
          )}
          {task.core_run_id && (
            <Button variant="secondary" asChild>
              <Link
                to="/projects/$projectId/work"
                params={{ projectId: project }}
                search={{ selection: 'run:' + task.core_run_id }}
              >
                {t('workflows.inspectCore')}
              </Link>
            </Button>
          )}
          {(
            [
              ['inputArtifact', task.input_artifact_id],
              ['outputArtifact', task.output_artifact_id],
            ] as const
          ).map(
            ([label, id]) =>
              id && (
                <Button variant="ghost" key={label} onClick={() => onArtifact(id)}>
                  {t('workflows.' + label)}
                </Button>
              ),
          )}
        </section>
      )}
      <section className="wf-connections">
        <h3>{t('workflows.connections')}</h3>
        {graph.edges
          .filter((e) => e.source === node.id || e.target === node.id)
          .map((e) => (
            <div key={e.id}>
              <span>
                {e.source} · {e.source_port} → {e.target}
              </span>
              <Button
                variant="ghost"
                size="icon"
                disabled={readOnly}
                aria-label={t('workflows.removeEdge') + ' ' + e.id}
                onClick={() => onRemoveEdge(e.id)}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          ))}
      </section>
      {!!registry[node.kind].outputs.length && (
        <fieldset className="af-fields" disabled={readOnly}>
          {field(
            'sourcePort',
            <select
              value={
                registry[node.kind].outputs.includes(sourcePort)
                  ? sourcePort
                  : registry[node.kind].outputs[0]
              }
              onChange={(e) => setSourcePort(e.target.value)}
            >
              {registry[node.kind].outputs.map((port) => (
                <option key={port}>{port}</option>
              ))}
            </select>,
          )}
          {field(
            'targetNode',
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">{t('workflows.targetNode')}</option>
              {graph.nodes
                .filter((n) => n.id !== node.id && registry[n.kind].inputs)
                .map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.label} · {n.input_schema}
                  </option>
                ))}
            </select>,
          )}
          <Button
            variant="secondary"
            disabled={!target}
            onClick={() =>
              onConnect(
                registry[node.kind].outputs.includes(sourcePort)
                  ? sourcePort
                  : registry[node.kind].outputs[0]!,
                target,
              )
            }
          >
            {t('workflows.connect')}
          </Button>
        </fieldset>
      )}
    </div>
  )
}

function TaskEvidence({
  project,
  run,
  nodeId,
  coreRunId,
  status,
}: {
  project: string
  run: Run
  nodeId: string
  coreRunId: string
  status: string
}) {
  const { t } = useTranslation()
  const evidence = useQuery({
    queryKey: [
      'workflow-core-evidence',
      run.organization_id,
      project,
      run.id,
      nodeId,
      coreRunId,
      status,
    ],
    retry: false,
    queryFn: async ({ signal }) => {
      const value = scoped(
        await request(
          base(project) + '/resources/runs/' + encodeURIComponent(coreRunId),
          resourceSchema,
          { signal },
        ),
        run.organization_id,
        project,
      )
      if (value.id !== coreRunId) throw new Error('Core run identity differs.')
      if (value.verified) {
        const reference = value.references.workflow as Record<string, unknown> | undefined
        if (
          reference?.workflow_id !== run.workflow_id ||
          reference?.run_id !== run.id ||
          reference?.node_id !== nodeId
        )
          throw new Error('Core workflow provenance differs.')
      }
      return value
    },
  })
  const value = !evidence.error && evidence.data?.verified ? evidence.data : undefined
  if (evidence.isPending) return <DataState kind="loading" />
  if (evidence.error)
    return <QueryError error={evidence.error} retry={() => void evidence.refetch()} />
  return (
    <dl className="af-detail-list">
      <dt>{t('workflows.actualModel')}</dt>
      <dd>
        {typeof value?.references.model === 'string'
          ? value.references.model
          : t('agents.notRecorded')}
      </dd>
      <dt>{t('agents.usage')}</dt>
      <dd>
        {value?.references.usage_availability === 'measured' &&
        typeof value.references.total_tokens === 'number'
          ? value.references.total_tokens
          : t('agents.notRecorded')}
      </dd>
      <dt>{t('agents.recordedCost')}</dt>
      <dd>{t('agents.notRecorded')}</dd>
      {value && (
        <>
          <dt>{t('projects.date')}</dt>
          <dd>
            <time dateTime={value.created_at}>{value.created_at}</time>
          </dd>
        </>
      )}
    </dl>
  )
}
