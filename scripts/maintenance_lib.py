from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


INVENTORY_SKIP_PARTS = {".git", "node_modules", "venv", ".venv", "__pycache__", "mysql_data", "redis_data", "storage"}
LOCAL_SKIP_PARTS = {".git", "node_modules", "venv", ".venv", "storage", "mysql_data", "redis_data"}
LOCAL_CLEANUP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov"}
LOCAL_CLEANUP_FILE_NAMES = {".coverage"}
LOCAL_CLEANUP_SUFFIXES = {".pyc", ".pyo"}
STATIC_DEPRECATED_ASSETS = (
    Path(".env.example.backup"),
    Path("openspec/specs/project.md"),
)
PROTECTED_PREFIXES = (
    Path("ComfyUIworkflow"),
    Path("ComfyUIworkflow_api"),
    Path("storage"),
    Path("nginx"),
)
PROTECTED_PATHS = (
    Path(".env.local"),
    Path("docker-compose.yml"),
    Path("docker-compose.unified.yml"),
    Path("docs/TWCC_HFS_COS_Mount_Guide.md"),
)
SUPPORTED_STUDIO_ENVS = {"local", "twcc"}


class MaintenanceError(RuntimeError):
    pass


def _relative_path(path: Path, project_root: Path) -> Path:
    return path.resolve().relative_to(project_root.resolve())


def _has_skipped_part(path: Path, skipped_parts: set[str]) -> bool:
    return any(part in skipped_parts for part in path.parts)


def _is_protected_path(relative_path: Path) -> bool:
    if relative_path in PROTECTED_PATHS:
        return True

    return any(relative_path == prefix or prefix in relative_path.parents for prefix in PROTECTED_PREFIXES)


def _looks_like_k8s_manifest(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    return bool(re.search(r"^apiVersion:\s*\S+", content, re.MULTILINE)) and bool(
        re.search(r"^kind:\s*\S+", content, re.MULTILINE)
    )


def collect_deprecated_assets(project_root: Path) -> list[str]:
    deprecated_assets: set[str] = set()

    for relative_path in STATIC_DEPRECATED_ASSETS:
        if (project_root / relative_path).exists():
            deprecated_assets.add(relative_path.as_posix())

    for path in project_root.rglob("*"):
        relative_path = path.relative_to(project_root)
        if _has_skipped_part(relative_path, INVENTORY_SKIP_PARTS):
            continue

        try:
            is_file = path.is_file()
        except OSError:
            continue

        normalized_parts = {part.lower() for part in relative_path.parts}
        if normalized_parts.intersection({"k8s", "helm", "charts"}):
            deprecated_assets.add(relative_path.as_posix())
            continue

        if is_file and path.name == "Chart.yaml":
            deprecated_assets.add(relative_path.as_posix())
            continue

        if is_file and path.suffix.lower() in {".yaml", ".yml"} and _looks_like_k8s_manifest(path):
            deprecated_assets.add(relative_path.as_posix())

    return sorted(deprecated_assets)


def detect_environment(
    project_root: Path,
    explicit_environment: str = "auto",
    environ: dict[str, str] | None = None,
) -> tuple[str, str]:
    environ = dict(os.environ if environ is None else environ)
    explicit_environment = explicit_environment.strip().lower()

    if explicit_environment in SUPPORTED_STUDIO_ENVS:
        return explicit_environment, f"--environment={explicit_environment}"
    if explicit_environment != "auto":
        raise MaintenanceError(
            f"Unsupported environment override '{explicit_environment}'. Use one of: auto, local, twcc."
        )

    explicit_env_file = environ.get("STUDIO_ENV_FILE", "").strip()
    if explicit_env_file:
        env_name = _environment_from_env_file(Path(explicit_env_file).name)
        return env_name, f"STUDIO_ENV_FILE={explicit_env_file}"

    explicit_env_name = environ.get("STUDIO_ENV", "").strip().lower()
    if explicit_env_name:
        if explicit_env_name not in SUPPORTED_STUDIO_ENVS:
            raise MaintenanceError(
                f"Unsupported STUDIO_ENV='{explicit_env_name}'. Use 'local' or 'twcc'."
            )
        return explicit_env_name, f"STUDIO_ENV={explicit_env_name}"

    local_exists = (project_root / ".env.local").is_file()
    twcc_exists = (project_root / ".env.twcc").is_file()

    if local_exists and twcc_exists:
        raise MaintenanceError(
            "Ambiguous environment selection: both .env.local and .env.twcc exist. "
            "Set STUDIO_ENV, STUDIO_ENV_FILE, or pass --environment explicitly."
        )

    if local_exists:
        return "local", "auto-detect .env.local"

    if twcc_exists:
        if platform.system().lower() != "windows" and (project_root / "nginx").exists():
            return "twcc", "auto-detect .env.twcc"
        raise MaintenanceError(
            "Found .env.twcc but runtime does not look like a supported TWCC host. "
            "Set STUDIO_ENV or pass --environment explicitly."
        )

    raise MaintenanceError(
        "Unable to determine environment. Set STUDIO_ENV, STUDIO_ENV_FILE, or pass --environment explicitly."
    )


def _environment_from_env_file(file_name: str) -> str:
    normalized_name = file_name.strip().lower()
    if normalized_name == ".env.local":
        return "local"
    if normalized_name == ".env.twcc":
        return "twcc"
    raise MaintenanceError(
        f"Unsupported env contract '{file_name}'. Expected '.env.local' or '.env.twcc'."
    )


def collect_local_cleanup_targets(project_root: Path) -> list[str]:
    cleanup_targets: set[str] = set()

    for path in project_root.rglob("*"):
        relative_path = path.relative_to(project_root)
        if _has_skipped_part(relative_path, LOCAL_SKIP_PARTS):
            continue

        if _is_protected_path(relative_path):
            continue

        if any(parent.name in LOCAL_CLEANUP_DIR_NAMES for parent in relative_path.parents):
            continue

        if path.is_dir() and path.name in LOCAL_CLEANUP_DIR_NAMES:
            cleanup_targets.add(relative_path.as_posix())
            continue

        if path.is_file() and path.name in LOCAL_CLEANUP_FILE_NAMES:
            cleanup_targets.add(relative_path.as_posix())
            continue

        if path.is_file() and path.suffix.lower() in LOCAL_CLEANUP_SUFFIXES:
            cleanup_targets.add(relative_path.as_posix())

    return sorted(cleanup_targets)


def build_twcc_actions(project_root: Path, use_sudo: bool | None = None) -> list[list[str]]:
    frontend_path = project_root / "frontend"
    if not frontend_path.is_dir():
        raise MaintenanceError("Missing frontend/ directory; cannot apply TWCC maintenance.")

    if use_sudo is None:
        use_sudo = platform.system().lower() != "windows" and shutil.which("sudo") is not None

    permission_command = ["sudo", "chmod", "755", str(frontend_path)] if use_sudo else ["chmod", "755", str(frontend_path)]
    return [permission_command, ["docker", "image", "prune", "-f"]]


def apply_local_cleanup(project_root: Path, dry_run: bool = False) -> list[str]:
    cleanup_targets = collect_local_cleanup_targets(project_root)
    if dry_run:
        return cleanup_targets

    removed_paths: list[str] = []
    for relative_name in cleanup_targets:
        target_path = project_root / relative_name
        if target_path.is_dir():
            shutil.rmtree(target_path)
        elif target_path.exists():
            target_path.unlink()
        removed_paths.append(relative_name)

    return removed_paths


def apply_twcc_cleanup(project_root: Path, dry_run: bool = False) -> list[str]:
    commands = build_twcc_actions(project_root)
    if dry_run:
        return [" ".join(command) for command in commands]

    executed_commands: list[str] = []
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None:
            raise MaintenanceError(f"Required command not found: {command[0]}")

        completed = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise MaintenanceError(f"Command failed: {' '.join(command)} :: {stderr}")

        executed_commands.append(" ".join(command))

    return executed_commands


def run_maintenance(
    project_root: Path,
    explicit_environment: str = "auto",
    dry_run: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, object]:
    environment_name, detected_by = detect_environment(
        project_root,
        explicit_environment=explicit_environment,
        environ=environ,
    )
    deprecated_assets = collect_deprecated_assets(project_root)

    if environment_name == "local":
        local_targets = apply_local_cleanup(project_root, dry_run=dry_run)
        return {
            "environment": environment_name,
            "detected_by": detected_by,
            "dry_run": dry_run,
            "deprecated_assets": deprecated_assets,
            "removed_paths": local_targets,
            "executed_commands": [],
        }

    twcc_commands = apply_twcc_cleanup(project_root, dry_run=dry_run)
    return {
        "environment": environment_name,
        "detected_by": detected_by,
        "dry_run": dry_run,
        "deprecated_assets": deprecated_assets,
        "removed_paths": [],
        "executed_commands": twcc_commands,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Environment-aware maintenance runner")
    parser.add_argument("--environment", default="auto", help="auto, local, twcc")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing files")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    try:
        result = run_maintenance(
            project_root,
            explicit_environment=args.environment,
            dry_run=args.dry_run,
        )
    except MaintenanceError as exc:
        print(f"[maintenance] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[maintenance] environment={result['environment']} ({result['detected_by']})")
    if result["deprecated_assets"]:
        print("[maintenance] deprecated assets still present:")
        for asset in result["deprecated_assets"]:
            print(f"  - {asset}")

    if result["removed_paths"]:
        print("[maintenance] local cleanup targets:")
        for target in result["removed_paths"]:
            print(f"  - {target}")

    if result["executed_commands"]:
        print("[maintenance] twcc actions:")
        for command in result["executed_commands"]:
            print(f"  - {command}")

    if not result["removed_paths"] and not result["executed_commands"]:
        print("[maintenance] nothing to clean")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
