"""Public errors and content scrubbing. Dependency text never enters diagnostics.

Only safe codes/IDs are logged; operational prompts/results have separate scoped
storage. Arbitrary unlabelled secrets cannot be inferred from natural language.
"""
import hashlib
import re

_KEY = re.compile(r"api.?key|secret|password|auth.?token|^auth$|^authorization$|credential|bearer|access.?token", re.I)
_CONTENT = {"prompt", "system_prompt", "system_instructions", "output", "raw_response", "raw_trace"}
_PATTERNS = [
    (re.compile(r"Bearer\s+[^\s\"'<>]+", re.I), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:sk-[\w-]{8,}|AIza[\w-]{12,}|gh[pousr]_[\w]{12,})"), "[REDACTED]"),
    (re.compile(r"((?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*)[^\s,;\"'<>]+", re.I), r"\1[REDACTED]"),
]


def sanitize(value, *, audit=False, credentials=()):
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if _KEY.search(str(key)):
                clean[key] = "[REDACTED]"
            elif audit and str(key).lower() in _CONTENT:
                raw = str(item).encode()
                clean[key + "_reference"] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            else:
                clean[key] = sanitize(item, audit=audit, credentials=credentials)
        return clean
    if isinstance(value, (list, tuple)):
        return [sanitize(item, audit=audit, credentials=credentials) for item in value]
    if isinstance(value, str):
        for credential in credentials:
            if credential:
                value = value.replace(credential, "[REDACTED]")
        for pattern, replacement in _PATTERNS:
            value = pattern.sub(replacement, value)
    return value


def public_error(exc=None, *, correlation_id=None, run_id=None):
    # A bounded allowlist; never str(exc), repr(exc), traceback or upstream body.
    codes = {"PermissionDeniedError": "permission_denied", "BudgetExceededError": "budget_exceeded",
             "ModelUnavailableError": "model_unavailable", "ModelIdentityError": "model_identity_invalid",
             "IdempotencyConflictError": "idempotency_conflict", "RunInProgressError": "run_in_progress",
             "ExecutionOwnershipError": "execution_ownership_unavailable", "TimeoutError": "execution_deadline",
             "QualityGateFailedError": "quality_gate_failed"}
    code = codes.get(type(exc).__name__, "execution_failed")
    return {"error_code": code, "message": "Operasi belum dapat diselesaikan. Periksa evidence Core dengan ID diagnosis.",
            "correlation_id": correlation_id, "run_id": run_id}
