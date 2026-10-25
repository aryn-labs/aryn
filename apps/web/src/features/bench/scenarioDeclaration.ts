export type ScenarioDeclaration = {
  scenario_id: string
  name: string
  prompt: string
  expected_text: string
  forbidden_text: string
  tools: string[]
  isolation: 'no_tools' | 'isolated_worker'
  timeout_seconds: number
}
export const emptyScenario = (): ScenarioDeclaration => ({
  scenario_id: 'operational_observation',
  name: '',
  prompt: '',
  expected_text: '',
  forbidden_text: '',
  tools: [],
  isolation: 'no_tools',
  timeout_seconds: 30,
})
export const validScenario = (value: ScenarioDeclaration) =>
  /^[A-Za-z0-9_-]{1,64}$/.test(value.scenario_id) &&
  !!value.name.trim() &&
  !!value.prompt.trim() &&
  (!!value.expected_text || !!value.forbidden_text) &&
  Number.isInteger(value.timeout_seconds) &&
  value.timeout_seconds >= 1 &&
  value.timeout_seconds <= 120
