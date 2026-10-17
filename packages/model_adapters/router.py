"""Model policy only. Hermes executes; 9Router owns provider routing/credentials."""

from packages.contracts.model import ModelRoutingConfig, ModelSpec


class ModelRoutingError(Exception):
    pass


class ModelRouter:
    def __init__(self, config=None, *, catalog=None):
        self.catalog = dict(catalog or {})
        self.config = config or ModelRoutingConfig(allowed_models=list(self.catalog))
        if self.config.allow_fallback or self.config.fallback_model or self.config.fallback_provider:
            raise ModelRoutingError("Silent fallback is forbidden.")

    def replace_catalog(self, specs):
        self.catalog = {s.model_id: s for s in specs}
        self.config.allowed_models = list(self.catalog)

    def resolve_model(self, requested_model=None) -> ModelSpec:
        if not requested_model or requested_model not in self.config.allowed_models:
            raise ModelRoutingError("Model is not in the allowed routing list. Silent fallback is forbidden.")
        if requested_model not in self.catalog:
            raise ModelRoutingError("Model is not present in the current gateway catalog.")
        return self.catalog[requested_model]

    def get_adapter_for_spec(self, spec):
        raise ModelRoutingError("Model invocation belongs to Hermes Runtime through 9Router.")
