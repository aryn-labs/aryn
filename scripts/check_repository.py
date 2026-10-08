"""Check source-controlled CI and placeholder/security hygiene."""
from pathlib import Path
import re
import subprocess

import yaml


def check():
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    for filename in tracked:
        path = Path(filename)
        if not path.exists():  # Intentional deletion pending commit.
            continue
        if path.name == ".gitkeep":
            assert not any(item.is_file() and item.name != ".gitkeep" for item in path.parent.rglob("*")), f"Redundant placeholder: {filename}"
        assert not re.search(r"\.(db|sqlite3?|key|pem|p12|pfx)(-|$)", path.name), f"Sensitive local artifact tracked: {filename}"
        assert path.name != ".env", "A local environment must never be tracked."
    for path in Path(".github/workflows").glob("*.yml"):
        source = path.read_text(encoding="utf-8")
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
        assert workflow["permissions"] == {"contents": "read"}, "CI requires read-only repository permissions."
        assert set(workflow["on"]) <= {"push", "pull_request", "workflow_dispatch"}
        assert "secrets." not in source and "pull_request_target" not in source
        for job in workflow["jobs"].values():
            assert "permissions" not in job, "No privileged job overrides."
            for step in job["steps"]:
                if "uses" in step:
                    assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", step["uses"]), "Every action must have a full immutable SHA."
    subprocess.run(["git", "diff", "--check"], check=True)
    print("Repository configuration, pinned actions and hygiene verified.")


if __name__ == "__main__":
    check()
