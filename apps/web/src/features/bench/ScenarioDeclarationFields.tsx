import { useQuery } from '@tanstack/react-query'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { useCopy } from '@/components/intelligence/hooks'
import { Field, Notice, QueryState } from '@/components/intelligence/IntelligenceUI'
import { base, request, scoped, nativeToolCatalogSchema } from '@/features/intelligence/api'
import type { ScenarioDeclaration } from './scenarioDeclaration'

export function ScenarioDeclarationFields({
  project,
  value,
  onChange,
}: {
  project: string
  value: ScenarioDeclaration
  onChange: (value: ScenarioDeclaration) => void
}) {
  const c = useCopy(),
    w = useWorkspace()
  const query = useQuery({
    queryKey: [
      'intelligence-native-tools',
      w.context?.user.id,
      w.context?.organization.id,
      project,
    ],
    enabled: !!w.context?.projects.some((item) => item.id === project),
    retry: false,
    queryFn: async ({ signal }) =>
      scoped(
        await request(base(project) + '/runtime/native-tools', nativeToolCatalogSchema, { signal }),
        w.context!.organization.id,
        project,
      ),
  })
  const change = (patch: Partial<ScenarioDeclaration>) => onChange({ ...value, ...patch })
  return (
    <>
      <Field label={c('scenarioIdentity')}>
        <input
          value={value.scenario_id}
          maxLength={64}
          onChange={(event) => change({ scenario_id: event.target.value })}
        />
      </Field>
      <Field label={c('scenarioName')}>
        <input
          value={value.name}
          maxLength={100}
          onChange={(event) => change({ name: event.target.value })}
        />
      </Field>
      <Field label={c('scenarioPrompt')}>
        <textarea
          value={value.prompt}
          maxLength={4000}
          onChange={(event) => change({ prompt: event.target.value })}
        />
      </Field>
      <Field label={c('expectedLiteral')}>
        <input
          value={value.expected_text}
          maxLength={500}
          onChange={(event) => change({ expected_text: event.target.value })}
        />
      </Field>
      <Field label={c('forbiddenLiteral')}>
        <input
          value={value.forbidden_text}
          maxLength={500}
          onChange={(event) => change({ forbidden_text: event.target.value })}
        />
      </Field>
      <Field label={c('executionEnvironment')}>
        <select
          value={value.isolation}
          onChange={(event) =>
            change({ isolation: event.target.value as ScenarioDeclaration['isolation'], tools: [] })
          }
        >
          <option value="no_tools">{c('withoutTools')}</option>
          <option value="isolated_worker" disabled={!query.data?.configured}>
            {c('isolatedWorker')}
          </option>
        </select>
      </Field>
      {value.isolation === 'isolated_worker' && (
        <>
          <QueryState query={query} />
          <fieldset>
            <legend>{c('requiredNativeTools')}</legend>
            {!query.error &&
              query.data?.tools.map((name) => {
                const tool = 'aryn_native_' + name
                return (
                  <label className="intel-checkbox" key={tool}>
                    <input
                      type="checkbox"
                      checked={value.tools.includes(tool)}
                      onChange={(event) =>
                        change({
                          tools: event.target.checked
                            ? [...value.tools, tool]
                            : value.tools.filter((item) => item !== tool),
                        })
                      }
                    />
                    {name}
                  </label>
                )
              })}
          </fieldset>
          <Notice>{c('nativeSuiteHelp')}</Notice>
        </>
      )}
      <Field label={c('timeoutSeconds')}>
        <input
          type="number"
          min={1}
          max={120}
          value={value.timeout_seconds}
          onChange={(event) => change({ timeout_seconds: Number(event.target.value) })}
        />
      </Field>
      <Notice>{c('mandatoryGraders')}</Notice>
    </>
  )
}
