from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REQUIRED_TOPOLOGIES = (
    "local-dev",
    "twcc-base-vm",
    "twcc-gpu-vm",
)


@dataclass(frozen=True)
class CanonicalEntry:
    path: str
    kind: str
    profiles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProxyContract:
    nginx_config: str
    upstream: str
    required_headers: tuple[str, ...]
    trusted_proxy_hops: int
    websocket_required: bool
    long_poll_timeout_seconds: int


@dataclass(frozen=True)
class TopologyDefinition:
    name: str
    canonical_entry: CanonicalEntry
    env_file: str
    services: tuple[str, ...]
    external_dependencies: tuple[str, ...]
    compatibility_entries: tuple[str, ...]
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...]
    unsupported_assumptions: tuple[str, ...]
    preflight_checks: tuple[str, ...]
    postdeploy_checks: tuple[str, ...]
    deploy_steps: tuple[str, ...]
    rollback_steps: tuple[str, ...]
    proxy_contract: ProxyContract | None = None


@dataclass(frozen=True)
class DeploymentMatrix:
    topologies: dict[str, TopologyDefinition]
    legacy_entries: tuple[dict[str, str], ...] = field(default_factory=tuple)
    common_optional_env: tuple[str, ...] = ()


def encode_value(value: Any) -> Any:
    if isinstance(value, str):
        return html.escape(value, quote=True)
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if isinstance(value, dict):
        return {key: encode_value(item) for key, item in value.items()}
    return value


def load_matrix(repo_root: Path) -> DeploymentMatrix:
    matrix_path = repo_root / "deployment_matrix.yaml"
    data = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    raw_topologies = data.get("topologies", {})
    topologies: dict[str, TopologyDefinition] = {}

    for name, raw in raw_topologies.items():
        raw_entry = raw.get("canonical_entry", {})
        canonical_entry = CanonicalEntry(
            path=str(raw_entry.get("path", "")),
            kind=str(raw_entry.get("kind", "")),
            profiles=tuple(raw_entry.get("profiles", []) or ()),
        )

        raw_proxy = raw.get("proxy_contract")
        proxy_contract = None
        if raw_proxy:
            proxy_contract = ProxyContract(
                nginx_config=str(raw_proxy.get("nginx_config", "")),
                upstream=str(raw_proxy.get("upstream", "")),
                required_headers=tuple(raw_proxy.get("required_headers", []) or ()),
                trusted_proxy_hops=int(raw_proxy.get("trusted_proxy_hops", 0) or 0),
                websocket_required=bool(raw_proxy.get("websocket_required", False)),
                long_poll_timeout_seconds=int(raw_proxy.get("long_poll_timeout_seconds", 0) or 0),
            )

        topologies[name] = TopologyDefinition(
            name=name,
            canonical_entry=canonical_entry,
            env_file=str(raw.get("env_file", "")),
            services=tuple(raw.get("services", []) or ()),
            external_dependencies=tuple(raw.get("external_dependencies", []) or ()),
            compatibility_entries=tuple(raw.get("compatibility_entries", []) or ()),
            required_env=tuple(raw.get("required_env", []) or ()),
            optional_env=tuple(raw.get("optional_env", []) or ()),
            unsupported_assumptions=tuple(raw.get("unsupported_assumptions", []) or ()),
            preflight_checks=tuple(raw.get("preflight_checks", []) or ()),
            postdeploy_checks=tuple(raw.get("postdeploy_checks", []) or ()),
            deploy_steps=tuple(raw.get("deploy_steps", []) or ()),
            rollback_steps=tuple(raw.get("rollback_steps", []) or ()),
            proxy_contract=proxy_contract,
        )

    return DeploymentMatrix(
        topologies=topologies,
        legacy_entries=tuple(data.get("legacy_entries", []) or ()),
        common_optional_env=tuple(data.get("common_optional_env", []) or ()),
    )


def add_violation(
    violations: list[dict[str, Any]],
    violation_type: str,
    message: str,
    **extra: Any,
) -> None:
    payload = {"type": violation_type, "message": message}
    payload.update(extra)
    violations.append(payload)


def load_compose_services(compose_path: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    services = data.get("services", {}) or {}
    profiles: set[str] = set()
    for config in services.values():
        for profile in config.get("profiles", []) or ():
            profiles.add(str(profile))
    return services, profiles


def parse_env_keys(env_path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def validate_deployment_matrix(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    violations: list[dict[str, Any]] = []

    matrix_path = repo_root / "deployment_matrix.yaml"
    if not matrix_path.is_file():
        add_violation(
            violations,
            "matrix-missing",
            "deployment_matrix.yaml is required.",
            file_path="deployment_matrix.yaml",
        )
        return {
            "compliant": False,
            "checked_paths": ["deployment_matrix.yaml"],
            "violations": violations,
        }

    try:
        matrix = load_matrix(repo_root)
    except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
        add_violation(
            violations,
            "matrix-invalid",
            f"deployment_matrix.yaml could not be parsed ({type(exc).__name__}).",
            file_path="deployment_matrix.yaml",
        )
        return {
            "compliant": False,
            "checked_paths": ["deployment_matrix.yaml"],
            "violations": violations,
        }

    checked_paths = {"deployment_matrix.yaml"}

    for topology_name in REQUIRED_TOPOLOGIES:
        if topology_name not in matrix.topologies:
            add_violation(
                violations,
                "missing-topology",
                f"Missing required topology: {topology_name}.",
                topology=topology_name,
            )

    for topology in matrix.topologies.values():
        checked_paths.add(topology.canonical_entry.path)
        entry_path = repo_root / topology.canonical_entry.path
        if not entry_path.exists():
            add_violation(
                violations,
                "missing-entrypoint",
                f"Canonical entrypoint does not exist for {topology.name}.",
                topology=topology.name,
                file_path=topology.canonical_entry.path,
            )
            continue

        if topology.canonical_entry.kind == "compose":
            services, available_profiles = load_compose_services(entry_path)
            missing_services = sorted(service for service in topology.services if service not in services)
            for service_name in missing_services:
                add_violation(
                    violations,
                    "missing-service",
                    f"Canonical compose for {topology.name} is missing service '{service_name}'.",
                    topology=topology.name,
                    service=service_name,
                    file_path=topology.canonical_entry.path,
                )

            for profile in topology.canonical_entry.profiles:
                if profile not in available_profiles:
                    add_violation(
                        violations,
                        "missing-profile",
                        f"Canonical compose for {topology.name} is missing profile '{profile}'.",
                        topology=topology.name,
                        profile=profile,
                        file_path=topology.canonical_entry.path,
                    )

        env_candidates = [
            repo_root / f"{topology.env_file}.example",
            repo_root / topology.env_file,
        ]
        env_contract_path = next((candidate for candidate in env_candidates if candidate.is_file()), None)
        if env_contract_path is None:
            add_violation(
                violations,
                "env-contract-missing",
                f"Missing env contract for {topology.name}.",
                topology=topology.name,
                file_path=topology.env_file,
            )
        else:
            checked_paths.add(env_contract_path.relative_to(repo_root).as_posix())
            env_keys = parse_env_keys(env_contract_path)
            missing_env_keys = sorted(key for key in topology.required_env if key not in env_keys)
            for env_key in missing_env_keys:
                add_violation(
                    violations,
                    "env-key-missing",
                    f"Env contract for {topology.name} is missing '{env_key}'.",
                    topology=topology.name,
                    file_path=env_contract_path.relative_to(repo_root).as_posix(),
                    env_key=env_key,
                )

        if topology.proxy_contract:
            checked_paths.add(topology.proxy_contract.nginx_config)
            nginx_path = repo_root / topology.proxy_contract.nginx_config
            if not nginx_path.is_file():
                add_violation(
                    violations,
                    "missing-proxy-config",
                    f"Missing nginx proxy config for {topology.name}.",
                    topology=topology.name,
                    file_path=topology.proxy_contract.nginx_config,
                )
            else:
                nginx_content = nginx_path.read_text(encoding="utf-8")
                if topology.proxy_contract.upstream not in nginx_content:
                    add_violation(
                        violations,
                        "proxy-upstream-missing",
                        f"Nginx config is missing upstream '{topology.proxy_contract.upstream}'.",
                        topology=topology.name,
                        upstream=topology.proxy_contract.upstream,
                        file_path=topology.proxy_contract.nginx_config,
                    )
                for header in topology.proxy_contract.required_headers:
                    if f"proxy_set_header {header}" not in nginx_content:
                        add_violation(
                            violations,
                            "proxy-header-missing",
                            f"Nginx config is missing required proxy header '{header}'.",
                            topology=topology.name,
                            header=header,
                            file_path=topology.proxy_contract.nginx_config,
                        )
                if topology.proxy_contract.websocket_required and "Upgrade $http_upgrade" not in nginx_content:
                    add_violation(
                        violations,
                        "proxy-websocket-missing",
                        "Nginx config must support WebSocket upgrade headers.",
                        topology=topology.name,
                        file_path=topology.proxy_contract.nginx_config,
                    )

    # --- Env example drift: keys present in an example file but undeclared anywhere ---
    # Allowed keys per env file = union of required_env/optional_env across all topologies
    # sharing that file, plus the matrix-level common_optional_env. Only matrix-named
    # files are opened (no path is built from an environment-variable value).
    env_file_allowed: dict[str, set[str]] = defaultdict(set)
    for topology in matrix.topologies.values():
        env_file_allowed[topology.env_file] |= set(topology.required_env) | set(topology.optional_env)
    common_keys = set(matrix.common_optional_env)

    seen_env_files: set[str] = set()
    for topology in matrix.topologies.values():
        env_file = topology.env_file
        if not env_file or env_file in seen_env_files:
            continue
        seen_env_files.add(env_file)
        example_path = repo_root / f"{env_file}.example"
        if not example_path.is_file():
            continue
        rel_example = example_path.relative_to(repo_root).as_posix()
        checked_paths.add(rel_example)
        allowed_keys = env_file_allowed[env_file] | common_keys
        for extra_key in sorted(parse_env_keys(example_path) - allowed_keys):
            add_violation(
                violations,
                "env-key-undeclared",
                f"Env example {rel_example} declares undeclared key '{extra_key}'.",
                file_path=rel_example,
                env_key=extra_key,
            )

    # --- Compose-file role consistency vs the matrix ---
    legacy_roles: dict[str, set[str]] = defaultdict(set)
    for entry in matrix.legacy_entries:
        legacy_path = str(entry.get("path", "")).strip()
        if not legacy_path:
            continue
        legacy_roles[legacy_path].add(str(entry.get("role", "")).strip())
        checked_paths.add(legacy_path)
        if not (repo_root / legacy_path).exists():
            add_violation(
                violations,
                "missing-legacy-entry",
                f"Matrix references entry path that does not exist: {legacy_path}.",
                file_path=legacy_path,
            )

    canonical_paths = {topology.canonical_entry.path for topology in matrix.topologies.values()}
    for canonical_path in sorted(canonical_paths):
        roles = legacy_roles.get(canonical_path)
        if roles and roles == {"compatibility"}:
            add_violation(
                violations,
                "compose-role-conflict",
                f"Compose '{canonical_path}' is a canonical entry but is classified only as 'compatibility'.",
                file_path=canonical_path,
            )

    script_path = repo_root / "scripts" / "start_unified_linux.sh"
    if script_path.is_file():
        checked_paths.add("scripts/start_unified_linux.sh")
        script_content = script_path.read_text(encoding="utf-8")
        if "infra-only profile" in script_content:
            add_violation(
                violations,
                "script-profile-drift",
                "Linux launcher must describe infra-only as a mode, not a profile.",
                file_path="scripts/start_unified_linux.sh",
            )

    return {
        "compliant": not violations,
        "checked_paths": sorted(checked_paths),
        "violations": violations,
    }


def build_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = encode_value(result)
    payload["_encoding"] = {
        "checked_paths[*]": True,
        "violations[*].type": True,
        "violations[*].message": True,
        "violations[*].topology": True,
        "violations[*].file_path": True,
        "violations[*].service": True,
        "violations[*].profile": True,
        "violations[*].header": True,
        "violations[*].upstream": True,
        "violations[*].env_key": True,
        "compliant": False,
    }
    return payload


def format_text_result(result: dict[str, Any]) -> str:
    lines = [
        f"compliant={str(result['compliant']).lower()}",
        f"checked_paths={len(result['checked_paths'])}",
    ]
    if result["violations"]:
        lines.append("violations:")
        for violation in result["violations"]:
            lines.append(
                "- {type}: {message} [{file_path}]".format(
                    type=html.escape(str(violation.get("type", ""))),
                    message=html.escape(str(violation.get("message", ""))),
                    file_path=html.escape(str(violation.get("file_path", "n/a"))),
                )
            )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate deployment matrix and topology contracts.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = validate_deployment_matrix(Path(args.repo_root))
    if args.format == "json":
        print(json.dumps(build_output_payload(result), ensure_ascii=False, indent=2))
    else:
        print(format_text_result(result))
    return 0 if result["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
