"""One native Hermes tool call inside a credential-free, network-denied container.

Only the trusted Core Docker adapter starts this entry point. It is not an HTTP
service and does not accept container, volume, environment or host path options.
"""
import json
import sys


def main():
    import tools.terminal_tool  # noqa: F401 — official registry registration
    import tools.file_tools  # noqa: F401
    from tools.registry import registry
    if sys.argv[1:] == ["--metadata"]:
        from toolsets import get_all_toolsets, resolve_toolset
        print(json.dumps({"schemas": {item.name: {**item.schema, "x_hermes_toolset": item.toolset} for item in registry.get_all_entries()},
            "toolsets": {name: sorted(set(resolve_toolset(name))) for name in get_all_toolsets()}}))
        return
    body = json.loads(sys.stdin.buffer.read(65537))
    if set(body) != {"name", "arguments", "task_id"} or not isinstance(body["arguments"], dict):
        raise ValueError("Invalid native worker request.")
    entry = registry.get_entry(body["name"])
    if entry is None:
        raise ValueError("Native tool is unavailable in this worker.")
    # No model client, user profile, gateway credential, plugin loader, scheduler,
    # skill installer or delegation bootstrap is loaded by this worker.
    result = registry.dispatch(body["name"], body["arguments"], task_id=body["task_id"])
    if not isinstance(result, str) or len(result.encode()) > 16384:
        raise ValueError("Native tool result exceeded the admitted output contract.")
    try:
        observation = json.loads(result)
    except ValueError:
        observation = None
    if isinstance(observation, dict) and (observation.get("error") or observation.get("exit_code", 0) != 0):
        raise ValueError("Native tool reported an unsuccessful operation.")
    print(json.dumps({"text": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
