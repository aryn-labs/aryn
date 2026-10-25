import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useCopy, useIntelligenceContext } from '@/components/intelligence/hooks'
import { Field, MutationDialog, Notice } from '@/components/intelligence/IntelligenceUI'
import { ScenarioDeclarationFields } from './ScenarioDeclarationFields'
import { emptyScenario, validScenario } from './scenarioDeclaration'

export function ScenarioCandidateDialog({
  project,
  sourceKind,
  sourceId,
  onClose,
}: {
  project: string
  sourceKind: 'capsule' | 'evaluation'
  sourceId: string
  onClose: () => void
}) {
  const c = useCopy(),
    permission = useIntelligenceContext(project),
    cache = useQueryClient(),
    [scenario, setScenario] = useState(emptyScenario),
    [reason, setReason] = useState('')
  return (
    <MutationDialog
      title={c('createCandidate')}
      description={c('candidateHelp')}
      project={project}
      path="/bench/scenario-candidates"
      body={{ source_kind: sourceKind, source_id: sourceId, scenario, reason: reason.trim() }}
      allowed={
        !!permission.data?.permissions['version:create'] &&
        validScenario(scenario) &&
        !!reason.trim()
      }
      onClose={onClose}
      onSuccess={async () => {
        await cache.invalidateQueries({ queryKey: ['intelligence-catalog'] })
      }}
    >
      <code>{sourceId}</code>
      <Notice>{c('candidateHelp')}</Notice>
      <ScenarioDeclarationFields project={project} value={scenario} onChange={setScenario} />
      <Field label={c('reason')}>
        <textarea
          value={reason}
          maxLength={1000}
          onChange={(event) => setReason(event.target.value)}
        />
      </Field>
    </MutationDialog>
  )
}
