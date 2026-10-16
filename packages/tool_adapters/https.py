"""Single pinned HTTPS GET. Core owns approval; this boundary owns the socket.

No proxy, redirect, retry, cookie jar, decompression, connection pool or alternate
address fallback. DNS is checked again, but never used by the physical connect.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import re
import socket
import ssl
import time
import threading
from collections import deque
from urllib.parse import quote, urlsplit

from modules.core.errors import sanitize
from packages.contracts.bench import evidence_hash, strict_json_loads
from packages.contracts.tool import (HTTPSApproval, HTTPSInvocation, HTTPSResultEvidence,
    GitHubIssueConnectionDefinition, GitHubIssueResultEvidence, GITHUB_API_ORIGIN, checked_data, https_endpoint)
from packages.tool_adapters.github import GitHubResponseError


class HTTPSBoundaryError(LookupError):
    def __init__(self, stage="unverified"):
        self.stage = stage if stage in {"authorization", "destination", "connect", "tls", "network",
            "response_headers", "response_body", "response_validation"} else "unverified"
        super().__init__("Approved HTTPS read could not be verified.")


class HTTPSTrust:
    """Trusted destination configuration, never an authorization engine.

    Production has no loopback/private bypass or environment configuration switch.
    Tests use a test-owned subclass with a synthetic CA and one literal loopback.
    """
    def __init__(self, endpoints=()):
        self.endpoints = frozenset(https_endpoint(value) for value in endpoints)
        self._context = None

    @property
    def context(self):
        if self._context is None:
            self._context = ssl.create_default_context()
            self._context.minimum_version = ssl.TLSVersion.TLSv1_2
        return self._context

    @context.setter
    def context(self, value):
        self._context = value

    def identity(self):
        if (self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname
                or self.context.minimum_version < ssl.TLSVersion.TLSv1_2):
            raise HTTPSBoundaryError()
        return evidence_hash({"endpoints": sorted(self.endpoints),
            "ca": sorted(hashlib.sha256(cert).hexdigest() for cert in self.context.get_ca_certs(binary_form=True)),
            "minimum_tls": int(self.context.minimum_version), "maximum_tls": int(self.context.maximum_version),
            "verify_flags": int(self.context.verify_flags), "options": int(self.context.options),
            "common_name": self.context.hostname_checks_common_name,
            "ciphers": sorted(row["name"] for row in self.context.get_ciphers())})

    def check_address(self, address):
        if "%" in address:
            raise HTTPSBoundaryError()
        ip = ipaddress.ip_address(address)
        if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback
                or ip.is_link_local or ip.is_private or ip.is_unspecified
                or getattr(ip, "ipv4_mapped", None) or getattr(ip, "sixtofour", None)
                or getattr(ip, "teredo", None) or str(ip) == "168.63.129.16"
                or ip.version == 6 and (ip in ipaddress.ip_network("64:ff9b::/96")
                    or ip in ipaddress.ip_network("64:ff9b:1::/48") or ip in ipaddress.ip_network("::/96"))):
            raise HTTPSBoundaryError()
        return str(ip)

    def check_service_origin(self, endpoint, official_origin):
        if endpoint != official_origin:
            raise HTTPSBoundaryError()

    async def resolve(self, endpoint):
        https_endpoint(endpoint)
        if endpoint not in self.endpoints:
            raise HTTPSBoundaryError()
        url = urlsplit(endpoint)
        try:
            addresses = [str(ipaddress.ip_address(url.hostname))]
        except ValueError:
            records = await asyncio.get_running_loop().getaddrinfo(
                url.hostname, url.port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP)
            if len(records) > 16 or any(row[0] not in {socket.AF_INET, socket.AF_INET6} for row in records):
                raise HTTPSBoundaryError() from None
            addresses = [row[4][0] for row in records]
        values = tuple(sorted({self.check_address(value) for value in addresses}))
        if not 1 <= len(values) <= 8:
            raise HTTPSBoundaryError()
        return values


class HTTPSAdapter:
    def __init__(self, approval, secret, trust):
        self.approval = HTTPSApproval.model_validate_json(approval.model_dump_json())
        self._secret, self.trust = secret, trust
        self._seen, self._attempts = set(), deque()
        self._admission = threading.Lock()
        self._receipts = {}

    def connection_matches(self, identity, derive):
        return hmac.compare_digest(identity, derive(self._secret))

    def request_route(self, arguments):
        spec = self.approval.connection
        if isinstance(spec, GitHubIssueConnectionDefinition):
            from packages.tool_adapters.github import request_route
            return request_route(spec, arguments)
        checked_data(arguments, spec.declaration.input_schema)
        if not re.fullmatch(r"[a-z0-9-]{1,64}", arguments["key"]):
            raise ValueError("Approved identifier is invalid.")
        return spec.route.replace("{key}", quote(arguments["key"], safe=""))

    def consume_receipt(self, invocation, evidence):
        """Core checks its returned evidence against the actual validated exchange."""
        with self._admission:
            return self._receipts.pop(evidence_hash(invocation.model_dump(mode="json")), None) == evidence_hash(evidence)

    def _current(self, invocation, verifier, reauthorize):
        approval = self.approval
        if isinstance(approval.connection, GitHubIssueConnectionDefinition):
            self.trust.check_service_origin(approval.connection.endpoint, GITHUB_API_ORIGIN)
        if (time.time() >= min(invocation.deadline_at, approval.expires_at)
                or approval.configuration_hash() != approval.binding_hash
                or self.trust.identity() != approval.trust_hash
                or not verifier("https_connection_approval", approval.payload(), approval.attestation)
                or not verifier("https_tool_call", invocation.payload(), invocation.attestation)):
            raise HTTPSBoundaryError("authorization")
        reauthorize()
        if time.time() >= min(invocation.deadline_at, approval.expires_at):
            raise TimeoutError("Approved HTTPS deadline expired.")

    async def invoke(self, arguments, invocation, verifier, reauthorize):
        writer, sock = None, None
        stage = "authorization"
        try:
            invocation = HTTPSInvocation.model_validate_json(invocation.model_dump_json())
            arguments = strict_json_loads(json.dumps(arguments, allow_nan=False))
            approval, spec = self.approval, self.approval.connection
            route = self.request_route(arguments)
            github = isinstance(spec, GitHubIssueConnectionDefinition)
            if (invocation.organization_id != spec.organization_id or invocation.project_id != spec.project_id
                    or invocation.binding_hash != approval.binding_hash or invocation.input_hash != evidence_hash(arguments)
                    or invocation.deadline_at > approval.expires_at):
                raise HTTPSBoundaryError()
            self._current(invocation, verifier, reauthorize)
            with self._admission:
                stamp = time.monotonic()
                while self._attempts and stamp - self._attempts[0] >= 60:
                    self._attempts.popleft()
                identity = (invocation.run_id, invocation.call_id)
                if identity in self._seen or len(self._seen) >= 128 or len(self._attempts) >= spec.calls_per_minute:
                    raise HTTPSBoundaryError()
                self._seen.add(identity)
                self._attempts.append(stamp)
            started = time.perf_counter()
            seconds = min(spec.timeout_seconds, invocation.deadline_at - time.time(), approval.expires_at - time.time())
            dispatch_deadline = time.monotonic() + seconds
            def guard():
                self._current(invocation, verifier, reauthorize)
                # Synchronous Core/DB checks can consume time without yielding to
                # asyncio's timer. Never dispatch after that operation deadline.
                if time.monotonic() >= dispatch_deadline:
                    raise TimeoutError("Approved HTTPS deadline expired.")
            async with asyncio.timeout(seconds):
                stage = "destination"
                addresses = await self.trust.resolve(spec.endpoint)
                if addresses != approval.addresses:
                    raise HTTPSBoundaryError()
                # Connect to the literal approved IP; no DNS or environment proxy
                # can substitute a destination between validation and dispatch.
                address = self.trust.check_address(addresses[0])
                url = urlsplit(spec.endpoint)
                sock = socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(False)
                guard()
                stage = "connect"
                await asyncio.get_running_loop().sock_connect(sock, (address, url.port))
                peer = sock.getpeername()
                if self.trust.check_address(peer[0]) != address or peer[1] != url.port:
                    raise HTTPSBoundaryError()
                guard()
                stage = "tls"
                reader, writer = await asyncio.open_connection(sock=sock, ssl=self.trust.context,
                    server_hostname=url.hostname, limit=8192, ssl_handshake_timeout=max(.001, seconds))
                sock = None  # TLS transport now owns it, including cancellation cleanup.
                guard()
                stage = "network"
                from packages.tool_adapters.github import HEADERS
                service_headers = HEADERS if github else "Accept: application/json\r\n"
                request = (f"GET {route} HTTP/1.1\r\nHost: {url.netloc}\r\n"
                    f"{service_headers}Accept-Encoding: identity\r\nConnection: close\r\n"
                    f"Authorization: Bearer {self._secret.get_secret_value()}\r\n\r\n").encode("ascii")
                writer.write(request)
                await writer.drain()
                # A deliberately small HTTP profile. Ambiguous framing, streaming
                # and compressed responses are denied rather than decoded.
                stage = "response_headers"
                header = await reader.readuntil(b"\r\n\r\n")
                if len(header) > 8192:
                    raise HTTPSBoundaryError()
                lines = header[:-4].split(b"\r\n")
                status = re.fullmatch(rb"HTTP/1\.[01] ([1-5][0-9]{2})(?: [\x20-\x7e]{0,80})?", lines[0])
                if not status or len(lines) > 65:
                    raise HTTPSBoundaryError()
                headers = {}
                for line in lines[1:]:
                    if not re.fullmatch(rb"[A-Za-z0-9-]+: ?[\x20-\x7e]*", line):
                        raise HTTPSBoundaryError()
                    key, value = line.decode("ascii").split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise HTTPSBoundaryError()
                    headers[key] = value.strip()
                if status[1] != b"200":
                    if github:
                        raise GitHubResponseError(int(status[1]))
                    raise HTTPSBoundaryError()
                length = headers.get("content-length", "")
                if ("transfer-encoding" in headers or headers.get("content-encoding", "identity").lower() != "identity"
                        or headers.get("content-type", "").lower() not in {"application/json", "application/json; charset=utf-8"}
                        or not re.fullmatch(r"[0-9]{1,8}", length) or not 0 < int(length) <= spec.max_response_bytes):
                    raise HTTPSBoundaryError()
                stage = "response_body"
                raw = await reader.readexactly(int(length))
                if await reader.read(1):
                    # This one-shot Connection: close profile accepts no trailing
                    # body, pipelined response or understated Content-Length.
                    raise HTTPSBoundaryError()
                stage = "response_validation"
                data = strict_json_loads(raw.decode("utf-8"))
                if sanitize(data, credentials=(self._secret.get_secret_value(),)) != data:
                    raise HTTPSBoundaryError()
                if github:
                    from packages.tool_adapters.github import normalize_issue
                    data = normalize_issue(spec, arguments, data)
                else:
                    data = checked_data(data, spec.output_schema, spec.max_response_bytes)
                guard()
                contract = GitHubIssueResultEvidence if github else HTTPSResultEvidence
                evidence = contract(run_id=invocation.run_id, trace_id=invocation.trace_id,
                    call_id=invocation.call_id, organization_id=spec.organization_id, project_id=spec.project_id,
                    connection_id=spec.connection_id, tool_name=spec.declaration.name, binding_hash=approval.binding_hash,
                    schema_hash=spec.schema_hash, endpoint_hash=evidence_hash(spec.endpoint),
                    target_hash=evidence_hash({"endpoint": spec.endpoint, "addresses": addresses, "route": route}),
                    invocation_hash=evidence_hash(invocation.model_dump(mode="json")), input_hash=invocation.input_hash,
                    output_hash=evidence_hash(data), response_digest=hashlib.sha256(raw).hexdigest(),
                    http_status=200, network_requests=1, tls_verified=True, validation="schema_valid",
                    policy="approved_pinned_get", source="https_transport", result_bytes=len(raw),
                    duration_seconds=time.perf_counter() - started, timeout_seconds=seconds,
                    **({"repository_binding_hash": spec.repository_binding_hash, "issue_number": arguments["issue_number"]} if github else {}))
                result = evidence.model_dump(mode="json")
                with self._admission:
                    self._receipts[evidence.invocation_hash] = evidence_hash(result)
                return data, result
        except (TimeoutError, asyncio.CancelledError, GitHubResponseError):
            raise
        except Exception as error:
            # Never copy request, response, TLS or upstream exception text.
            if isinstance(error, HTTPSBoundaryError) and error.stage != "unverified":
                stage = error.stage
            raise HTTPSBoundaryError(stage) from None
        finally:
            if writer:
                writer.close()
            if sock:
                sock.close()
