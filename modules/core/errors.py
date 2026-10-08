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
    (re.compile(r"Basic\s+[^\s\"'<>]+", re.I), "Basic [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[REDACTED]"),
    (re.compile(r"\b(?:sk-[\w-]{8,}|AIza[\w-]{12,}|gh[pousr]_[\w]{12,})"), "[REDACTED]"),
    (re.compile(r"((?:api[_-]?key|secret|password|access[_-]?token|id[_-]?token|__Host-aryn_session|__Host-aryn_login|aryn_studio_session)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'<>]+", re.I), r"\1[REDACTED]"),
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


def protect_diagnostic_logging(credentials):
    """Process diagnostics exclude dependency tracebacks and registered credential values."""
    import logging
    registered = getattr(logging, "_aryn_protected_credentials", set())
    registered.update(value for value in credentials if value)
    logging._aryn_protected_credentials = registered
    if getattr(logging, "_aryn_record_protection", False):
        return
    factory = logging.getLogRecordFactory()

    def protected_record(*args, **kwargs):
        record = factory(*args, **kwargs)
        record.msg = sanitize(record.getMessage(), credentials=registered)
        record.args = ()
        # Traceback frames and exception repr can contain request/token bodies.
        if record.exc_info:
            record.msg += " [exception=" + record.exc_info[0].__name__ + "]"
        record.exc_info = record.exc_text = record.stack_info = None
        return record

    logging.setLogRecordFactory(protected_record)
    logging._aryn_record_protection = True


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
