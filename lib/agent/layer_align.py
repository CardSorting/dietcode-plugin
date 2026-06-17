"""Optional post-write [LAYER] tag alignment — ports codemarie RefactorHealer.alignTag."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WRITE_TOOLS = frozenset({
    "write_file",
    "patch",
    "dietcode_kernel",
    "apply_patch",
    "replace_in_file",
    "write_to_file",
})


def is_auto_align_layer_tags_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.governance_exemptions import _governance_config_section

        return bool(_governance_config_section().get("auto_align_layer_tags", False))
    except Exception:
        return False


def align_layer_tag(workspace: Path, file_path: str) -> dict[str, object]:
    """Align [LAYER: …] tag with geographic layer when misaligned."""
    from plugins.dietcode.lib.agent.joy_zoning import (
        generate_layer_comment,
        get_path_layer,
        is_layer_tag_supported,
        parse_layer_tag,
    )

    rel = (file_path or "").strip()
    if not rel:
        return {"aligned": False, "reason": "empty_path"}

    absolute = (workspace / rel).resolve() if not os.path.isabs(rel) else Path(rel).resolve()
    if not absolute.is_file():
        return {"aligned": False, "reason": "not_a_file", "path": str(absolute)}

    try:
        content = absolute.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"aligned": False, "reason": "read_failed", "error": str(exc)}

    if not is_layer_tag_supported(str(absolute), content):
        return {"aligned": False, "reason": "unsupported_file_type"}

    current = parse_layer_tag(content)
    expected = get_path_layer(str(absolute))
    if current == expected:
        return {"aligned": False, "reason": "already_aligned", "layer": expected}

    tag_label = "UTILS" if expected.upper() == "PLUMBING" else expected.upper()
    tag_regex = re.compile(r"/\*\*[\s\S]*?\[LAYER:\s*\w+\][\s\S]*?\*/", re.IGNORECASE)
    if tag_regex.search(content):
        new_content = tag_regex.sub(f"/**\n * [LAYER: {tag_label}]\n */", content, count=1)
    else:
        new_content = generate_layer_comment(str(absolute), tag_label, content) or content

    if not new_content or new_content == content:
        return {"aligned": False, "reason": "no_change", "expected_layer": expected}

    try:
        absolute.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return {"aligned": False, "reason": "write_failed", "error": str(exc)}

    logger.info("DietCode aligned [LAYER: %s] for %s", tag_label, absolute.name)
    return {
        "aligned": True,
        "path": rel,
        "layer": expected,
        "tag": tag_label,
    }


def maybe_align_after_write(*, tool_name: str = "", args: object = None, workspace: Optional[str] = None) -> None:
    if not is_auto_align_layer_tags_enabled():
        return
    if (tool_name or "").strip().lower() not in _WRITE_TOOLS:
        return
    if not isinstance(args, dict):
        return
    path = str(args.get("path") or "").strip()
    if not path:
        return
    try:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root

        root = Path(resolve_workspace_root(workspace))
    except Exception as exc:
        logger.debug("layer align skipped — workspace unresolved: %s", exc)
        return
    try:
        align_layer_tag(root, path)
    except Exception as exc:
        logger.debug("layer align skipped for %s: %s", path, exc)
