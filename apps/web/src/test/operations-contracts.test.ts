import { describe, it, expect } from 'vitest'
import { triggerRegistry, triggerAvailable } from '@/features/automations/triggers'
import { policySchema, triggerSchema, scheduleSchema } from '@/features/automations/api'
import { operationsId, operationsEn } from '@/i18n/operations'
describe('Runs and Automation contracts', () => {
  it('reads legacy signed schedules without requiring an additive cron field', () => {
    const schedule = scheduleSchema.parse({
      kind: 'daily',
      timezone: 'UTC',
      start_at: '2026-10-12T00:00:00Z',
      interval_minutes: 60,
      local_time: '09:00',
      weekdays: [0, 1, 2, 3, 4],
    })
    expect(schedule.cron_expression).toBeNull()
  })
  it('keeps six extension definitions while ingress and MCP require actual capabilities', () => {
    expect(triggerRegistry.map((item) => item.kind)).toEqual([
      'interval',
      'daily',
      'weekly',
      'cron',
      'webhook',
      'mcp',
    ])
    const capability = triggerSchema.parse({
      organization_id: 'org',
      project_id: 'project',
      mode: 'local',
      webhook_available: false,
      webhook_reason: 'hosted_https_ingress_required',
      webhook_authentication: 'scoped_bearer_over_tls',
      mcp_available: false,
      kinds: ['interval', 'daily', 'weekly', 'cron', 'webhook'],
      scheduler: { authority: 'core_single_owner', last_tick_at: null, error_code: null },
    })
    expect(triggerAvailable('cron', capability)).toBe(true)
    expect(triggerAvailable('webhook', capability)).toBe(false)
    expect(triggerAvailable('mcp', capability)).toBe(false)
    expect(triggerAvailable('cron')).toBe(false)
    expect(
      triggerAvailable('webhook', { ...capability, mode: 'hosted', webhook_available: true }),
    ).toBe(true)
  })
  it('enforces Core policy bounds and distinguishes operational statuses in both locales', () => {
    const policy = {
      overlap: 'skip',
      missed: 'skip',
      catch_up_limit: 1,
      max_runs_per_day: 24,
      max_tokens_per_task: 4096,
      max_attempts: 1,
      backoff_seconds: 60,
    }
    expect(policySchema.safeParse(policy).success).toBe(true)
    for (const [key, value] of Object.entries({
      catch_up_limit: 4,
      max_runs_per_day: 101,
      max_tokens_per_task: 127,
      max_attempts: 4,
      backoff_seconds: 59,
    }))
      expect(policySchema.safeParse({ ...policy, [key]: value }).success).toBe(false)
    expect(Object.keys(operationsEn).sort()).toEqual(Object.keys(operationsId).sort())
    expect(Object.keys(operationsEn.states).sort()).toEqual(Object.keys(operationsId.states).sort())
    expect(operationsId.states.skipped).not.toBe(operationsId.states.completed)
    expect(operationsId.states.stopping).not.toBe(operationsId.states.cancelled)
  })
})
