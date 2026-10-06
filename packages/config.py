"""Central server-side configuration for ARYN."""

import os
from typing import Optional
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


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

    aryn_env: str = "development"
    studio_host: str = "127.0.0.1"
    studio_port: int = 8710
    runtime_base_url: str = "http://127.0.0.1:8642"
    nine_router_base_url: str = "http://127.0.0.1:20128/v1"
    nine_router_api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    api_server_key: SecretStr = Field(default_factory=lambda: SecretStr(""))

    def model_post_init(self, context) -> None:
        host = self.studio_host.strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise ValueError(f"ARYN Studio host must be a loopback address ({host} is not allowed).")
        if not (1024 <= self.studio_port <= 65535):
            raise ValueError(f"ARYN Studio port must be between 1024 and 65535, got {self.studio_port}.")

        _validate_url(self.runtime_base_url, "ARYN_RUNTIME_BASE_URL", enforce_loopback=True)
        _validate_url(self.nine_router_base_url, "ARYN_9ROUTER_BASE_URL", require_v1=True, enforce_loopback=True)

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
        aryn_env = os.getenv("ARYN_ENV", "development")
        is_dev = aryn_env.strip().lower() == "development"

        studio_host_env = os.getenv("ARYN_STUDIO_HOST", "")
        studio_port_env = os.getenv("ARYN_STUDIO_PORT", "")
        runtime_url_env = os.getenv("ARYN_RUNTIME_BASE_URL", "")
        nine_router_url_env = os.getenv("ARYN_9ROUTER_BASE_URL", "")
        nine_router_key_env = os.getenv("ARYN_9ROUTER_API_KEY", "")
        api_server_key_env = os.getenv("API_SERVER_KEY", "")

        if not is_dev:
            if not studio_host_env:
                raise ValueError("ARYN_STUDIO_HOST is required in non-development environment")
            if not studio_port_env:
                raise ValueError("ARYN_STUDIO_PORT is required in non-development environment")
            if not runtime_url_env:
                raise ValueError("ARYN_RUNTIME_BASE_URL is required in non-development environment")
            if not nine_router_url_env:
                raise ValueError("ARYN_9ROUTER_BASE_URL is required in non-development environment")

        studio_host = studio_host_env.strip() if studio_host_env else ("127.0.0.1" if is_dev else "")
        studio_port = int(studio_port_env.strip()) if studio_port_env else (8710 if is_dev else 0)
        runtime_base_url = runtime_url_env.strip() if runtime_url_env else ("http://127.0.0.1:8642" if is_dev else "")
        nine_router_base_url = nine_router_url_env.strip() if nine_router_url_env else ("http://127.0.0.1:20128/v1" if is_dev else "")

        return cls(
            aryn_env=aryn_env,
            studio_host=studio_host,
            studio_port=studio_port,
            runtime_base_url=runtime_base_url,
            nine_router_base_url=nine_router_base_url,
            nine_router_api_key=SecretStr(nine_router_key_env),
            api_server_key=SecretStr(api_server_key_env),
        )


def get_settings() -> ARYNSettings:
    """Return an ARYNSettings instance initialized from the environment."""
    return ARYNSettings.from_env()
