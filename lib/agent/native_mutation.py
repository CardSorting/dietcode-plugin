# -*- coding: utf-8 -*-
"""Native mutation manager — Python port of codemarie-new NativeMutationManager."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_SEARCH_EXTENSIONS = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml",
})
_SKIP_DIRS = frozenset({".git", "node_modules", "dist", "build"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_hash(content: str) -> str:
    return hashlib.sha256(content.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return _normalized_hash(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _run_git(workspace: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def is_path_in_workspace(workspace: Path, target: Path) -> bool:
    try:
        resolved_workspace = workspace.expanduser().resolve()
        current = target.expanduser().resolve()
        while True:
            try:
                real_current = current.resolve()
                if real_current == resolved_workspace:
                    return True
                return str(real_current).startswith(str(resolved_workspace) + os.sep)
            except OSError:
                parent = current.parent
                if parent == current:
                    break
                current = parent
        return False
    except OSError:
        return False


def apply_unified_diff(content: str, diff: str) -> str:
    lines = re.split(r"\r?\n", content)
    diff_lines = re.split(r"\r?\n", diff)
    chunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        header = re.match(r"^@@\s+-(\d+),?(\d+)?\s+\+(\d+),?(\d+)?\s+@@", line)
        if header:
            if current:
                chunks.append(current)
            current = {
                "old_start": int(header.group(1)),
                "lines": [],
            }
        elif current is not None:
            if line.startswith((" ", "-", "+")) or line == "":
                current["lines"].append(line)

    if current:
        chunks.append(current)
    if not chunks:
        return content

    offset = 0
    result_lines = list(lines)
    for chunk in chunks:
        start_idx = chunk["old_start"] - 1 + offset
        expected_deleted: list[str] = []
        inserted: list[str] = []
        for dline in chunk["lines"]:
            if dline.startswith("-"):
                expected_deleted.append(dline[1:])
            elif dline.startswith("+"):
                inserted.append(dline[1:])
            elif dline.startswith(" "):
                expected_deleted.append(dline[1:])
                inserted.append(dline[1:])
            elif dline == "":
                expected_deleted.append("")
                inserted.append("")

        def check_match(idx: int) -> bool:
            if idx < 0 or idx + len(expected_deleted) > len(result_lines):
                return False
            return all(result_lines[idx + i] == expected_deleted[i] for i in range(len(expected_deleted)))

        actual_start = start_idx
        matched = check_match(start_idx)
        if not matched:
            for scan in range(1, 101):
                if check_match(start_idx - scan):
                    actual_start = start_idx - scan
                    matched = True
                    break
                if check_match(start_idx + scan):
                    actual_start = start_idx + scan
                    matched = True
                    break

        result_lines[actual_start : actual_start + len(expected_deleted)] = inserted
        offset += len(inserted) - len(expected_deleted)

    return "\n".join(result_lines)


def apply_line_search_replace(content: str, search: str, replace: str) -> str:
    if not search:
        return content
    return content.replace(search, replace, 1)


@dataclass
class CoherenceToken:
    token_id: str
    task_id: str
    workspace_revision: int
    verify_revision: int
    anchors: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    expires_at: str = ""


@dataclass
class MutationState:
    workspace_revision: int = 1
    verify_revision: int = 0
    context_refresh_id: int = 1
    tracked_file_hashes: dict[str, str] = field(default_factory=dict)
    coherence_tokens: dict[str, CoherenceToken] = field(default_factory=dict)
    anchor_git_head: str = ""
    anchor_refreshed_at: str = ""
    last_verified_command: str = ""
    last_verified_at: str = ""
    last_verify_passed: Optional[bool] = None


class NativeMutationManager:
    _instance: NativeMutationManager | None = None

    @classmethod
    def get_instance(cls) -> NativeMutationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _state_path(self, workspace: Path) -> Path:
        return workspace / ".dietcode" / "mutation-state.json"

    def read_mutation_state(self, workspace: Path) -> MutationState:
        path = self._state_path(workspace)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("workspaceRevision"):
                tokens: dict[str, CoherenceToken] = {}
                for tid, tok in (raw.get("coherenceTokens") or {}).items():
                    if isinstance(tok, dict):
                        tokens[tid] = CoherenceToken(
                            token_id=str(tok.get("tokenId", tid)),
                            task_id=str(tok.get("taskId", "")),
                            workspace_revision=int(tok.get("workspaceRevision", 1)),
                            verify_revision=int(tok.get("verifyRevision", 0)),
                            anchors=dict(tok.get("anchors") or {}),
                            created_at=str(tok.get("createdAt", "")),
                            expires_at=str(tok.get("expiresAt", "")),
                        )
                return MutationState(
                    workspace_revision=int(raw.get("workspaceRevision", 1)),
                    verify_revision=int(raw.get("verifyRevision", 0)),
                    context_refresh_id=int(raw.get("contextRefreshId", 1)),
                    tracked_file_hashes=dict(raw.get("trackedFileHashes") or {}),
                    coherence_tokens=tokens,
                    anchor_git_head=str(raw.get("anchorGitHead") or ""),
                    anchor_refreshed_at=str(raw.get("anchorRefreshedAt") or ""),
                    last_verified_command=str(raw.get("lastVerifiedCommand") or ""),
                    last_verified_at=str(raw.get("lastVerifiedAt") or ""),
                    last_verify_passed=raw.get("lastVerifyPassed"),
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return MutationState()

    def write_mutation_state(self, workspace: Path, state: MutationState) -> None:
        path = self._state_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspaceRevision": state.workspace_revision,
            "verifyRevision": state.verify_revision,
            "contextRefreshId": state.context_refresh_id,
            "trackedFileHashes": state.tracked_file_hashes,
            "coherenceTokens": {
                tid: {
                    "tokenId": tok.token_id,
                    "taskId": tok.task_id,
                    "workspaceRevision": tok.workspace_revision,
                    "verifyRevision": tok.verify_revision,
                    "anchors": tok.anchors,
                    "createdAt": tok.created_at,
                    "expiresAt": tok.expires_at,
                }
                for tid, tok in state.coherence_tokens.items()
            },
            "anchorGitHead": state.anchor_git_head,
            "anchorRefreshedAt": state.anchor_refreshed_at,
            "lastVerifiedCommand": state.last_verified_command,
            "lastVerifiedAt": state.last_verified_at,
            "lastVerifyPassed": state.last_verify_passed,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_status(self, workspace: Path, task_id: str = "") -> dict[str, Any]:
        try:
            state = self.read_mutation_state(workspace)
            git_head = _run_git(workspace, ["rev-parse", "HEAD"])
            git_branch = _run_git(workspace, ["rev-parse", "--abbrev-ref", "HEAD"])
            status_lines = [ln for ln in _run_git(workspace, ["status", "--porcelain"]).splitlines() if ln.strip()]
            dirty_files = [ln[3:].strip() for ln in status_lines if ln[3:].strip()]

            affected_files: list[dict[str, Any]] = []
            for rel_path, anchor_hash in state.tracked_file_hashes.items():
                full_path = (workspace / rel_path).resolve()
                current_hash = _file_hash(full_path)
                if anchor_hash and current_hash and anchor_hash != current_hash:
                    affected_files.append({
                        "path": rel_path,
                        "reason": "changed since agent read it",
                        "anchorHash": anchor_hash,
                        "currentHash": current_hash,
                        "source": "tracked_hash",
                    })

            if state.anchor_git_head and git_head and state.anchor_git_head != git_head:
                affected_files.append({
                    "path": "(git HEAD)",
                    "reason": "git HEAD moved since context anchor",
                    "anchorGitHead": state.anchor_git_head,
                    "currentGitHead": git_head,
                    "source": "git_head",
                })

            drift_detected = bool(affected_files)
            active_token = None
            if task_id:
                active_token = self.issue_coherence_token(workspace, task_id, [])

            return {
                "ok": True,
                "result": {
                    "mode": "workspace_status",
                    "workspaceRoot": str(workspace),
                    "workspaceRevision": state.workspace_revision,
                    "verifyRevision": state.verify_revision,
                    "contextRefreshId": state.context_refresh_id,
                    "gitHead": git_head,
                    "gitBranch": git_branch,
                    "anchorGitHead": state.anchor_git_head,
                    "anchorRefreshedAt": state.anchor_refreshed_at,
                    "dirtyFiles": dirty_files,
                    "affectedFiles": affected_files,
                    "driftDetected": drift_detected,
                    "coherenceToken": active_token,
                    "requiresContextRefresh": drift_detected,
                },
            }
        except Exception as exc:
            return {"ok": False, "error": {"string_code": "status_error", "message": str(exc)}}

    def search_literal(self, workspace: Path, query: str, max_results: int = 20) -> dict[str, Any]:
        try:
            results: list[dict[str, Any]] = []

            def walk(directory: Path) -> None:
                if len(results) >= max_results:
                    return
                try:
                    entries = list(directory.iterdir())
                except OSError:
                    return
                for entry in entries:
                    if len(results) >= max_results:
                        return
                    if entry.is_dir():
                        if entry.name not in _SKIP_DIRS:
                            walk(entry)
                    elif entry.is_file() and entry.suffix.lower() in _SEARCH_EXTENSIONS:
                        try:
                            text = entry.read_text(encoding="utf-8")
                        except OSError:
                            continue
                        if query in text:
                            for lineno, line in enumerate(text.splitlines(), 1):
                                if query in line:
                                    results.append({
                                        "path": str(entry.relative_to(workspace)),
                                        "line": lineno,
                                        "content": line.strip(),
                                    })
                                    if len(results) >= max_results:
                                        break

            walk(workspace)
            return {"ok": True, "result": {"results": results, "query": query}}
        except Exception as exc:
            return {"ok": False, "error": {"string_code": "search_error", "message": str(exc)}}

    def issue_coherence_token(
        self,
        workspace: Path,
        task_id: str,
        paths: list[str],
    ) -> dict[str, Any]:
        state = self.read_mutation_state(workspace)
        existing_id: str | None = None
        for tid, tok in state.coherence_tokens.items():
            if tok.task_id == task_id:
                existing_id = tid
                break

        now = _utc_now()
        expires_at = now + timedelta(minutes=5)

        if existing_id:
            token = state.coherence_tokens[existing_id]
            token.workspace_revision = state.workspace_revision
            token.verify_revision = state.verify_revision
            token.expires_at = expires_at.isoformat()
        else:
            seq = len(state.coherence_tokens) + 1
            token_id = f"coh_{seq}"
            token = CoherenceToken(
                token_id=token_id,
                task_id=task_id,
                workspace_revision=state.workspace_revision,
                verify_revision=state.verify_revision,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
            )
            state.coherence_tokens[token_id] = token

        if not state.anchor_git_head:
            state.anchor_git_head = _run_git(workspace, ["rev-parse", "HEAD"])
            state.anchor_refreshed_at = now.isoformat()

        paths_to_anchor = set(paths) | set(state.tracked_file_hashes)
        for rel_path in paths_to_anchor:
            if not rel_path:
                continue
            full_path = (workspace / rel_path).resolve()
            current_hash = _file_hash(full_path)
            if current_hash:
                token.anchors[rel_path] = current_hash
                state.tracked_file_hashes[rel_path] = current_hash

        self.write_mutation_state(workspace, state)
        return {
            "tokenId": token.token_id,
            "workspaceRevision": token.workspace_revision,
            "verifyRevision": token.verify_revision,
            "anchors": token.anchors,
        }

    def refresh_anchor(self, workspace: Path, paths: list[str] | None = None) -> dict[str, Any]:
        state = self.read_mutation_state(workspace)
        git_head = _run_git(workspace, ["rev-parse", "HEAD"])
        now = _utc_now().isoformat()
        state.anchor_git_head = git_head
        state.anchor_refreshed_at = now
        state.context_refresh_id += 1

        paths_to_refresh = paths if paths else list(state.tracked_file_hashes)
        for rel_path in paths_to_refresh:
            full_path = (workspace / rel_path).resolve()
            current_hash = _file_hash(full_path)
            if current_hash:
                state.tracked_file_hashes[rel_path] = current_hash
            else:
                state.tracked_file_hashes.pop(rel_path, None)

        for token in state.coherence_tokens.values():
            token.workspace_revision = state.workspace_revision
            token.verify_revision = state.verify_revision
            for rel_path in paths_to_refresh:
                full_path = (workspace / rel_path).resolve()
                current_hash = _file_hash(full_path)
                if current_hash:
                    token.anchors[rel_path] = current_hash
                else:
                    token.anchors.pop(rel_path, None)

        self.write_mutation_state(workspace, state)
        return {
            "ok": True,
            "result": {
                "contextRefreshId": state.context_refresh_id,
                "anchorGitHead": state.anchor_git_head,
                "anchorRefreshedAt": state.anchor_refreshed_at,
            },
        }

    def _validate_coherence(
        self,
        workspace: Path,
        task_id: str,
        coherence_token_id: str | None,
        expected_workspace_revision: int | None,
    ) -> dict[str, Any]:
        state = self.read_mutation_state(workspace)
        if not coherence_token_id or expected_workspace_revision is None:
            return {
                "ok": False,
                "reason": "token_required",
                "message": (
                    "Mutating RPC requires coherenceTokenId and expectedWorkspaceRevision when "
                    "taskId is set. Call dietcode_kernel(action='status') or read the files again."
                ),
                "details": {
                    "requiredAction": "refresh_context",
                    "currentWorkspaceRevision": state.workspace_revision,
                },
            }

        token = state.coherence_tokens.get(coherence_token_id)
        if not token:
            return {
                "ok": False,
                "reason": "token_unknown",
                "message": "Coherence token is missing or unknown.",
                "details": {"requiredAction": "refresh_context"},
            }

        expires = datetime.fromisoformat(token.expires_at.replace("Z", "+00:00"))
        if _utc_now() > expires:
            return {"ok": False, "reason": "token_expired", "message": "Coherence token has expired."}

        if token.task_id != task_id:
            return {"ok": False, "reason": "token_task_mismatch", "message": "Coherence token does not match taskId."}

        if expected_workspace_revision != state.workspace_revision:
            return {
                "ok": False,
                "reason": "workspace_changed",
                "message": (
                    f"Workspace revision changed. Expected {expected_workspace_revision}, "
                    f"current is {state.workspace_revision}."
                ),
                "details": {"currentWorkspaceRevision": state.workspace_revision},
            }

        if token.verify_revision != state.verify_revision:
            return {
                "ok": False,
                "reason": "verify_revision_stale",
                "message": "Verification revision changed since this task observed state.",
            }

        changed_paths: list[str] = []
        for rel_path, anchor_hash in token.anchors.items():
            full_path = (workspace / rel_path).resolve()
            current_hash = _file_hash(full_path)
            if anchor_hash and current_hash and anchor_hash != current_hash:
                changed_paths.append(rel_path)

        if changed_paths:
            return {
                "ok": False,
                "reason": "coherence_mismatch",
                "message": f"Anchored file content changed: {', '.join(changed_paths)}",
                "details": {"changedPaths": changed_paths},
            }

        return {"ok": True}

    def apply_patch(
        self,
        workspace: Path,
        file_path: str,
        *,
        unified_diff: str = "",
        line_search: str = "",
        line_replace: str = "",
        task_id: str = "",
        coherence_token_id: str | None = None,
        expected_workspace_revision: int | None = None,
    ) -> dict[str, Any]:
        full_path = (workspace / file_path).resolve()
        if not is_path_in_workspace(workspace, full_path):
            return {
                "ok": False,
                "error": {
                    "string_code": "workspace_unsafe",
                    "message": f"Target path lies outside active workspace: {file_path}",
                },
            }
        if not full_path.is_file():
            return {
                "ok": False,
                "error": {"string_code": "file_not_found", "message": f"File not found: {file_path}"},
            }

        if task_id:
            check = self._validate_coherence(
                workspace, task_id, coherence_token_id, expected_workspace_revision,
            )
            if not check.get("ok"):
                return {
                    "ok": False,
                    "error": {
                        "string_code": check.get("reason"),
                        "message": check.get("message"),
                        "details": check.get("details"),
                    },
                }

        try:
            before_content = full_path.read_text(encoding="utf-8")
            if unified_diff.strip():
                post_content = apply_unified_diff(before_content, unified_diff)
            elif line_search.strip():
                post_content = apply_line_search_replace(before_content, line_search, line_replace)
            else:
                return {
                    "ok": False,
                    "error": {
                        "string_code": "patch_invalid",
                        "message": "unified_diff or line_search/line_replace is required.",
                    },
                }

            if before_content == post_content:
                return {"ok": True, "result": {"patched": False, "reason": "No changes applied"}}

            full_path.write_text(post_content, encoding="utf-8")
            before_hash = _normalized_hash(before_content)
            post_hash = _normalized_hash(post_content)
            fingerprint_src = unified_diff or (line_search + line_replace)
            receipt = {
                "path": file_path,
                "beforeContentHash": before_hash,
                "postContentHash": post_hash,
                "patchFingerprint": hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest(),
                "readSourceBefore": before_content[:1000],
                "applyChannel": "native",
                "atomic": True,
            }

            state_before = self.read_mutation_state(workspace)
            revision_before = state_before.workspace_revision
            revision_after = revision_before + 1
            kernel_result = {
                "mutationReceipt": receipt,
                "operationId": str(uuid.uuid4()),
                "patched": True,
                "revisionBefore": revision_before,
                "revisionAfter": revision_after,
            }
            self._record_mutation_receipt(workspace, receipt, kernel_result, task_id)
            return {
                "ok": True,
                "workspace_root": str(workspace),
                "path": file_path,
                "taskId": task_id or None,
                "kernel": kernel_result,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": {"string_code": "patch_apply_error", "message": str(exc)},
            }

    def apply_verify(
        self,
        workspace: Path,
        command: str,
        cwd: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        try:
            command_cwd = (workspace / cwd).resolve() if cwd else workspace
            if not is_path_in_workspace(workspace, command_cwd):
                return {
                    "ok": False,
                    "error": {
                        "string_code": "workspace_unsafe",
                        "message": f"Working directory lies outside workspace: {cwd}",
                    },
                }

            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(command_cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            passed = proc.returncode == 0
            state = self.read_mutation_state(workspace)
            if passed:
                state.verify_revision += 1
            state.last_verified_command = command
            state.last_verified_at = _utc_now().isoformat()
            state.last_verify_passed = passed
            self.write_mutation_state(workspace, state)

            return {
                "ok": True,
                "workspace_root": str(workspace),
                "taskId": task_id or None,
                "command": command,
                "verify_ran": True,
                "passed": passed,
                "exit_code": proc.returncode,
                "stdout_summary": (proc.stdout or "")[:4000],
                "stderr_summary": (proc.stderr or "")[:4000],
            }
        except Exception as exc:
            return {"ok": False, "error": {"string_code": "verify_error", "message": str(exc)}}

    def _record_mutation_receipt(
        self,
        workspace: Path,
        receipt: dict[str, Any],
        kernel_result: dict[str, Any],
        task_id: str,
    ) -> None:
        session_receipt = {
            "timestamp": _utc_now().isoformat(),
            "taskId": task_id or None,
            "workspace": str(workspace),
            "receipt": receipt,
            "kernelResult": kernel_result,
        }
        for history_path in (
            workspace / ".dietcode" / "mutation-history.json",
            Path.home() / ".dietcode" / "session" / "mutation-receipts.json",
        ):
            try:
                history_path.parent.mkdir(parents=True, exist_ok=True)
                history: list[Any] = []
                if history_path.is_file():
                    try:
                        parsed = json.loads(history_path.read_text(encoding="utf-8"))
                        if isinstance(parsed, list):
                            history = parsed
                    except json.JSONDecodeError:
                        pass
                history.append(session_receipt)
                history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
            except OSError:
                pass

        state = self.read_mutation_state(workspace)
        state.workspace_revision += 1
        state.tracked_file_hashes[receipt["path"]] = receipt["postContentHash"]
        for token in state.coherence_tokens.values():
            token.anchors[receipt["path"]] = receipt["postContentHash"]
        self.write_mutation_state(workspace, state)


def resolve_workspace(override: str | None = None) -> tuple[Path | None, str | None]:
    """Resolve a safe project workspace for native mutation."""
    try:
        from plugins.dietcode.lib.workspace_root import resolve_workspace_root

        report = resolve_workspace_root(explicit=override)
        if report.resolved_workspace_root and report.safe_for_mutation:
            return Path(report.resolved_workspace_root), None
        errors = report.validation.errors if report.validation else []
        return None, "; ".join(errors) or "workspace not safe for mutation"
    except Exception as exc:
        return None, str(exc)
