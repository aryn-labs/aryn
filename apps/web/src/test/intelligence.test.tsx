import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { Badge, DateValue, Notice } from '@/components/intelligence/IntelligenceUI'
import {
  scoped,
  replaySchema,
  evidenceStates,
  incidentStates,
  scenarioSchema,
} from '@/features/intelligence/api'
import { intelligenceId, intelligenceEn } from '@/i18n/intelligence'

describe('Intelligence governance presentation', () => {
  it('separates passed from unverified evidence', async () => {
    await i18n.changeLanguage('id-ID')
    render(
      <>
        <Badge value="passed" />
        <Badge value="UNVERIFIED" />
      </>,
    )
    expect(screen.getByText('Lulus')).toHaveAttribute('data-tone', 'good')
    expect(screen.getByText('Tidak terverifikasi')).toHaveAttribute('data-tone', 'warn')
  })
  it.each(['CONFLICTING', 'INSUFFICIENT_EVIDENCE', 'OUTCOME_UNKNOWN', 'DEGRADED'])(
    'keeps %s visible without a success tone',
    (value) => {
      render(<Badge value={value} />)
      expect(screen.getByText(value)).not.toHaveAttribute('data-tone', 'good')
    },
  )
  it('does not imply recovered from execution state', () => {
    render(<Badge value="action_completed" />)
    expect(screen.getByText('action_completed')).toHaveAttribute('data-tone', 'neutral')
  })
  it('has all authoritative evidence and incident states', () => {
    expect(evidenceStates).toHaveLength(4)
    expect(incidentStates).toContain('OUTCOME_UNKNOWN')
    expect(incidentStates).toHaveLength(8)
  })
  it('rejects cross-project data even with a matching resource ID', () => {
    expect(() =>
      scoped({ id: 'record', organization_id: 'org', project_id: 'other' }, 'org', 'owner'),
    ).toThrow()
  })
  it('forbids live effects, inference and promotion in replay responses', () => {
    const report = {
      id: 'replay',
      organization_id: 'org',
      project_id: 'proj',
      created_at: '2026-10-12T00:00:00Z',
      capsule_id: 'cap',
      capsule_digest: 'digest',
      scenario_id: 'scenario',
      backend: 'deterministic_in_memory',
      model: null,
      provider: null,
      live_write_calls: 0,
      promotion_evidence: false,
      passed: true,
      graders: [],
      digest: 'digest',
    }
    expect(replaySchema.safeParse(report).success).toBe(true)
    for (const change of [
      { live_write_calls: 1 },
      { model: 'model' },
      { provider: 'provider' },
      { promotion_evidence: true },
    ])
      expect(replaySchema.safeParse({ ...report, ...change }).success).toBe(false)
  })
  it('allows legacy scenario results without fabricating graders or trace', () => {
    const result = scenarioSchema.parse({
      scenario_id: 'legacy',
      name: 'Legacy',
      category: 'research',
      passed: true,
      score: 1,
      actual_output: 'Stored history',
      failure_reason: null,
      latency_seconds: 1,
    })
    expect(result.grader_results).toEqual([])
    expect(result.execution).toBeUndefined()
    expect(result.state).toBe('unverifiable')
  })
  it('supports Indonesian and English with matching keys', async () => {
    expect(Object.keys(intelligenceId).sort()).toEqual(Object.keys(intelligenceEn).sort())
    await i18n.changeLanguage('en-US')
    render(
      <>
        <Badge value="UNVERIFIED" />
        <DateValue value="invalid" />
        <Notice warning>{i18n.t('intelligence.replayBoundary')}</Notice>
      </>,
    )
    expect(screen.getByText('Unverified')).toBeVisible()
    expect(screen.getByText(/promotion_evidence=false/)).toBeVisible()
    expect(screen.getByText('—')).toBeVisible()
  })
})
