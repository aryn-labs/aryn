"""Bounded regular-file and raw Git-object reads from operator-owned bindings."""

import hashlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import time
from packages.contracts.evidence import EvidenceBindings
from packages.contracts.bench import evidence_hash


class EvidenceBoundaryError(LookupError):
    pass


def physical(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise EvidenceBoundaryError("Evidence paths cannot traverse links or reparse points.")
    return info


def physical_identity(path):
    info = physical(path)
    return [info.st_dev, info.st_ino]


class LocalEvidence:
    def __init__(self, manifest):
        config = EvidenceBindings.model_validate(manifest)
        self.bindings = {}
        for item in config.bindings:
            if not Path(item.root).is_absolute() or PureWindowsPath(item.root).drive.startswith("\\\\"):
                raise EvidenceBoundaryError("Evidence roots must be explicit local absolute directories; UNC paths are unsupported.")
            root = Path(item.root).absolute()
            for ancestor in [*reversed(root.parents), root]:
                physical(ancestor)
            if not root.is_dir():
                raise ValueError("Evidence root must be a physical existing directory.")
            value = item.model_dump(mode="json")
            value["root"] = str(root)
            info = physical(root)
            value["root_identity"] = [info.st_dev, info.st_ino]
            for relative in item.files.values():
                self.relative(relative)
            if item.kind == "git":
                value["git_identity"] = self.git_root(root)
            self.bindings[item.binding_id] = value

    @staticmethod
    def relative(value):
        path = PurePosixPath(value)
        if (not value or len(value) > 512 or "\\" in value or ":" in value or path.is_absolute() or ".." in path.parts
                or any(part.startswith(".") for part in path.parts)
                or path.suffix.lower() not in {".md", ".txt", ".json", ".rst", ".py", ".ts", ".tsx"}
                or re.search(r"(?i)(secret|credential|private.key|password|token)", value)):
            raise EvidenceBoundaryError("Evidence selection must be an explicitly allowed regular text file.")
        return path

    @staticmethod
    def git_root(root):
        directory = root / ".git"
        physical(directory)
        if (not directory.is_dir() or (directory / "commondir").exists()
                or (directory / "objects" / "info" / "alternates").exists()):
            raise EvidenceBoundaryError("Git evidence requires a contained object database without alternates.")
        for component in [directory / "objects", directory / "objects" / "info"]:
            if component.exists():
                physical(component)
        count = 0
        for parent, directories, files in os.walk(directory, followlinks=False):
            for name in directories + files:
                count += 1
                if count > 20000:
                    raise EvidenceBoundaryError("Git object traversal exceeds its resource limit.")
                info = physical(Path(parent) / name)
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise EvidenceBoundaryError("Git evidence objects cannot share hard links with another store.")
        config = directory / "config"
        if config.exists():
            if config.stat().st_size > 65536:
                raise EvidenceBoundaryError("Git configuration exceeds its resource limit.")
            if re.search(r"(?im)^\s*\[\s*include(?:if)?\b", config.read_text(encoding="utf-8")):
                raise EvidenceBoundaryError("Git evidence configuration cannot include external files.")
        return [physical_identity(directory), physical_identity(directory / "objects")]

    def binding(self, ctx, identifier):
        value = self.bindings.get(identifier)
        if not value or (value["organization_id"], value["project_id"]) != (ctx.organization_id, ctx.project_id):
            raise EvidenceBoundaryError("Scoped evidence binding is unavailable.")
        root = Path(value["root"])
        for ancestor in [*reversed(root.parents), root]:
            physical(ancestor)
        info = physical(root)
        if [info.st_dev, info.st_ino] != value["root_identity"]:
            raise EvidenceBoundaryError("Evidence root identity changed.")
        if value["kind"] == "git" and self.git_root(root) != value["git_identity"]:
            raise EvidenceBoundaryError("Git object database identity changed.")
        return value

    @staticmethod
    def git(root, *arguments):
        # No checkout, filters, hooks, user config, network or credential helper.
        environment = {"PATH": os.getenv("PATH", os.defpath)}
        system_root = os.getenv("SYSTEMROOT")
        if system_root:
            environment["SYSTEMROOT"] = system_root
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_COUNT="0", GIT_NO_LAZY_FETCH="1")
        deadline = time.monotonic() + 5
        process = subprocess.Popen(["git", "--no-optional-locks", "--literal-pathspecs", "-C", str(root),
            "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-c", "protocol.allow=never",
            "-c", "gc.auto=0", "-c", "maintenance.auto=false", *arguments],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment)
        try:
            with ThreadPoolExecutor(max_workers=1) as reader:
                output = reader.submit(process.stdout.read, 65537)
                try:
                    raw = output.result(timeout=max(0.01, deadline - time.monotonic()))
                except TimeoutError:
                    process.kill()
                    process.wait(timeout=1)
                    raise EvidenceBoundaryError("Local Git evidence read exceeded its deadline.") from None
                if len(raw) > 65536:
                    raise EvidenceBoundaryError("Git evidence output exceeds its resource limit.")
                if process.wait(timeout=max(0.01, deadline - time.monotonic())):
                    raise EvidenceBoundaryError("Bounded local Git evidence read failed.")
                return raw
        except subprocess.TimeoutExpired:
            raise EvidenceBoundaryError("Local Git evidence read exceeded its deadline.") from None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            process.stdout.close()

    def revision(self, ctx, binding_id):
        binding = self.binding(ctx, binding_id)
        if binding["kind"] != "git":
            raise EvidenceBoundaryError("Only Git bindings have revisions.")
        self.git_root(Path(binding["root"]))
        revision = self.git(binding["root"], "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise EvidenceBoundaryError("Git revision identity differs.")
        return revision

    def read(self, ctx, binding_id, file_key, revision=None):
        binding = self.binding(ctx, binding_id)
        relative = binding["files"].get(file_key)
        if relative is None:
            raise EvidenceBoundaryError("File selection is not in the reviewed binding.")
        path = self.relative(relative)
        if binding["kind"] == "git":
            if not re.fullmatch(r"[a-f0-9]{40}", revision or ""):
                raise EvidenceBoundaryError("An exact Git commit is required.")
            self.git_root(Path(binding["root"]))
            tree = self.git(binding["root"], "ls-tree", "-z", revision, "--", path.as_posix())
            match = re.fullmatch(rb"100644 blob ([a-f0-9]{40})\t([^\x00]+)\x00", tree)
            if not match or match[2].decode() != path.as_posix():
                raise EvidenceBoundaryError("Git evidence must be a regular non-executable file blob.")
            size = self.git(binding["root"], "cat-file", "-s", match[1].decode()).strip()
            if not size.isdigit() or int(size) > 65536:
                raise EvidenceBoundaryError("Git evidence blob exceeds its resource limit.")
            raw = self.git(binding["root"], "cat-file", "blob", match[1].decode())
            observed_revision = self.revision(ctx, binding_id)
        else:
            if revision is not None:
                raise EvidenceBoundaryError("File bindings do not accept a Git revision.")
            root = Path(binding["root"])
            target = root.joinpath(*path.parts)
            parents = [root, *[root.joinpath(*path.parts[:index]) for index in range(1, len(path.parts))]]
            parent_identity = [physical_identity(parent) for parent in parents]
            before = physical(target)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 65536:
                raise EvidenceBoundaryError("Evidence must be a bounded regular file without hard links.")
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
            with os.fdopen(descriptor, "rb") as stream:
                actual = os.fstat(stream.fileno())
                raw = stream.read(65537)
                after = os.fstat(stream.fileno())
            final = physical(target)
            final_parents = [physical_identity(parent) for parent in parents]
            identities = [(item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns) for item in (before, actual, after, final)]
            if len(set(identities)) != 1 or parent_identity != final_parents:
                raise EvidenceBoundaryError("Evidence changed while it was being read.")
            observed_revision = None
        if len(raw) > 65536 or b"\x00" in raw:
            raise EvidenceBoundaryError("Evidence is not bounded UTF-8 text.")
        self.binding(ctx, binding_id)
        origin_identity = evidence_hash({"kind": binding["kind"], "root_identity": binding["root_identity"],
            "file": path.as_posix() if binding["kind"] == "git" else os.path.normcase(path.as_posix()),
            "revision": revision})
        return {"text": raw.decode("utf-8", errors="strict"), "binding_hash": evidence_hash(binding),
            "file_key": file_key, "revision": revision, "current_revision": observed_revision,
            "origin_identity": origin_identity,
            "origin_digest": hashlib.sha256(raw).hexdigest()}
