"""Reusable isolated suite definitions for exercising Bench without live writes."""
from packages.contracts.bench import (
    BenchScenario, BenchSuiteDefinition, OutputContract, ResourceLimits, SchemaGraderSpec,
    EvidenceIntegrityGraderSpec, ModelIdentityGraderSpec, ForbiddenActionGraderSpec, LatencyCostGraderSpec,
)
from tests.studio_runtime import IsolatedTestRuntime
from packages.contracts.agent import AgentEvaluationReference, AgentOutputContract


def generic_scenario(**changes):
    values = dict(scenario_id="summary", name="Structured summary", description="Summarize a fixture as JSON.",
        category="summarization", prompt="Produce a structured summary.",
        evaluation_contract=OutputContract(format="json", strict=True, schema_definition={
            "type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}),
        resource_limits=ResourceLimits(max_latency_seconds=5, max_total_tokens=100),
        graders=[EvidenceIntegrityGraderSpec(grader_id="integrity"), ModelIdentityGraderSpec(grader_id="identity"),
                 ForbiddenActionGraderSpec(grader_id="boundaries"), SchemaGraderSpec(grader_id="schema"),
                 LatencyCostGraderSpec(grader_id="resources")])
    values.update(changes)
    return BenchScenario(**values)


def generic_suite(**changes):
    scenarios = [generic_scenario(), generic_scenario(scenario_id="extraction", name="Structured extraction", category="extraction")]
    values = dict(suite_id="structured-analysis", evaluation_version="2.1.0", aliases=["analysis"],
                  name="Structured analysis evaluation", description="JSON contracts without content regex.",
                  scenarios=scenarios, scenario_ids=[s.scenario_id for s in scenarios])
    values.update(changes)
    return BenchSuiteDefinition(**values)


def install_generic_suite(monkeypatch, suite=None):
    from modules.bench.registry import BenchSuiteRegistry
    from modules.bench import scenarios
    research = scenarios.get_bench_suite("research-safety")
    suite = suite or generic_suite()
    monkeypatch.setattr(scenarios, "BENCH_SUITE_REGISTRY", BenchSuiteRegistry([research, suite]))
    return suite


class StructuredRuntime(IsolatedTestRuntime):
    def __init__(self, output='{"summary":"Grounded fixture summary"}', observations=None):
        super().__init__()
        self.output = output
        self.observations = observations

    async def execute_direct_turn(self, request, context):
        result = await super().execute_direct_turn(request, context)
        result.output = self.output
        if self.observations is not None:
            result.execution_evidence = {"run_id": result.run_id, **self.observations}
        return result


def create_generic_version(lifecycle, monkeypatch, suite=None, runtime=None):
    db, ctx, original_runtime, factory, bp, original_version = lifecycle
    suite = install_generic_suite(monkeypatch, suite)
    runtime = runtime or StructuredRuntime()
    factory.bench_runner.runtime_adapter = runtime
    version = factory.create_version(ctx, bp.id, "2.0.0", "Produce grounded structured JSON.", "mock-fast",
        role="summarizer", evaluation_reference=AgentEvaluationReference(suite_id=suite.suite_id),
        output_contract=AgentOutputContract(format="json", schema_definition={"type": "object"}))
    return db, ctx, runtime, factory, bp, version
