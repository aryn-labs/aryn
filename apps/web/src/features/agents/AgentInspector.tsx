import { cloneElement, useId, useState, type ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Capabilities, Draft, Graph, Lifecycle, NodeType } from './api'
import { nodeRegistry } from './registry'

export function AgentInspector({
  selected,
  draft,
  capabilities,
  lifecycle,
  graph,
  readOnly,
  onChange,
  onGraph,
  onInvalid,
}: {
  selected: NodeType | null
  draft: Draft | null
  capabilities: Capabilities
  lifecycle: Lifecycle
  graph: Graph
  readOnly: boolean
  onChange: (draft: Draft) => void
  onGraph: (graph: Graph) => void
  onInvalid: (invalid: boolean) => void
}) {
  const { t } = useTranslation()
  const fieldPrefix = useId()
  const definition = selected ? nodeRegistry[selected] : nodeRegistry.agent
  const Icon = definition.icon
  const [agentSection, setSection] = useState<string>('agent')
  const section = selected && selected !== 'agent' ? definition.inspector : agentSection
  const [schemaText, setSchemaText] = useState(() =>
    draft?.output_contract.schema_definition
      ? JSON.stringify(draft.output_contract.schema_definition, null, 2)
      : '',
  )
  const [schemaInvalid, setSchemaInvalid] = useState(false)
  const field = (label: string, content: ReactElement<{ 'aria-labelledby'?: string }>) => (
    <label className="af-field">
      <span id={fieldPrefix + label}>{t('agents.' + label)}</span>
      {cloneElement(content, { 'aria-labelledby': fieldPrefix + label })}
    </label>
  )
  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    if (draft) onChange({ ...draft, [key]: value })
  }
  function number(event: React.ChangeEvent<HTMLInputElement>) {
    return event.target.valueAsNumber
  }
  return (
    <div className="af-inspector-content">
      <header className="af-inspector-title">
        <span className="af-node-icon">
          <Icon size={19} />
        </span>
        <div>
          <h2>{t('agents.' + definition.label)}</h2>
          <p>{t('agents.' + definition.description)}</p>
        </div>
        {selected && (
          <Button
            variant="ghost"
            size="icon"
            disabled={readOnly}
            aria-label={t('agents.remove')}
            onClick={() =>
              onGraph({
                ...graph,
                nodes: graph.nodes.filter((node) => node.id !== selected),
                connections: graph.connections.filter(
                  (edge) => edge.source !== selected && edge.target !== selected,
                ),
              })
            }
          >
            <Trash2 size={15} />
          </Button>
        )}
      </header>
      {selected === 'agent' && (
        <div className="af-inspector-sections" aria-label={t('agents.configure')}>
          {['agent', 'output', 'constraints', 'tools', 'budget', 'evaluation'].map((item) => (
            <button key={item} aria-pressed={section === item} onClick={() => setSection(item)}>
              {t('agents.' + item)}
            </button>
          ))}
        </div>
      )}
      {!draft ? (
        <p className="af-note">{t('agents.noModel')}</p>
      ) : (
        <fieldset disabled={readOnly} className="af-fields">
          {section === 'agent' && (
            <>
              <div className="af-section-label">{t('agents.identity')}</div>
              {field(
                'role',
                <input
                  value={draft.role}
                  maxLength={64}
                  required
                  onChange={(event) => update('role', event.target.value)}
                />,
              )}
              {field(
                'objective',
                <textarea
                  rows={2}
                  value={draft.objective}
                  maxLength={4000}
                  onChange={(event) => update('objective', event.target.value)}
                />,
              )}
              {field(
                'owner',
                <input
                  value={draft.owner ?? ''}
                  maxLength={64}
                  onChange={(event) => update('owner', event.target.value || null)}
                />,
              )}
              {field(
                'instructions',
                <textarea
                  rows={7}
                  required
                  minLength={20}
                  maxLength={12000}
                  value={draft.system_prompt}
                  onChange={(event) => update('system_prompt', event.target.value)}
                />,
              )}
              <div className="af-section-label">{t('agents.model')}</div>
              {field(
                'model',
                <select
                  required
                  value={draft.model}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      model: event.target.value,
                      model_policy: {
                        ...draft.model_policy,
                        primary_model: event.target.value,
                        allowed_models: [event.target.value],
                        provider: '9router',
                      },
                    })
                  }
                >
                  <option value="" disabled>
                    {t('agents.model')}
                  </option>
                  {!capabilities.models.some((model) => model.model_id === draft.model) && (
                    <option value={draft.model}>
                      {draft.model} · {t('agents.unavailable')}
                    </option>
                  )}
                  {capabilities.models.map((model) => (
                    <option key={model.model_id} value={model.model_id}>
                      {model.display_name}
                      {model.availability !== 'available' ? ` · ${t('agents.unavailable')}` : ''}
                    </option>
                  ))}
                </select>,
              )}
              {field('provider', <input readOnly value={draft.model_policy.provider} />)}
              <div className="af-field-pair">
                {field(
                  'temperature',
                  <input
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={Number.isFinite(draft.temperature) ? draft.temperature : ''}
                    onChange={(event) =>
                      onChange({
                        ...draft,
                        temperature: number(event),
                        model_policy: { ...draft.model_policy, temperature: number(event) },
                      })
                    }
                  />,
                )}
                {field(
                  'maxTokens',
                  <input
                    type="number"
                    min={128}
                    max={4096}
                    value={Number.isFinite(draft.max_tokens) ? draft.max_tokens : ''}
                    onChange={(event) =>
                      onChange({
                        ...draft,
                        max_tokens: number(event),
                        model_policy: { ...draft.model_policy, max_tokens: number(event) },
                      })
                    }
                  />,
                )}
              </div>
              {field(
                'version',
                <input
                  value={draft.version_number}
                  required
                  maxLength={32}
                  onChange={(event) => update('version_number', event.target.value)}
                />,
              )}
            </>
          )}
          {section === 'input' && (
            <p className="af-note">
              {t('agents.inputDescription')} {t('agents.promptPlaceholder')}
            </p>
          )}
          {section === 'output' && (
            <>
              {field(
                'outputFormat',
                <select
                  value={draft.output_contract.format}
                  onChange={(event) => {
                    update('output_contract', {
                      ...draft.output_contract,
                      format: event.target.value as Draft['output_contract']['format'],
                      schema_definition: null,
                    })
                    setSchemaText('')
                    setSchemaInvalid(false)
                    onInvalid(false)
                  }}
                >
                  {['text', 'markdown', 'json'].map((format) => (
                    <option key={format}>{format}</option>
                  ))}
                </select>,
              )}
              {field(
                'outputDescriptionField',
                <textarea
                  rows={3}
                  value={draft.output_contract.description ?? ''}
                  onChange={(event) =>
                    update('output_contract', {
                      ...draft.output_contract,
                      description: event.target.value || null,
                    })
                  }
                />,
              )}
              {field(
                'requiredSections',
                <textarea
                  rows={4}
                  value={draft.output_contract.required_sections.join('\n')}
                  onChange={(event) =>
                    update('output_contract', {
                      ...draft.output_contract,
                      required_sections: event.target.value.split('\n'),
                    })
                  }
                />,
              )}
              <label className="af-check">
                <input
                  type="checkbox"
                  checked={draft.output_contract.strict}
                  onChange={(event) =>
                    update('output_contract', {
                      ...draft.output_contract,
                      strict: event.target.checked,
                    })
                  }
                />
                {t('agents.strict')}
              </label>
              {draft.output_contract.format === 'json' &&
                field(
                  'jsonSchema',
                  <textarea
                    rows={8}
                    className="af-code"
                    aria-invalid={schemaInvalid}
                    value={schemaText}
                    onChange={(event) => {
                      setSchemaText(event.target.value)
                      try {
                        const value: unknown = event.target.value.trim()
                          ? JSON.parse(event.target.value)
                          : null
                        if (value !== null && (typeof value !== 'object' || Array.isArray(value)))
                          throw new Error()
                        update('output_contract', {
                          ...draft.output_contract,
                          schema_definition: value as Record<string, unknown> | null,
                        })
                        setSchemaInvalid(false)
                        onInvalid(false)
                      } catch {
                        setSchemaInvalid(true)
                        onInvalid(true)
                      }
                    }}
                  />,
                )}
              {schemaInvalid && (
                <p role="alert" className="af-error">
                  {t('agents.schemaError')}
                </p>
              )}
            </>
          )}
          {section === 'constraints' && (
            <>
              {field(
                'constraintsRules',
                <textarea
                  rows={5}
                  value={draft.constraints.operational_rules.join('\n')}
                  onChange={(event) =>
                    update('constraints', {
                      ...draft.constraints,
                      operational_rules: event.target.value.split('\n'),
                    })
                  }
                />,
              )}
              {field(
                'disallowed',
                <textarea
                  rows={4}
                  value={draft.constraints.disallowed_actions.join('\n')}
                  onChange={(event) =>
                    update('constraints', {
                      ...draft.constraints,
                      disallowed_actions: event.target.value.split('\n'),
                    })
                  }
                />,
              )}
              <label className="af-check">
                <input
                  type="checkbox"
                  checked={draft.constraints.require_evidence_citation}
                  onChange={(event) =>
                    update('constraints', {
                      ...draft.constraints,
                      require_evidence_citation: event.target.checked,
                    })
                  }
                />
                {t('agents.citations')}
              </label>
              {field(
                'timeout',
                <input
                  type="number"
                  min={1}
                  max={3600}
                  value={draft.constraints.max_execution_time_seconds || ''}
                  onChange={(event) =>
                    update('constraints', {
                      ...draft.constraints,
                      max_execution_time_seconds: number(event),
                    })
                  }
                />,
              )}
            </>
          )}
          {section === 'tools' && (
            <>
              <p className="af-note">
                <ShieldCheck size={18} />
                {t('agents.toolUnavailable')}
              </p>
              <dl className="af-detail-list">
                <dt>{t('agents.tools')}</dt>
                <dd>0</dd>
                <dt>Network / File write / Code execution</dt>
                <dd>{t('agents.unavailable')}</dd>
              </dl>
              <div className="af-field">
                <span>Forbidden tools</span>
                <pre className="af-code">{draft.tool_policy.forbidden_tools.join(', ')}</pre>
              </div>
            </>
          )}
          {section === 'budget' && (
            <>
              {field(
                'totalTokens',
                <input
                  type="number"
                  min={1}
                  max={100000}
                  value={draft.budget_policy.max_tokens_per_run || ''}
                  onChange={(event) =>
                    update('budget_policy', {
                      ...draft.budget_policy,
                      max_tokens_per_run: number(event),
                    })
                  }
                />,
              )}
              {field(
                'cost',
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  value={
                    Number.isFinite(draft.budget_policy.max_cost_usd)
                      ? draft.budget_policy.max_cost_usd
                      : ''
                  }
                  onChange={(event) =>
                    update('budget_policy', { ...draft.budget_policy, max_cost_usd: number(event) })
                  }
                />,
              )}
              {field(
                'timeout',
                <input
                  type="number"
                  min={1}
                  max={3600}
                  value={draft.budget_policy.timeout_seconds || ''}
                  onChange={(event) =>
                    update('budget_policy', {
                      ...draft.budget_policy,
                      timeout_seconds: number(event),
                    })
                  }
                />,
              )}
              {field(
                'turns',
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={draft.budget_policy.max_turns || ''}
                  onChange={(event) =>
                    update('budget_policy', { ...draft.budget_policy, max_turns: number(event) })
                  }
                />,
              )}
              <p className="af-note">{t('agents.oneTurn')}</p>
            </>
          )}
          {section === 'evaluation' && (
            <>
              {field(
                'suite',
                <select
                  value={draft.evaluation_reference.suite_id}
                  onChange={(event) => {
                    const suite = lifecycle.evaluation_suites.find(
                      (item) => item.suite_id === event.target.value,
                    )
                    const scenarios = suite?.scenarios as { scenario_id: string }[] | undefined
                    update('evaluation_reference', {
                      ...draft.evaluation_reference,
                      suite_id: event.target.value,
                      evaluation_version: suite?.evaluation_version ?? '',
                      required_scenarios: scenarios?.map((scenario) => scenario.scenario_id) ?? [],
                      evaluation_id: null,
                    })
                  }}
                >
                  {lifecycle.evaluation_suites.map((suite) => (
                    <option key={suite.suite_id}>{suite.suite_id}</option>
                  ))}
                </select>,
              )}
              {field(
                'threshold',
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={
                    Number.isFinite(draft.evaluation_reference.min_score_threshold)
                      ? draft.evaluation_reference.min_score_threshold
                      : ''
                  }
                  onChange={(event) =>
                    update('evaluation_reference', {
                      ...draft.evaluation_reference,
                      min_score_threshold: number(event),
                    })
                  }
                />,
              )}
              <ul className="af-scenarios">
                {draft.evaluation_reference.required_scenarios.map((scenario) => (
                  <li key={scenario}>{scenario}</li>
                ))}
              </ul>
            </>
          )}
        </fieldset>
      )}
      {selected &&
        graph.connections.filter((edge) => edge.source === selected || edge.target === selected)
          .length > 0 && (
          <details className="af-connection-list">
            <summary>{t('agents.connection')}</summary>
            {graph.connections
              .filter((edge) => edge.source === selected || edge.target === selected)
              .map((edge) => (
                <div key={`${edge.source}:${edge.target}`}>
                  <span>
                    {t('agents.' + edge.source)} → {t('agents.' + edge.target)}
                  </span>
                  <button
                    disabled={readOnly}
                    aria-label={`${t('agents.removeEdge')} ${edge.source} ${edge.target}`}
                    onClick={() =>
                      onGraph({
                        ...graph,
                        connections: graph.connections.filter((item) => item !== edge),
                      })
                    }
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
          </details>
        )}
      <p className="af-inspector-governance">
        <ShieldCheck size={14} />
        {t('agents.governed')}
      </p>
      {definition.category === 'policy' && <p className="af-note">{t('agents.policyScope')}</p>}
    </div>
  )
}
