#!/usr/bin/env python3
"""Shared NDJSON helpers for live-server agent integration harnesses."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from dietcode_agent_client import emit_test_line, finish_test_run


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--compact", action="store_true", default=True, help="Emit compact NDJSON (default).")
    parser.add_argument("--pretty", action="store_true", help="Emit indented JSON instead of compact NDJSON.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mirror per-check detail lines to stderr in addition to stdout NDJSON.",
    )


def output_compact(args: argparse.Namespace) -> bool:
    return not args.pretty


class CheckRecorder:
    """Collect NDJSON check lines; optional stderr mirror for humans."""

    def __init__(self, *, compact: bool = True, verbose: bool = False) -> None:
        self.compact = compact
        self.verbose = verbose
        self.checks: list[dict[str, Any]] = []

    def record(self, name: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"type": "check", "name": name, "ok": ok}
        if detail is not None:
            payload["detail"] = detail
        self.checks.append(payload)
        emit_test_line(payload, compact=self.compact)
        if self.verbose and detail is not None:
            import sys

            print(f"[{name}] ok={ok} {detail}", file=sys.stderr)

    def run(self, name: str, fn: Callable[[], None]) -> bool:
        try:
            fn()
            self.record(name, True)
            return True
        except Exception as exc:
            self.record(name, False, {"error": str(exc)})
            return False

    def finish(self, suite: str) -> int:
        return finish_test_run(self.checks, suite=suite, compact=self.compact)
