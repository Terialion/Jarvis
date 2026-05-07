from __future__ import annotations

from urllib.parse import urlparse


def classify_source(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    full = f"{host}{path}"

    if "github.com" in host and "/issues/" in path:
        return "github_issue"
    if "github.com" in host and "/pull/" in path:
        return "github_pr"
    if any(host.startswith(prefix) for prefix in ("docs.", "developer.", "nightlies.")):
        return "official_docs"
    if "/docs/" in path:
        return "documentation"
    if "release" in full or "changelog" in full:
        return "release_notes"
    if any(name in host for name in ("stackoverflow.com", "reddit.com", "forum", "discuss")):
        return "forum"
    if any(name in host for name in ("blog.", "medium.com", "substack.com")):
        return "blog"
    if host:
        return "documentation" if "docs" in host else "unknown"
    return "unknown"

