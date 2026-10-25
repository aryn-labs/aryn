import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { useCatalog, useCopy, useIntelligenceContext } from '@/components/intelligence/hooks'
import {
  Badge,
  Facts,
  Field,
  JsonFacts,
  More,
  MutationDialog,
  Notice,
  Panel,
  QueryState,
} from '@/components/intelligence/IntelligenceUI'
import { suiteVersionSchema, candidateSchema } from '@/features/intelligence/api'
import { ScenarioDeclarationFields } from './ScenarioDeclarationFields'
import { emptyScenario, validScenario, type ScenarioDeclaration } from './scenarioDeclaration'
import type { z } from '@/lib/types/validation'

type Suite = z.infer<typeof suiteVersionSchema>
type Candidate = z.infer<typeof candidateSchema>
export function SuiteAuthoringPanel({ project }: { project: string }) {
  const c = useCopy(),
    permission = useIntelligenceContext(project),
    cache = useQueryClient(),
    query = useCatalog('/bench/suite-versions', suiteVersionSchema, project),
    candidates = useCatalog('/bench/scenario-candidates', candidateSchema, project),
    [create, setCreate] = useState(false),
    [family, setFamily] = useState(''),
    [version, setVersion] = useState('1.0.0'),
    [name, setName] = useState(''),
    [description, setDescription] = useState(''),
    [previous, setPrevious] = useState<Suite | null>(null),
    [candidate, setCandidate] = useState<Candidate | null>(null),
    [scenarios, setScenarios] = useState<ScenarioDeclaration[]>([emptyScenario()]),
    [review, setReview] = useState<{
      id: string
      digest: string
      candidate: boolean
      declaration: Record<string, unknown>
    } | null>(null),
    [reason, setReason] = useState('')
  const items = query.error ? [] : (query.data?.pages.flatMap((page) => page.items) ?? [])
  const candidateItems = candidates.error
    ? []
    : (candidates.data?.pages.flatMap((page) => page.items) ?? [])
  async function changed() {
    await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
    await cache.invalidateQueries({ queryKey: ['intelligence-suites'] })
    await cache.invalidateQueries({ queryKey: ['agent-editor'] })
  }
  function start(prior: Suite | null = null, from: Candidate | null = null) {
    setPrevious(prior)
    setFamily(prior?.family_key ?? '')
    setVersion('')
    setName('')
    setDescription('')
    setCandidate(from)
    setScenarios(from ? [from.scenario] : [emptyScenario()])
    setCreate(true)
  }
  return (
    <>
      <div className="intel-actions">
        <Button disabled={!permission.data?.permissions['version:create']} onClick={() => start()}>
          {c('authorSuite')}
        </Button>
      </div>
      <QueryState query={query} empty={!items.length} />
      <div className="intel-stack">
        {items.map((suite) => (
          <Panel key={suite.id} title={String(suite.definition.name ?? suite.family_key)}>
            <Badge value={suite.reviewed ? 'reviewed' : 'pending_review'} />
            <Facts
              values={[
                [c('suite'), <code>{suite.id}</code>],
                [c('evaluationVersion'), suite.evaluation_version],
                [c('digest'), <code>{suite.digest}</code>],
              ]}
            />
            <details>
              <summary>{c('reviewDeclaration')}</summary>
              <JsonFacts data={suite.definition} />
            </details>
            <div className="intel-actions">
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['version:approve'] || suite.reviewed}
                onClick={() => {
                  setReason('')
                  setReview({
                    id: suite.id,
                    digest: suite.digest,
                    candidate: false,
                    declaration: suite.definition,
                  })
                }}
              >
                {c('reviewSuite')}
              </Button>
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['version:create']}
                onClick={() => start(suite)}
              >
                {c('authorRevision')}
              </Button>
            </div>
          </Panel>
        ))}
      </div>
      <More query={query} />
      <Panel title={c('regressionCandidates')}>
        <Notice>{c('candidateHelp')}</Notice>
        <QueryState query={candidates} empty={!candidateItems.length} />
        {candidateItems.map((item) => (
          <div className="intel-row" key={item.id}>
            <code>{item.id}</code> · <Badge value={item.reviewed ? 'reviewed' : 'pending_review'} />
            <Facts
              values={[
                [c('origin'), item.source_id],
                [c('reason'), item.reason],
                [c('digest'), item.digest],
              ]}
            />
            <details>
              <summary>{c('reviewDeclaration')}</summary>
              <JsonFacts data={item.scenario} />
            </details>
            <div className="intel-actions">
              <Button
                variant="secondary"
                disabled={!permission.data?.permissions['version:approve'] || item.reviewed}
                onClick={() => {
                  setReason('')
                  setReview({
                    id: item.id,
                    digest: item.digest,
                    candidate: true,
                    declaration: item.scenario,
                  })
                }}
              >
                {c('reviewCandidate')}
              </Button>
              <Button
                disabled={!item.reviewed || !permission.data?.permissions['version:create']}
                onClick={() => start(null, item)}
              >
                {c('authorFromCandidate')}
              </Button>
            </div>
          </div>
        ))}
        <More query={candidates} />
      </Panel>
      {create && (
        <MutationDialog
          title={c('authorSuite')}
          description={c('suiteAuthoringHelp')}
          project={project}
          path="/bench/suite-versions"
          body={{
            family_key: family,
            evaluation_version: version,
            name: name.trim(),
            description,
            previous_version_id: previous?.id ?? null,
            candidate_id: candidate?.id ?? null,
            scenarios,
          }}
          allowed={
            !!permission.data?.permissions['version:create'] &&
            /^[A-Za-z0-9_-]{1,64}$/.test(family) &&
            /^\d+\.\d+\.\d+$/.test(version) &&
            !!name.trim() &&
            scenarios.every(validScenario) &&
            new Set(scenarios.map((item) => item.scenario_id)).size === scenarios.length
          }
          onClose={() => setCreate(false)}
          onSuccess={changed}
        >
          <Field label={c('suiteFamily')}>
            <input
              value={family}
              maxLength={64}
              readOnly={!!previous}
              onChange={(event) => setFamily(event.target.value)}
            />
          </Field>
          <Field label={c('evaluationVersion')}>
            <input
              value={version}
              maxLength={32}
              placeholder="1.0.0"
              onChange={(event) => setVersion(event.target.value)}
            />
          </Field>
          <Field label={c('title')}>
            <input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label={c('description')}>
            <textarea
              value={description}
              maxLength={1000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          {previous && (
            <code>
              {previous.id} · {previous.evaluation_version}
            </code>
          )}
          {scenarios.map((item, index) => (
            <fieldset key={index} disabled={!!candidate && index === 0}>
              <legend>
                {c('scenario')} {index + 1}
              </legend>
              <ScenarioDeclarationFields
                project={project}
                value={item}
                onChange={(value) =>
                  setScenarios(
                    scenarios.map((entry, position) => (position === index ? value : entry)),
                  )
                }
              />
              {scenarios.length > 1 && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    setScenarios(scenarios.filter((_, position) => position !== index))
                  }
                >
                  {c('removeScenario')}
                </Button>
              )}
            </fieldset>
          ))}
          <Button
            variant="secondary"
            disabled={scenarios.length >= 16}
            onClick={() =>
              setScenarios([
                ...scenarios,
                {
                  ...emptyScenario(),
                  scenario_id: 'observation_' + crypto.randomUUID().slice(0, 8),
                },
              ])
            }
          >
            {c('addScenario')}
          </Button>
        </MutationDialog>
      )}
      {review && (
        <MutationDialog
          title={c(review.candidate ? 'reviewCandidate' : 'reviewSuite')}
          description={c('suiteReviewHelp')}
          project={project}
          path={`/bench/${review.candidate ? 'scenario-candidates' : 'suite-versions'}/${review.id}/review`}
          body={{ expected_digest: review.digest, reason: reason.trim() }}
          allowed={!!permission.data?.permissions['version:approve'] && !!reason.trim()}
          onClose={() => setReview(null)}
          onSuccess={changed}
        >
          <JsonFacts data={review.declaration} />
          <code>{review.digest}</code>
          <Field label={c('reason')}>
            <textarea
              value={reason}
              maxLength={1000}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
        </MutationDialog>
      )}
    </>
  )
}
