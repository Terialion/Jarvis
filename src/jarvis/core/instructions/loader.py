from __future__ import annotations

from pathlib import Path

from ..repo_inspection.safety import is_likely_binary, is_sensitive_path, is_within_workspace

from .defaults import BUILTIN_DEFAULT_INSTRUCTIONS
from .schema import InstructionBundle, InstructionSource

MAX_FILE_BYTES = 32768
MAX_TOTAL_BYTES = 65536


def load_project_instructions(workspace_root: Path, cwd: Path | None = None) -> InstructionBundle:
    root = workspace_root.resolve()
    current = (cwd or root).resolve()
    bundle = InstructionBundle()
    chunks: list[str] = []

    _add_builtin(bundle, chunks)

    # Safely get global JARVIS.md path, handling missing home directory
    try:
        global_path = Path.home() / ".jarvis" / "JARVIS.md"
        _try_load(bundle, chunks, global_path, "global", workspace_root=root, allow_outside=True)
    except RuntimeError:
        # Home directory cannot be determined; skip global config
        pass

    candidates: list[tuple[str, Path]] = [
        ("project", root / "JARVIS.md"),
        ("agents", root / "AGENTS.md"),
        ("claude", root / "CLAUDE.md"),
        ("override", root / ".jarvis" / "JARVIS.override.md"),
    ]
    directory_instruction = current / "JARVIS.md"
    if is_within_workspace(directory_instruction, root) and directory_instruction != root / "JARVIS.md":
        candidates.append(("directory", directory_instruction))

    for scope, path in candidates:
        _try_load(bundle, chunks, path, scope, workspace_root=root, allow_outside=False)

    bundle.combined_text = "\n\n".join(chunks)[:MAX_TOTAL_BYTES]
    return bundle


def _add_builtin(bundle: InstructionBundle, chunks: list[str]) -> None:
    text = BUILTIN_DEFAULT_INSTRUCTIONS
    bundle.sources.append(InstructionSource(scope="builtin", path="<builtin>", loaded=True, bytes=len(text.encode("utf-8"))))
    chunks.append(f"## Source: builtin\n{text}")


def _try_load(
    bundle: InstructionBundle,
    chunks: list[str],
    path: Path,
    scope: str,
    *,
    workspace_root: Path,
    allow_outside: bool,
) -> None:
    resolved = path.resolve()
    if not resolved.exists():
        return
    if not resolved.is_file():
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, skipped_reason="not_file"))
        return
    if not allow_outside and not is_within_workspace(resolved, workspace_root):
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, skipped_reason="outside_workspace"))
        return
    if is_sensitive_path(resolved):
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, skipped_reason="sensitive"))
        return
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, bytes=size, skipped_reason="too_large"))
        return
    data = resolved.read_bytes()
    if is_likely_binary(data):
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, bytes=len(data), skipped_reason="binary"))
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, bytes=len(data), skipped_reason="decode_error"))
        return
    already = sum(source.bytes for source in bundle.sources if source.loaded)
    if already + len(data) > MAX_TOTAL_BYTES:
        bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=False, bytes=len(data), skipped_reason="total_limit"))
        bundle.warnings.append("instruction total byte limit reached")
        return
    bundle.sources.append(InstructionSource(scope=scope, path=str(resolved), loaded=True, bytes=len(data)))
    chunks.append(f"## Source: {scope} ({resolved})\n{text}")
