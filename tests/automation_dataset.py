"""Persisted performance fixture; no seed or clock endpoint in the product."""

import asyncio
from datetime import datetime, timezone
from database.schema import AutomationDefinitionModel
from modules.core.automations.recurrence import next_instant
from modules.core.automations.service import stamp
from packages.contracts.automation import (
    AutomationDefinition,
    AutomationInput,
    AutomationDecision,
    AutomationStateInput,
    ManualOccurrence,
)


def seed_automation_dataset(app, ctx):
    factory, scheduler = app.state.factory, app.state.automations
    from packages.contracts.model import ModelProviderType, ModelSpec

    discovery = asyncio.run(
        app.state.coordinator.runtime_adapter.discover_models(refresh=True)
    )
    assert discovery.discovery_valid
    factory.model_router.replace_catalog(
        [
            ModelSpec(
                provider=ModelProviderType.NINE_ROUTER,
                model_id=model["model_id"],
                display_name=model["display_name"],
                requires_api_key=False,
            )
            for model in discovery.models
        ]
    )
    blueprint = factory.create_blueprint(
        ctx, "Benchmark researcher", "benchmark-researcher"
    )
    version = factory.create_version(
        ctx,
        blueprint.id,
        "1.0.0",
        "Follow research safety guidelines and abstain without evidence.",
        "test/model-a",
        max_tokens=512,
    )
    evaluation = asyncio.run(factory.evaluate_version_with_bench(ctx, version.id))
    assert evaluation.passed
    factory.approve_version(
        ctx,
        version.id,
        "Isolated benchmark human review",
        expected_payload_hash=version.payload_hash,
    )
    factory.publish_version(ctx, version.id)
    assignment = factory.assign_agent(
        ctx,
        blueprint_id=blueprint.id,
        version_id=version.id,
        role_name="Benchmark researcher",
    )
    body = AutomationInput.model_validate(
        {
            "title": "Governed benchmark primary",
            "input": "Research safe scoped evidence.",
            "allow_remote_model": True,
            "target": {
                "kind": "agent",
                "id": assignment.id,
                "version_id": version.id,
                "payload_hash": version.payload_hash,
                "activation_id": assignment.current_transition_id,
            },
            "schedule": {
                "kind": "daily",
                "timezone": "Asia/Bangkok",
                "start_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    )
    definition = scheduler.save(ctx, body)
    scheduler.approve(
        ctx,
        definition["id"],
        AutomationDecision(
            expected_revision=1,
            payload_hash=definition["payload_hash"],
            reason="Review exact benchmark configuration",
        ),
    )
    scheduler.state(
        ctx, definition["id"], AutomationStateInput(expected_revision=1, enabled=True)
    )
    occurrence = asyncio.run(
        scheduler.manual(
            ctx,
            definition["id"],
            ManualOccurrence(expected_revision=1, idempotency_key="benchmark-primary"),
        )
    )
    assert occurrence["status"] == "completed"
    # Populate paused inventory in one fixture transaction. Use actual contracts,
    # signer, protected heads and audit; do not invent approvals, effects or runs.
    # Setup durability is outside measured navigation/API latency.
    scheduler.preflight_target(ctx, body.target)
    with scheduler.db.session(write=True) as session:
        scheduler.manage(session, ctx)
        for index in range(1, 200):
            item = body.model_copy(update={"title": f"Scoped paused schedule {index}"})
            _, record = scheduler.add(
                session,
                ctx,
                AutomationDefinitionModel,
                AutomationDefinition,
                "automation",
                title=item.title,
                owner_actor_id=ctx.actor.actor_id,
                revision=1,
                configuration=item.model_dump(mode="json"),
                payload_hash=scheduler.configuration_hash(
                    ctx, ctx.actor.actor_id, item
                ),
                next_run_at=stamp(next_instant(item.schedule, scheduler.clock())),
                updated_at=stamp(scheduler.clock()),
            )
            scheduler.event(
                session,
                ctx,
                record,
                "fixture.saved",
                revision=1,
                payload_hash=record["payload_hash"],
            )
