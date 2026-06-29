from __future__ import annotations

from pathlib import Path


def resolve_root_document(frontend_dir: Path, is_authenticated: bool) -> str:
    if is_authenticated:
        dashboard_path = frontend_dir / "dashboard.html"
        if dashboard_path.exists():
            return "dashboard.html"
        return "index.html"
    return "login.html"


def resolve_legacy_redirect(path: str, is_authenticated: bool) -> str | None:
    guest_only_pages = {"login.html"}
    member_only_pages = {"dashboard.html", "profile.html"}
    legacy_pages = {"index.html"}

    if path in guest_only_pages and is_authenticated:
        return "/dashboard.html"
    if path in member_only_pages and not is_authenticated:
        return "/login.html"
    if path in legacy_pages:
        return "/dashboard.html" if is_authenticated else "/login.html"
    return None
