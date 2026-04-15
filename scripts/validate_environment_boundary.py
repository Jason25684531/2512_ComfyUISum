from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def load_manifest(repo_root: Path) -> dict:
    manifest_path = repo_root / "environment_boundary_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def encode_value(value):
    if isinstance(value, str):
        return html.escape(value, quote=True)
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if isinstance(value, dict):
        return {key: encode_value(item) for key, item in value.items()}
    return value


def resolve_repo_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate

    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"Path escapes repo root: {raw_path}") from exc
    return resolved


def to_repo_rel(repo_root: Path, target_path: Path) -> str:
    return target_path.resolve().relative_to(repo_root).as_posix()


def matches_manifest_path(repo_relative_path: str, manifest_entry: str) -> bool:
    normalized_entry = manifest_entry.rstrip("/")
    if manifest_entry.endswith("/"):
        return repo_relative_path == normalized_entry or repo_relative_path.startswith(f"{normalized_entry}/")
    return repo_relative_path == normalized_entry


def is_excluded(repo_relative_path: str, prefixes: list[str]) -> bool:
    return any(matches_manifest_path(repo_relative_path, prefix) for prefix in prefixes)


def collect_scan_files(repo_root: Path, manifest: dict) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    for entry in manifest["path_allowlist"]:
        resolved = resolve_repo_path(repo_root, entry)
        if resolved.is_dir():
            for candidate in sorted(path for path in resolved.rglob("*") if path.is_file()):
                repo_relative = to_repo_rel(repo_root, candidate)
                if is_excluded(repo_relative, manifest.get("scan_exclude_prefixes", [])):
                    continue
                if candidate not in seen:
                    seen.add(candidate)
                    files.append(candidate)
            continue

        if resolved.is_file() and resolved not in seen:
            repo_relative = to_repo_rel(repo_root, resolved)
            if is_excluded(repo_relative, manifest.get("scan_exclude_prefixes", [])):
                continue
            seen.add(resolved)
            files.append(resolved)

    return files


def add_violation(violations: list[dict], violation_type: str, message: str,
                  file_path: str = "", matched_literal: str = "", recommendation: str = "") -> None:
    violations.append({
        "type": violation_type,
        "message": message,
        "file_path": file_path,
        "matched_literal": matched_literal,
        "recommendation": recommendation,
    })


def validate_environment_boundary(repo_root: Path, environment: str, env_file: str | None = None,
                                  required_paths: list[str] | None = None) -> dict:
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root)
    env_contract = manifest["env_contract"][environment]
    selected_env_file = env_file or env_contract["env_file"]
    canonical_assets = list(env_contract["canonical_assets"])
    requested_paths = list(required_paths or [])
    required_paths = []
    seen_required_paths: set[str] = set()

    for raw_path in canonical_assets + requested_paths:
        normalized_path = raw_path.rstrip("/")
        if normalized_path in seen_required_paths:
            continue
        seen_required_paths.add(normalized_path)
        required_paths.append(raw_path)

    violations: list[dict] = []
    checked_paths: set[str] = set()

    try:
        resolved_env_path = resolve_repo_path(repo_root, selected_env_file)
        resolved_env_file = to_repo_rel(repo_root, resolved_env_path)
        checked_paths.add(resolved_env_file)
        if Path(selected_env_file).name != Path(env_contract["env_file"]).name:
            add_violation(
                violations,
                "env-file-mismatch",
                f"Environment '{environment}' must use {env_contract['env_file']}, not {selected_env_file}.",
                resolved_env_file,
                recommendation=f"Use {env_contract['env_file']} or deployment injection for {environment}.",
            )
        if not resolved_env_path.exists():
            add_violation(
                violations,
                "env-file-missing",
                f"Missing environment contract file: {selected_env_file}",
                resolved_env_file,
                recommendation=f"Create {env_contract['example_file']} as {env_contract['env_file']} before deployment.",
            )
    except ValueError:
        add_violation(
            violations,
            "path-outside-repo",
            f"Selected env file escapes repo root: {selected_env_file}",
            selected_env_file,
            recommendation="Keep env contract files inside the repository root.",
        )

    for raw_path in required_paths:
        try:
            resolved_required_path = resolve_repo_path(repo_root, raw_path)
            repo_relative = to_repo_rel(repo_root, resolved_required_path)
            checked_paths.add(repo_relative)
            if not any(matches_manifest_path(repo_relative, asset) for asset in canonical_assets):
                add_violation(
                    violations,
                    "canonical-boundary-mismatch",
                    f"Path '{raw_path}' is not canonical for environment '{environment}'.",
                    repo_relative,
                    recommendation="Use the environment-specific canonical assets from environment_boundary_manifest.json.",
                )
            if not resolved_required_path.exists():
                add_violation(
                    violations,
                    "required-path-missing",
                    f"Required path is missing: {raw_path}",
                    repo_relative,
                    recommendation="Create the canonical asset before validating this environment.",
                )
        except ValueError:
            add_violation(
                violations,
                "path-outside-repo",
                f"Required path escapes repo root: {raw_path}",
                raw_path,
                recommendation="Only validate allowlisted paths inside the repository root.",
            )

    for candidate in collect_scan_files(repo_root, manifest):
        repo_relative = to_repo_rel(repo_root, candidate)
        checked_paths.add(repo_relative)
        content = candidate.read_text(encoding="utf-8", errors="ignore")
        for forbidden_literal in manifest.get("forbidden_literals", []):
            if forbidden_literal in content:
                add_violation(
                    violations,
                    "forbidden-literal",
                    f"Found forbidden literal '{forbidden_literal}' in governed file.",
                    repo_relative,
                    matched_literal=forbidden_literal,
                    recommendation="Replace cloud IP literals with placeholders such as TWCC_GATEWAY_HOST or TWCC_GPU_NODE_HOST.",
                )

    return {
        "environment_name": environment,
        "selected_env_file": selected_env_file,
        "violation_found": bool(violations),
        "compliant": not violations,
        "checked_paths": sorted(checked_paths),
        "violations": violations,
    }


def build_output_payload(result: dict) -> dict:
    payload = encode_value(result)
    payload["_encoding"] = {
        "environment_name": True,
        "selected_env_file": True,
        "checked_paths[*]": True,
        "violations[*].type": True,
        "violations[*].message": True,
        "violations[*].file_path": True,
        "violations[*].matched_literal": True,
        "violations[*].recommendation": True,
        "violation_found": False,
        "compliant": False,
    }
    return payload


def format_text_result(result: dict) -> str:
    lines = [
        f"environment={html.escape(result['environment_name'])}",
        f"selected_env_file={html.escape(result['selected_env_file'])}",
        f"compliant={str(result['compliant']).lower()}",
        f"checked_paths={len(result['checked_paths'])}",
    ]

    if result["violations"]:
        lines.append("violations:")
        for violation in result["violations"]:
            lines.append(
                "- {type}: {message} [{file_path}]".format(
                    type=html.escape(violation["type"]),
                    message=html.escape(violation["message"]),
                    file_path=html.escape(violation["file_path"] or "n/a"),
                )
            )

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate repository environment boundaries.")
    parser.add_argument("--environment", choices=["local", "twcc"], required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--required-path", action="append", default=[])
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = validate_environment_boundary(
        repo_root=Path(args.repo_root),
        environment=args.environment,
        env_file=args.env_file,
        required_paths=args.required_path,
    )

    if args.format == "json":
        print(json.dumps(build_output_payload(result), ensure_ascii=False, indent=2))
    else:
        print(format_text_result(result))

    return 0 if result["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())