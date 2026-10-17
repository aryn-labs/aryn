"""Read installed Hermes dependencies without running its updater or repair paths."""
import importlib
from pathlib import Path
import site
import sys


def prepare_runtime_home(source, home, environment):
    source, home = Path(source).resolve(), Path(home).resolve()
    sys.path.insert(0, str(source))
    constants = importlib.import_module("hermes_constants")
    installed_home = Path(constants.get_default_hermes_root()).resolve()
    if (home.is_relative_to(installed_home) or home.is_relative_to(source)
            or installed_home.is_relative_to(home) or source.is_relative_to(home)):
        raise SystemExit("ARYN runtime home must be separate from the installed/user Hermes profile.")
    # These upstream modules are stdlib-only at import. Selection is explicitly
    # documented read-only; activate_dependencies itself takes locks, recovers
    # publication and creates leases, so it must not be called on the user install.
    dependencies = importlib.import_module("pm.environments")
    recovery = importlib.import_module("hermes_cli._early_recovery")
    launch = importlib.import_module("hermes_cli.venv_sync")
    pending = [recovery.interrupted_pull_marker(source), source / ".hermes-update-zip-swap",
        launch.completion_pending_path(source)]
    if any(path.exists() for path in pending):
        raise SystemExit("Installed Hermes needs explicit operator repair; ARYN will not modify it.")
    selected = dependencies.site_packages(dependencies.selected_venv(source))
    if not selected.is_dir() and sys.prefix == sys.base_prefix:
        raise SystemExit("Installed Hermes dependency generation is unavailable; operator repair is required.")

    def activate_read_only(_source):
        if selected.is_dir():
            site.addsitedir(str(selected))
            sys.path.insert(0, str(selected))

    # Dedicated-process hooks only. No installed file/configuration is modified.
    dependencies.activate_dependencies = activate_read_only
    recovery.restore_interrupted_pull = lambda *args, **kwargs: False
    recovery.recover_if_needed = lambda *args, **kwargs: False
    launch.prepare_launch = lambda *args, **kwargs: None
    home.mkdir(parents=True, exist_ok=True)
    environment["HERMES_HOME"] = str(home)
    environment["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    constants.set_hermes_home_override(str(home))
    constants.pin_process_hermes_home(str(home))
    configuration = home / "config.yaml"
    if not configuration.exists():
        configuration.write_text("platform_toolsets:\n  api_server: []\nmemory:\n  memory_enabled: false\ncompression:\n  enabled: false\n", encoding="utf-8")
    importlib.import_module("hermes_bootstrap")
