import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { request } from '@/lib/api/client'
import { z } from '@/lib/types/validation'
import { Button } from '@/components/ui/button'
import { QueryError } from '@/components/feedback/DataState'
import { post, scoped } from '@/features/agents/api'
import './preferences.css'
import { translate } from '@/i18n'

const feature = z.object({
  name: z.string(),
  description: z.string(),
  tools: z.array(z.string()),
  availability: z.string(),
  configuration_readiness: z.string(),
  risk: z.string(),
  required_permissions: z.array(z.string()),
  execution_environment: z.string(),
  approval_required: z.boolean(),
  enabled: z.boolean(),
  executable: z.boolean(),
  verification: z.string(),
  reason: z.string(),
  native_api: z.boolean(),
  native_cli: z.boolean(),
})
const inventorySchema = z.object({
  organization_id: z.string(),
  project_id: z.string(),
  attestation: z.string(),
  inventory: z.object({
    version: z.string(),
    source_revision: z.string().nullable(),
    configuration_id: z.string().nullable(),
    reason: z.string(),
    toolsets: z.array(feature),
    features: z.array(feature),
    skills: z.array(
      z.object({
        name: z.string(),
        description: z.string(),
        category: z.string(),
        enabled: z.boolean(),
        content_hash: z.string().nullable(),
        source_verified: z.boolean(),
      }),
    ),
    settings: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])),
  }),
})
const connectionSchema = z.object({
  supported: z.boolean(),
  reason: z.string(),
  base_url: z.string().optional(),
  configuration_id: z.string().optional(),
  credential_configured: z.boolean().optional(),
  credential_storage: z.string().optional(),
  administration_available: z.boolean().optional(),
  connected: z.boolean().optional(),
  discovery_valid: z.boolean().optional(),
  runtime_binding_verified: z.boolean().optional(),
  models: z
    .array(
      z.object({
        model_id: z.string(),
        display_name: z.string(),
        provider: z.string(),
        provider_identity_status: z.string(),
        availability: z.string(),
      }),
    )
    .optional(),
})

function useRuntimeInventory() {
  const { project, context } = useWorkspace()
  return useQuery({
    queryKey: ['runtime-inventory', context?.organization.id, project?.id],
    enabled: !!project && !!context,
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(`/api/projects/${encodeURIComponent(project!.id)}/runtime`, inventorySchema, {
          signal,
        }),
        context!.organization.id,
        project!.id,
      ),
  })
}

export function RuntimeControl() {
  const { project, context, csrf } = useWorkspace()
  const inventory = useRuntimeInventory()
  const client = useQueryClient()
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [tab, setTab] = useState<'toolsets' | 'skills' | 'features' | 'settings'>('toolsets')
  const [skillPreview, setSkillPreview] = useState<{ name: string; content: string } | null>(null)
  const reviewSkill = useMutation({
    mutationFn: (selection: { name: string; content_hash: string }) =>
      post(
        `/api/projects/${encodeURIComponent(project?.id ?? '')}/runtime/skills/read`,
        z.object({ name: z.string(), content: z.string(), content_hash: z.string() }),
        csrf ?? '',
        selection,
      ),
    onSuccess: (value) => setSkillPreview(value),
  })
  const path = `/api/projects/${encodeURIComponent(project?.id ?? '')}/model-connection`
  const connection = useQuery({
    queryKey: ['model-connection', context?.organization.id, project?.id],
    enabled: !!project && !!context,
    retry: false,
    queryFn: ({ signal }) => request(path, connectionSchema, { signal }),
  })
  const change = useMutation({
    mutationFn: (revoke: boolean) =>
      post(path + (revoke ? '/revoke' : ''), connectionSchema, csrf ?? '', {
        expected_configuration_id: connection.data?.configuration_id,
        ...(revoke ? {} : { base_url: baseUrl || connection.data?.base_url, api_key: apiKey }),
      }),
    onSettled: async () => {
      setApiKey('')
      await client.invalidateQueries({ queryKey: ['model-connection'] })
      await client.invalidateQueries({ queryKey: ['runtime-inventory'] })
      await client.invalidateQueries({ queryKey: ['workspace-status'] })
    },
  })
  if (!project || !context) return null
  const data = inventory.data?.inventory
  const administrative = context.user.role === 'admin' && connection.data?.administration_available
  return (
    <div className="preferences-grid">
      <section className="runtime-card" aria-labelledby="gateway-control-heading">
        <h2 id="gateway-control-heading">Model Gateway · 9Router</h2>
        <p className="muted">{translate('ui.active_model_unavailable')}</p>
        <p className="muted">
          ARYN Core → Hermes → 9Router. Select an exact model in Agent Factory or Chat.
        </p>
        {connection.isPending ? (
          <p role="status">Checking connection…</p>
        ) : connection.isError ? (
          <QueryError error={connection.error} retry={() => void connection.refetch()} />
        ) : (
          <>
            <p role="status">
              {connection.data?.connected ? 'Connected' : 'Unavailable'} · {connection.data?.reason}
            </p>
            <p>
              Runtime binding:{' '}
              {connection.data?.runtime_binding_verified ? 'verified' : 'unverified'}
            </p>
            <p>
              Credential: {connection.data?.credential_configured ? 'configured' : 'not configured'}{' '}
              · trusted server memory
            </p>
            <p className="muted">
              Persistent credential storage requires a trusted secret provider before multi-user
              hosting. Upstream attempts and final cost remain unverified.
            </p>
            <Button
              variant="secondary"
              onClick={async () => {
                await request(path + '?refresh=true', connectionSchema)
                await connection.refetch()
              }}
            >
              Refresh model catalog
            </Button>
            {administrative && (
              <form
                className="gateway-fields"
                onSubmit={(event) => {
                  event.preventDefault()
                  change.mutate(false)
                }}
              >
                <label>
                  Gateway URL
                  <input
                    type="url"
                    value={baseUrl}
                    placeholder={connection.data?.base_url}
                    onChange={(event) => setBaseUrl(event.target.value)}
                  />
                </label>
                <label>
                  Replace API key
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                  />
                </label>
                <p className="muted">
                  The server keeps the key in process memory. Restart removes Web-supplied
                  credentials. Active or uncertain runs block changes.
                </p>
                <div>
                  <Button type="submit" disabled={change.isPending || !csrf}>
                    Replace connection
                  </Button>{' '}
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={change.isPending || !csrf}
                    onClick={() => change.mutate(true)}
                  >
                    Revoke connection
                  </Button>
                </div>
              </form>
            )}
            {change.isError && (
              <QueryError error={change.error} retry={() => void connection.refetch()} />
            )}
            {change.isSuccess && <p role="status">Connection lifecycle updated.</p>}
            <ul className="provider-preferences">
              {connection.data?.models?.map((model) => (
                <li key={model.model_id}>
                  <div>
                    <strong>{model.display_name}</strong>
                    <code>{model.model_id}</code>
                    <span>
                      {model.provider_identity_status === 'reported'
                        ? model.provider
                        : 'Provider identity unknown'}{' '}
                      · {model.availability}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <NativeActionApproval />
      <section className="runtime-card" aria-labelledby="hermes-control-heading">
        <h2 id="hermes-control-heading">Hermes Runtime</h2>
        {inventory.isPending ? (
          <p role="status">Discovering runtime…</p>
        ) : inventory.isError ? (
          <QueryError error={inventory.error} retry={() => void inventory.refetch()} />
        ) : (
          <>
            <p>
              Version: {data?.version} · {data?.reason}
            </p>
            <p className="muted">
              Discovery grants no permission. Native operations require Core admission and a
              verified isolated worker.
            </p>
            <div className="runtime-tabs" aria-label="Runtime resources">
              {(['toolsets', 'skills', 'features', 'settings'] as const).map((name) => (
                <Button
                  key={name}
                  variant="secondary"
                  aria-pressed={tab === name}
                  onClick={() => setTab(name)}
                >
                  {name}
                </Button>
              ))}
            </div>
            {tab === 'settings' ? (
              <dl>
                {Object.entries(data?.settings ?? {}).map(([name, value]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : tab === 'skills' ? (
              <ul className="provider-preferences">
                {data?.skills.map((skill) => (
                  <li key={skill.name}>
                    <div>
                      <strong>{skill.name}</strong>
                      <span>{skill.description}</span>
                      <span>
                        {skill.category} ·{' '}
                        {skill.source_verified ? 'source verified' : 'source review required'}
                      </span>
                      {skill.content_hash && (
                        <Button
                          variant="secondary"
                          disabled={!csrf || reviewSkill.isPending}
                          onClick={() =>
                            reviewSkill.mutate({
                              name: skill.name,
                              content_hash: skill.content_hash!,
                            })
                          }
                        >
                          Review pinned content
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <ul className="provider-preferences">
                {data?.[tab].map((item) => (
                  <li key={item.name}>
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.description}</span>
                      <span>
                        {item.availability} · {item.executable ? 'executable' : 'BLOCKED'} ·{' '}
                        {item.reason}
                      </span>
                      <span>
                        Risk: {item.risk} · Environment: {item.execution_environment} · Approval:{' '}
                        {item.approval_required ? 'required' : 'not required'}
                      </span>
                      <span>
                        Native API: {String(item.native_api)} · CLI: {String(item.native_cli)} ·
                        Configuration: {item.configuration_readiness}
                      </span>
                      <details>
                        <summary>Tools and permissions</summary>
                        <p>{item.tools.join(', ') || 'No tools reported'}</p>
                        <p>{item.required_permissions.join(', ')}</p>
                      </details>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Button variant="secondary" onClick={() => void inventory.refetch()}>
              Refresh runtime discovery
            </Button>
            {reviewSkill.isError && (
              <QueryError error={reviewSkill.error} retry={() => void inventory.refetch()} />
            )}
            {skillPreview && (
              <details open>
                <summary>{skillPreview.name} · guidance only</summary>
                <pre className="af-code">{skillPreview.content}</pre>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  )
}

function NativeActionApproval() {
  const { context, project, csrf } = useWorkspace()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [identifier, setIdentifier] = useState('')
  const [argumentsText, setArgumentsText] = useState('{}')
  const [invalid, setInvalid] = useState(false)
  const path = `/api/projects/${encodeURIComponent(project?.id ?? '')}/runtime/native-tools`
  const status = useQuery({
    queryKey: ['native-tools', context?.organization.id, project?.id],
    enabled: !!project && !!context,
    retry: false,
    queryFn: ({ signal }) =>
      request(
        path,
        z.object({
          configured: z.boolean(),
          tools: z.array(z.string()),
          bindings: z.array(z.object({ namespace: z.string(), available: z.boolean() })),
          registrations: z
            .array(
              z.object({
                connection_id: z.string(),
                tool_name: z.string(),
                expires_at: z.number(),
              }),
            )
            .optional(),
        }),
        { signal },
      ),
  })
  const approve = useMutation({
    mutationFn: (argumentsValue: Record<string, unknown>) =>
      post(
        path + '/approve',
        z.object({ binding_hash: z.string(), expires_at: z.number() }),
        csrf ?? '',
        { connection_id: identifier, tool_name: name, arguments: argumentsValue, ttl_seconds: 300 },
      ),
    onSuccess: async () => {
      setArgumentsText('{}')
      await status.refetch()
      await queryClient.invalidateQueries({ queryKey: ['agent-editor'] })
    },
  })
  const revoke = useMutation({
    mutationFn: (connection: string) =>
      post(
        path + '/' + encodeURIComponent(connection) + '/revoke',
        z.object({ revoked: z.boolean() }),
        csrf ?? '',
        {},
      ),
    onSuccess: async () => {
      await status.refetch()
      await queryClient.invalidateQueries({ queryKey: ['agent-editor'] })
    },
  })
  return (
    <section className="runtime-card" aria-labelledby="native-actions-heading">
      <h2 id="native-actions-heading">Core native action approvals</h2>
      <p className="muted">
        Approve exact arguments for a credential-free, network-denied run workspace. Agent Factory
        must pin this binding to an immutable version. Approval expires after five minutes.
      </p>
      {status.isError ? (
        <QueryError error={status.error} retry={() => void status.refetch()} />
      ) : !status.data?.configured ? (
        <p role="status">
          BLOCKED · Configure a reviewed immutable native worker through trusted server
          administration.
        </p>
      ) : (
        <>
          {context?.user.role === 'admin' && (
            <form
              className="gateway-fields"
              onSubmit={(event) => {
                event.preventDefault()
                try {
                  const value: unknown = JSON.parse(argumentsText)
                  if (!value || typeof value !== 'object' || Array.isArray(value))
                    throw new Error('invalid')
                  setInvalid(false)
                  approve.mutate(value as Record<string, unknown>)
                } catch {
                  setInvalid(true)
                }
              }}
            >
              <label>
                Binding identifier
                <input
                  required
                  pattern="[a-z][a-z0-9_]{0,23}"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
              </label>
              <label>
                Installed native tool
                <select required value={name} onChange={(event) => setName(event.target.value)}>
                  <option value="">Select a tool</option>
                  {status.data.tools.map((tool) => (
                    <option key={tool}>{tool}</option>
                  ))}
                </select>
              </label>
              <label>
                Exact action arguments (JSON)
                <textarea
                  rows={5}
                  value={argumentsText}
                  aria-invalid={invalid}
                  onChange={(event) => setArgumentsText(event.target.value)}
                />
              </label>
              {invalid && (
                <p role="alert">Enter a JSON object matching the installed tool schema.</p>
              )}
              <Button type="submit" disabled={!csrf || approve.isPending}>
                Approve exact sandbox action
              </Button>
            </form>
          )}
          {approve.isSuccess && (
            <p role="status">
              Action approved. Refresh Agent Factory capabilities and select its grant.
            </p>
          )}
          {approve.isError && (
            <QueryError error={approve.error} retry={() => void status.refetch()} />
          )}
          <ul>
            {status.data.bindings.map((binding) => (
              <li key={binding.namespace}>
                {binding.namespace} ·{' '}
                {binding.available ? 'approval current' : 'approval unavailable'}
              </li>
            ))}
          </ul>
          {context?.user.role === 'admin' &&
            status.data.registrations?.map((entry) => (
              <Button
                key={entry.connection_id}
                variant="secondary"
                disabled={!csrf || revoke.isPending}
                onClick={() => revoke.mutate(entry.connection_id)}
              >
                Revoke {entry.connection_id}
              </Button>
            ))}
          {revoke.isError && (
            <QueryError error={revoke.error} retry={() => void status.refetch()} />
          )}
        </>
      )}
    </section>
  )
}
