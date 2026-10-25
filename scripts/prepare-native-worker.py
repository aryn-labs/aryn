"""Build a disposable native worker from audited tracked Hermes source, not user state."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-source", required=True, type=Path)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._:/@-]+", args.base_image):
        raise SystemExit("Invalid trusted base image reference.")
    source = args.hermes_source.resolve()
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise SystemExit("Worker build requires clean reviewed source.")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    base = json.loads(subprocess.check_output(["docker", "image", "inspect", args.base_image], text=True))[0]["Id"]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "hermes-source.tar"
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar", "--output=" + str(archive), revision], check=True)
    subprocess.run(["uv", "export", "--project", str(source), "--frozen", "--no-dev", "--no-emit-project",
        "--format", "requirements-txt", "--output-file", str(output / "requirements.txt")], check=True, stdout=subprocess.DEVNULL)
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["uv", "export", "--project", str(root), "--frozen", "--extra", "dev", "--extra", "runtime", "--no-emit-project",
        "--format", "requirements-txt", "--output-file", str(output / "security-constraints.txt")], check=True, stdout=subprocess.DEVNULL)
    shutil.copyfile(root / "services/runtime/native_worker.py", output / "native_worker.py")
    (output / "Dockerfile").write_text(f"""FROM {args.base_image}
COPY requirements.txt /native-requirements.txt
COPY security-constraints.txt /security-constraints.txt
RUN pip install --no-cache-dir --require-hashes -r /native-requirements.txt && pip install --no-cache-dir --require-hashes -r /security-constraints.txt
ADD hermes-source.tar /opt/hermes
COPY native_worker.py /opt/aryn/native_worker.py
ENV PYTHONPATH=/opt/hermes HERMES_HOME=/home/runtime TERMINAL_ENV=local TERMINAL_CWD=/workspace
WORKDIR /workspace
""", encoding="utf-8")
    (output / ".dockerignore").write_text("hermes-source/\n", encoding="utf-8")
    subprocess.run(["docker", "build", "--tag", "aryn-native-worker", str(output)], check=True)
    if json.loads(subprocess.check_output(["docker", "image", "inspect", args.base_image], text=True))[0]["Id"] != base:
        raise SystemExit("Trusted base image changed during the build.")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", "aryn-native-worker"], text=True))[0]["Id"]
    metadata = subprocess.check_output(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65532:65532", "--tmpfs", "/tmp:rw,size=32m",
        "--tmpfs", "/home/runtime:rw,size=16m,uid=65532,gid=65532", image, "python", "/opt/aryn/native_worker.py", "--metadata"], text=True)
    manifest = {"image_id": image, "source_revision": revision, **json.loads(metadata)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"image_id": image, "source_revision": revision, "tools": list(manifest["schemas"])}))


if __name__ == "__main__":
    main()
