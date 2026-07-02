from __future__ import annotations

from pathlib import Path


def resolve_root_document(frontend_dir: Path) -> str:
    dashboard_path = frontend_dir / "dashboard.html"
    if dashboard_path.exists():
        return "dashboard.html"
    return "index.html"


def resolve_legacy_redirect(path: str) -> str | None:
    legacy_pages = {"index.html", "login.html", "profile.html"}
    if path in legacy_pages:
        return "/dashboard.html"
    return None
