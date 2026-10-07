"""Immutable, server-owned suite registry with alias and configuration validation."""
from types import MappingProxyType
from packages.contracts.bench import BenchSuiteDefinition


class BenchSuiteRegistry:
    def __init__(self, suites):
        definitions, identifiers = {}, {}
        for candidate in suites:
            suite = BenchSuiteDefinition.model_validate(candidate.model_dump(mode="json"))
            if suite.suite_id in definitions:
                raise ValueError("Duplicate suite identity.")
            definitions[suite.suite_id] = suite.model_dump_json()
            for identifier in [suite.suite_id, *suite.aliases]:
                if not identifier or identifier in identifiers:
                    raise ValueError("Ambiguous suite identifier.")
                identifiers[identifier] = suite.suite_id
        self._definitions = MappingProxyType(definitions)
        self._identifiers = MappingProxyType(identifiers)

    def resolve(self, identifier):
        canonical = self._identifiers.get(identifier)
        return BenchSuiteDefinition.model_validate_json(self._definitions[canonical]) if canonical else None

    def identifiers(self):
        return sorted(self._identifiers)

    def suites(self):
        return [self.resolve(identifier) for identifier in self._definitions]
