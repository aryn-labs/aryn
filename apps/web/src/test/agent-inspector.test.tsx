import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import i18n from '@/i18n'
import { AgentInspector } from '@/features/agents/AgentInspector'
import type { Draft } from '@/features/agents/api'
import { initialGraph } from '@/features/agents/registry'

const draft: Draft = {
  schema_version: '1.0.0',
  version_number: '1.0.0',
  system_prompt: 'Answer accurately using available evidence.',
  model: 'test/model',
  temperature: 0.3,
  max_tokens: 2048,
  tool_grants: [],
  role: 'general_agent',
  objective: '',
  owner: null,
  metadata: {},
  output_contract: {
    format: 'text',
    schema_definition: null,
    required_sections: [],
    description: null,
    strict: false,
  },
  constraints: {
    disallowed_actions: [],
    operational_rules: [],
    require_evidence_citation: true,
    max_execution_time_seconds: 120,
  },
  tool_policy: {
    tool_grants: [],
    forbidden_tools: ['terminal'],
    deny_by_default: true,
    network_access: false,
    file_write_access: false,
    code_execution: false,
  },
  model_policy: {
    primary_model: 'test/model',
    provider: '9router',
    allowed_models: ['test/model'],
    temperature: 0.3,
    max_tokens: 2048,
    allow_fallback: false,
    stop_sequences: [],
  },
  budget_policy: {
    max_tokens_per_run: 4096,
    max_turns: 1,
    max_cost_usd: 0.5,
    timeout_seconds: 120,
  },
  evaluation_reference: {
    suite_id: 'test',
    evaluation_version: '1.0.0',
    min_score_threshold: 0.8,
    required_scenarios: [],
    evaluation_id: null,
  },
}

function inspector(availability?: string, listed = true) {
  const onChange = vi.fn()
  render(
    <AgentInspector
      selected="agent"
      draft={draft}
      capabilities={{
        organization_id: 'org-test',
        project_id: 'project-test',
        models: listed ? [{ model_id: draft.model, display_name: draft.model, availability }] : [],
        draft_defaults: draft,
        tools: [],
        telemetry: 'core_lifecycle_only',
      }}
      lifecycle={{
        organization_id: 'org-test',
        project_id: 'project-test',
        blueprints: [],
        versions: [],
        assignments: [],
        evaluations: [],
        evaluation_suites: [],
        accepted_baselines: [],
        permissions: {},
      }}
      graph={initialGraph()}
      readOnly={false}
      onChange={onChange}
      onGraph={vi.fn()}
      onInvalid={vi.fn()}
    />,
  )
  return onChange
}

describe('Agent Inspector model readiness', () => {
  it.each([
    ['id-ID', 'unknown', 'Belum terverifikasi'],
    ['id-ID', undefined, 'Belum terverifikasi'],
    ['id-ID', 'unavailable', 'Tidak tersedia'],
    ['en-US', 'unknown', 'Unverified'],
    ['en-US', 'unavailable', 'Unavailable'],
  ])(
    'shows %s readiness for %s without claiming a provider failure',
    async (locale, status, label) => {
      await i18n.changeLanguage(locale)
      inspector(status)
      expect(screen.getByRole('option', { name: `test/model · ${label}` })).toBeInTheDocument()
      expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('test/model')
      if (status !== 'unavailable')
        expect(screen.getByText(i18n.t('agents.modelCatalogOnly'))).toBeVisible()
      else expect(screen.queryByText(i18n.t('agents.modelCatalogOnly'))).not.toBeInTheDocument()
    },
  )

  it('shows verified readiness without an unavailable warning', () => {
    inspector('available')
    expect(screen.getByRole('option', { name: 'test/model' })).toBeInTheDocument()
    expect(screen.queryByText(i18n.t('agents.modelCatalogOnly'))).not.toBeInTheDocument()
  })

  it('preserves a saved model missing from discovery without claiming inference failure', () => {
    const onChange = inspector(undefined, false)
    expect(
      screen.getByRole('option', { name: 'test/model · Not in the current catalog' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('test/model')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('keeps model selection as draft configuration without granting tools or fallback', async () => {
    const onChange = inspector('unknown')
    await userEvent
      .setup()
      .selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'test/model')
    expect(onChange).toHaveBeenCalledWith({
      ...draft,
      model_policy: { ...draft.model_policy, allowed_models: ['test/model'] },
    })
  })
})
