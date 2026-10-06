"""Central server-side configuration for ARYN."""

import os
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEVELOPMENT_DEFAULTS = {
    "ARYN_ENV": "development",
    "ARYN_STUDIO_HOST": "127.0.0.1",
    "ARYN_STUDIO_PORT": 8710,
    "ARYN_RUNTIME_BASE_URL": "http://127.0.0.1:8642",
    "ARYN_9ROUTER_BASE_URL": "http://127.0.0.1:20128/v1",
}
ENDPOINT_FIELDS = {
    "ARYN_STUDIO_HOST": "studio_host",
    "ARYN_STUDIO_PORT": "studio_port",
    "ARYN_RUNTIME_BASE_URL": "runtime_base_url",
    "ARYN_9ROUTER_BASE_URL": "nine_router_base_url",
}


def _validate_url(
    url_str: str,
    name: str,
    *,
    require_v1: bool = False,
    enforce_loopback: bool = True,
) -> str:
    if not url_str or not isinstance(url_str, str):
        raise ValueError(f"{name} must not be empty.")
    parsed = urlsplit(url_str)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{name} must use http or https scheme, got '{parsed.scheme}'.")
    if parsed.username or parsed.password:
        raise ValueError(f"{name} must not contain credentials in URL.")
    if parsed.query:
        raise ValueError(f"{name} must not contain query parameters.")
    if parsed.fragment:
        raise ValueError(f"{name} must not contain a fragment.")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError(f"{name} must specify a valid hostname.")
    if enforce_loopback and hostname not in LOOPBACK_HOSTS:
        raise ValueError(f"{name} must bind only to loopback ({hostname} is not allowed).")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError(f"{name} port must be between 1 and 65535.")
    if require_v1:
        clean_path = parsed.path.rstrip("/")
        if clean_path != "/v1":
            raise ValueError(f"{name} must end with /v1 path.")
    return url_str.rstrip("/")


class ARYNSettings(BaseModel):
    """Immutable, centralized configuration for ARYN runtime, gateway, and studio."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    aryn_env: str = DEVELOPMENT_DEFAULTS["ARYN_ENV"]
    studio_host: str = DEVELOPMENT_DEFAULTS["ARYN_STUDIO_HOST"]
    studio_port: int = DEVELOPMENT_DEFAULTS["ARYN_STUDIO_PORT"]
    runtime_base_url: str = DEVELOPMENT_DEFAULTS["ARYN_RUNTIME_BASE_URL"]
    nine_router_base_url: str = DEVELOPMENT_DEFAULTS["ARYN_9ROUTER_BASE_URL"]
    nine_router_api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    api_server_key: SecretStr = Field(default_factory=lambda: SecretStr(""))

    @model_validator(mode="before")
    @classmethod
    def require_explicit_non_development_endpoints(cls, values):
        values = dict(values)
        env = str(values.get("aryn_env", DEVELOPMENT_DEFAULTS["ARYN_ENV"])).strip().lower()
        if not env:
            raise ValueError("ARYN_ENV must not be empty")
        values["aryn_env"] = env
        if env != "development":
            for name, field in ENDPOINT_FIELDS.items():
                if not str(values.get(field, "")).strip():
                    raise ValueError(f"{name} is required in non-development environment")
        return values

    def model_post_init(self, context) -> None:
        host = self.studio_host.strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise ValueError(f"ARYN Studio host must be a loopback address ({host} is not allowed).")
        if not (1024 <= self.studio_port <= 65535):
            raise ValueError(f"ARYN Studio port must be between 1024 and 65535, got {self.studio_port}.")

        object.__setattr__(self, "studio_host", host)
        object.__setattr__(self, "runtime_base_url", _validate_url(
            self.runtime_base_url, "ARYN_RUNTIME_BASE_URL", enforce_loopback=True))
        object.__setattr__(self, "nine_router_base_url", _validate_url(
            self.nine_router_base_url, "ARYN_9ROUTER_BASE_URL", require_v1=True, enforce_loopback=True))

    @property
    def studio_origin(self) -> str:
        return f"http://{self.studio_host}:{self.studio_port}"

    @property
    def runtime_port(self) -> int:
        parsed = urlsplit(self.runtime_base_url)
        return parsed.port or (80 if parsed.scheme == "http" else 443)

    @property
    def gateway_settings(self):
        from packages.model_adapters.gateway import GatewaySettings
        return GatewaySettings(
            base_url=self.nine_router_base_url,
            api_key=self.nine_router_api_key,
        )

    @classmethod
    def from_env(cls) -> "ARYNSettings":
        values = {"aryn_env": os.getenv("ARYN_ENV", DEVELOPMENT_DEFAULTS["ARYN_ENV"])}
        endpoints = {
            "studio_host": os.getenv("ARYN_STUDIO_HOST", "").strip(),
            "studio_port": os.getenv("ARYN_STUDIO_PORT", "").strip(),
            "runtime_base_url": os.getenv("ARYN_RUNTIME_BASE_URL", "").strip(),
            "nine_router_base_url": os.getenv("ARYN_9ROUTER_BASE_URL", "").strip(),
        }
        values.update({field: value for field, value in endpoints.items() if value})
        values["nine_router_api_key"] = SecretStr(os.getenv("ARYN_9ROUTER_API_KEY", ""))
        values["api_server_key"] = SecretStr(os.getenv("API_SERVER_KEY", ""))
        return cls(**values)


def get_settings() -> ARYNSettings:
    """Return an ARYNSettings instance initialized from the environment."""
    return ARYNSettings.from_env()


if __name__ == "__main__":
    import json
    import sys

    try:
        settings = get_settings()
    except ValueError:
        # Validation inputs can include secrets. Never serialize them to launcher logs.
        sys.exit("Konfigurasi ARYN ditolak; periksa ARYN_ENV dan endpoint wajib.")
    print(json.dumps({
        "ARYN_ENV": settings.aryn_env,
        **{name: getattr(settings, field) for name, field in ENDPOINT_FIELDS.items()},
    }))
