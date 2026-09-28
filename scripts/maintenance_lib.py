from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


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
)
PROTECTED_PATHS = (
    Path(".env.local"),
    Path("docker-compose.yml"),
)


class MaintenanceError(RuntimeError):
    pass


def _relative_path(path: Path, project_root: Path) -> Path:
    return path.resolve().relative_to(project_root.resolve())


def _is_protected_path(relative_path: Path) -> bool:
    if relative_path in PROTECTED_PATHS:
        return True

    return any(relative_path == prefix or prefix in relative_path.parents for prefix in PROTECTED_PREFIXES)


def collect_deprecated_assets(project_root: Path) -> list[str]:
    return sorted(
        relative_path.as_posix()
        for relative_path in STATIC_DEPRECATED_ASSETS
        if (project_root / relative_path).exists()
    )


def detect_environment(
    project_root: Path,
    explicit_environment: str = "auto",
    environ: dict[str, str] | None = None,
) -> tuple[str, str]:
    environ = dict(os.environ if environ is None else environ)
    explicit_environment = explicit_environment.strip().lower()

    if explicit_environment not in {"auto", "local"}:
        raise MaintenanceError(
            f"Unsupported environment override '{explicit_environment}'. Use one of: auto or local."
        )

    explicit_env_file = environ.get("STUDIO_ENV_FILE", "").strip()
    if explicit_env_file:
        env_name = _environment_from_env_file(Path(explicit_env_file).name)
        return env_name, f"STUDIO_ENV_FILE={explicit_env_file}"

    explicit_env_name = environ.get("STUDIO_ENV", "").strip().lower()
    if explicit_env_name:
        if explicit_env_name != "local":
            raise MaintenanceError(
                f"Unsupported STUDIO_ENV='{explicit_env_name}'. Use 'local'."
            )
        return "local", f"STUDIO_ENV={explicit_env_name}"

    local_exists = (project_root / ".env.local").is_file()
    if local_exists:
        return "local", "auto-detect .env.local"

    raise MaintenanceError(
        "Unable to determine local environment. Provide .env.local or set STUDIO_ENV_FILE=.env.local."
    )


def _environment_from_env_file(file_name: str) -> str:
    normalized_name = file_name.strip().lower()
    if normalized_name in {".env.local", ".env.selected"}:
        return "local"
    raise MaintenanceError(
        f"Unsupported env contract '{file_name}'. Expected '.env.local'."
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
    local_targets = apply_local_cleanup(project_root, dry_run=dry_run)
    return {
        "environment": environment_name,
        "detected_by": detected_by,
        "dry_run": dry_run,
        "deprecated_assets": deprecated_assets,
        "removed_paths": local_targets,
        "executed_commands": [],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local maintenance runner")
    parser.add_argument("--environment", default="auto", help="auto or local")
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

    if not result["removed_paths"]:
        print("[maintenance] nothing to clean")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
