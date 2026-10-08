"""Install checksum-pinned scanners; never execute a remote installation script."""
import hashlib
from pathlib import Path
import platform
import tarfile
from urllib.request import urlopen
import zipfile

TOOLS = {
    "gitleaks": ("gitleaks/gitleaks", "8.30.1", {
        "Linux": ("gitleaks_8.30.1_linux_x64.tar.gz", "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
        "Windows": ("gitleaks_8.30.1_windows_x64.zip", "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"),
    }),
    "actionlint": ("rhysd/actionlint", "1.7.12", {
        "Linux": ("actionlint_1.7.12_linux_amd64.tar.gz", "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"),
        "Windows": ("actionlint_1.7.12_windows_amd64.zip", "6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9"),
    }),
}


def install():
    system = platform.system()
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Quality tools are pinned for x86_64 Linux/Windows only.")
    destination = Path(".local/quality-tools")
    destination.mkdir(parents=True, exist_ok=True)
    for name, (repository, version, releases) in TOOLS.items():
        filename, digest = releases[system]
        with urlopen(f"https://github.com/{repository}/releases/download/v{version}/{filename}", timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f"{name} archive checksum mismatch.")
        archive = destination / filename
        archive.write_bytes(data)
        executable = name + (".exe" if system == "Windows" else "")
        if system == "Windows":
            with zipfile.ZipFile(archive) as bundle:
                binary = bundle.read(executable)
        else:
            with tarfile.open(archive) as bundle:
                with bundle.extractfile(executable) as entry:
                    binary = entry.read()
        target = destination / executable
        target.write_bytes(binary)
        target.chmod(0o755)
        archive.unlink()
        print(f"Verified {name} {version}")


if __name__ == "__main__":
    install()
