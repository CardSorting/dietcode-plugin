"""Roadmap checkpoint lifecycle hooks — first-class native integration."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROADMAP_TOOLS = frozenset({"roadmap", "roadmap_checkpoint"})
_EVENT_BY_ACTION = {
    "guide": "guide",
    "checkpoint": "checkpoint_brief",
    "validate": "validated",
    "doctor": "doctor",
    "cockpit": "cockpit",
    "template": "template",
    "evidence": "evidence",
    "status": "status",
    "explain_gate": "explain_gate",
    "explain_stale": "explain_stale",
    "progress": "progress",
    "watch": "watch",
    "last_error": "last_error",
}


def _roadmap_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        return bool(get_roadmap_config().enabled)
    except Exception:
        return False


def _on_session_start(*, session_id: str = "", **_: Any) -> None:
    """Install skills, emit session event, surface roadmap brief in runtime journal."""
    if not _roadmap_enabled():
        return

    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
        from plugins.dietcode.lib.agent.roadmap.session import emit_roadmap_event, session_brief
        from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_primary_skill
    except ImportError:
        return

    cfg = get_roadmap_config()
    root = resolve_workspace_root()

    if cfg.auto_install_skills:
        try:
            result = ensure_primary_skill(root)
            if result.get("installed"):
                logger.debug("DietCode roadmap: installed skills %s", result.get("installed"))
        except Exception as exc:
            logger.debug("DietCode roadmap skill install skipped: %s", exc)

    try:
        brief = session_brief(workspace=root)
        emit_roadmap_event(
            "session_started",
            session_id=session_id,
            payload={"brief": brief, "workspace": root},
        )
    except Exception as exc:
        logger.debug("DietCode roadmap on_session_start skipped: %s", exc)


def _on_session_end(*, session_id: str = "", **_: Any) -> None:
    """Emit session-end roadmap snapshot for operator timeline."""
    if not _roadmap_enabled():
        return

    try:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
        from plugins.dietcode.lib.agent.roadmap.session import emit_roadmap_event, session_brief
    except ImportError:
        return

    try:
        root = resolve_workspace_root()
        brief = session_brief(workspace=root)
        emit_roadmap_event(
            "session_ended",
            session_id=session_id,
            payload={"brief": brief, "workspace": root},
        )
    except Exception as exc:
        logger.debug("DietCode roadmap on_session_end skipped: %s", exc)


def _post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    session_id: str = "",
    **_: Any,
) -> None:
    """Journal roadmap tool usage and ROADMAP.md write follow-ups."""
    if not _roadmap_enabled():
        return

    try:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import (
            parse_roadmap_tool_action,
            targets_roadmap_file,
        )
        from plugins.dietcode.lib.agent.roadmap.session import emit_roadmap_event
    except ImportError:
        return

    if tool_name in _ROADMAP_TOOLS:
        action = parse_roadmap_tool_action(args)
        event = _EVENT_BY_ACTION.get(action, "tool_call")
        payload: dict[str, Any] = {"action": action, "tool": tool_name}
        parsed: dict[str, Any] = {}
        success = True
        if isinstance(result, str):
            try:
                raw = json.loads(result)
                if isinstance(raw, dict):
                    parsed = raw
                    payload["phase"] = parsed.get("phase")
                    payload["valid"] = (parsed.get("validation") or {}).get("valid")
                    if parsed.get("success") is False or parsed.get("ok") is False:
                        success = False
                    elif action == "validate":
                        success = bool(payload.get("valid"))
                    elif action == "doctor":
                        success = bool(parsed.get("ok"))
                    else:
                        success = bool(parsed.get("success", parsed.get("ok", True)))
            except json.JSONDecodeError:
                success = False
        try:
            emit_roadmap_event(event, session_id=session_id, payload=payload)
            from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config
            from plugins.dietcode.lib.agent.roadmap.progress import emit_progress

            if get_roadmap_config().progress_enabled:
                emit_progress(
                    f"roadmap.{event}",
                    action=action,
                    workspace=str(parsed.get("workspace") or ""),
                    payload={
                        "phase": payload.get("phase"),
                        "valid": payload.get("valid"),
                        "stale": (parsed.get("checkpoint_freshness") or {}).get("stale"),
                    },
                    success=success,
                )
        except Exception as exc:
            logger.debug("DietCode roadmap post_tool_call event skipped: %s", exc)
        return

    if targets_roadmap_file(tool_name=tool_name, args=args):
        mutate_path = (args or {}).get("path") if isinstance(args, dict) else None
        mutate_payload = {
            "tool": tool_name,
            "path": mutate_path,
            "followup": "roadmap(action='validate')",
        }
        try:
            from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
            from plugins.dietcode.lib.agent.roadmap.workspace_state import record_file_mutation

            record_file_mutation(
                resolve_workspace_root(),
                tool=tool_name,
                path=str(mutate_path or ""),
            )
            from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot

            invalidate_snapshot(resolve_workspace_root())
            emit_roadmap_event(
                "roadmap_file_mutated",
                session_id=session_id,
                payload=mutate_payload,
            )
            from plugins.dietcode.lib.agent.roadmap.progress import emit_progress

            emit_progress("roadmap.file_mutated", payload=mutate_payload, success=True)
        except Exception as exc:
            logger.debug("DietCode roadmap write event skipped: %s", exc)


def on_roadmap_write_transform(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    """Attach validation nudge after native writes to ROADMAP.md."""
    if not _roadmap_enabled():
        return None
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config
        if not get_roadmap_config().nudge_on_roadmap_write:
            return None
        from plugins.dietcode.lib.agent.roadmap.native_bridge import (
            merge_roadmap_hint_into_result,
            roadmap_write_hint,
            targets_roadmap_file,
        )
    except ImportError:
        return None

    if not targets_roadmap_file(tool_name=tool_name, args=args):
        return None

    hint = roadmap_write_hint(tool_name=tool_name, args=args)
    try:
        return merge_roadmap_hint_into_result(result, hint)
    except Exception as exc:
        logger.debug("DietCode roadmap transform skipped: %s", exc)
        return None
