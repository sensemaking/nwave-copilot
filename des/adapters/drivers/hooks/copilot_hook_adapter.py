#!/usr/bin/env python3
"""GitHub Copilot CLI hook adapter with DES integration.

Bridges GitHub Copilot's hook protocol (JSON stdin/stdout) to DES application
services (PreToolUseService, SubagentStopService, PostToolUseService).

Protocol-only: no business logic here. All decisions delegated to application layer.

Commands:
  python -m des.adapters.drivers.hooks.copilot_hook_adapter pre-tool-use
  python -m des.adapters.drivers.hooks.copilot_hook_adapter subagent-stop
  python -m des.adapters.drivers.hooks.copilot_hook_adapter post-tool-use

Copilot Hook Protocol (differences from Claude Code):
  Input field changes:
    tool_name       → toolName
    tool_input      → toolArgs
    tool_result     → toolResult.textResultForLlm
  Output format changes:
    {"decision": "allow"}            → {"permissionDecision": "approve"}
    {"decision": "block", "reason"} → {"permissionDecision": "deny",
                                        "permissionDecisionReason": "..."}
  SubagentStop context:
    Claude Code: agent_transcript_path, cwd
    Copilot: DES signal file (written by preToolUse hook) provides project_id,
             step_id; cwd is not in the Copilot subagentStop payload.

Exit Codes:
  0 = allow/continue (exit 0 is the only way Copilot processes stdout JSON)
  1 = error (logged but hooks fail-open in Copilot for safety)

Notes:
  - Copilot hooks always exit 0 — non-zero exit may be treated as a hook error.
    Block decisions are communicated via JSON output, not exit code.
  - additionalContext for PostToolUse is supported in Copilot (same field name).
"""

import contextlib
import io
import json
import sys
import time
import uuid
from pathlib import Path


# Ensure DES package is importable when running as __main__
if __name__ == "__main__":
    # Installed via pip: des is a top-level package
    # Source tree: src/ must be on path
    src_root = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "src")
    if src_root not in sys.path:
        sys.path.insert(0, src_root)

from des.adapters.driven.git.git_commit_verifier import GitCommitVerifier
from des.adapters.driven.hooks.yaml_execution_log_reader import YamlExecutionLogReader
from des.adapters.driven.logging.jsonl_audit_log_writer import JsonlAuditLogWriter
from des.adapters.driven.time.system_time import SystemTimeProvider
from des.adapters.driven.validation.git_scope_checker import GitScopeChecker
from des.application.pre_tool_use_service import PreToolUseService
from des.application.subagent_stop_service import SubagentStopService
from des.application.validator import TemplateValidator
from des.domain.des_enforcement_policy import DesEnforcementPolicy
from des.domain.des_marker_parser import DesMarkerParser
from des.domain.log_integrity_validator import LogIntegrityValidator
from des.domain.marker_completeness_policy import MarkerCompletenessPolicy
from des.domain.max_turns_policy import MaxTurnsPolicy
from des.domain.session_guard_policy import SessionGuardPolicy
from des.domain.step_completion_validator import StepCompletionValidator
from des.domain.tdd_schema import get_tdd_schema
from des.ports.driven_ports.audit_log_writer import AuditEvent, AuditLogWriter
from des.ports.driver_ports.pre_tool_use_port import PreToolUseInput


# ---------------------------------------------------------------------------
# Shared infrastructure (mirrors claude_code_hook_adapter.py structure)
# ---------------------------------------------------------------------------

_SLOW_HOOK_THRESHOLD_MS = 5000.0
_STDERR_CAPTURE_MAX_CHARS = 1000

# Signal files written by preToolUse so subagentStop can recover DES context.
# Copilot's subagentStop does not provide the task prompt, so we use files.
DES_SESSION_DIR = Path(".nwave") / "des"
DES_TASK_ACTIVE_FILE = DES_SESSION_DIR / "des-task-active"


def _create_audit_writer() -> AuditLogWriter:
    from des.adapters.driven.config.des_config import DESConfig
    from des.adapters.driven.logging.null_audit_log_writer import NullAuditLogWriter

    config = DESConfig()
    if not config.audit_logging_enabled:
        return NullAuditLogWriter()
    return JsonlAuditLogWriter()


def _log_event(event_type: str, data: dict) -> None:
    """Log an audit event, swallowing failures."""
    try:
        _create_audit_writer().log_event(
            AuditEvent(
                event_type=event_type,
                timestamp=SystemTimeProvider().now_utc().isoformat(),
                data=data,
            )
        )
    except Exception:
        pass


def _read_and_parse_stdin(handler: str) -> tuple[dict | None, bool]:
    """Read JSON from stdin.

    Returns:
        (hook_input, is_empty)
        hook_input is None on parse error or empty stdin.
    """
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        _log_event(
            "HOOK_PROTOCOL_ANOMALY",
            {"handler": handler, "anomaly_type": "empty_stdin", "fallback": "allow"},
        )
        return None, True

    try:
        return json.loads(raw), False
    except json.JSONDecodeError as e:
        _log_event(
            "HOOK_PROTOCOL_ANOMALY",
            {
                "handler": handler,
                "anomaly_type": "json_parse_error",
                "detail": str(e),
                "fallback": "allow",
            },
        )
        return None, False


def _signal_file_for(project_id: str, step_id: str) -> Path:
    safe_name = f"{project_id}--{step_id}".replace("/", "_")
    return DES_SESSION_DIR / f"des-task-active-{safe_name}"


def _create_des_task_signal(step_id: str, project_id: str) -> str:
    """Create signal file so subagentStop can recover DES context without transcript."""
    task_correlation_id = str(uuid.uuid4())
    try:
        from datetime import datetime, timezone

        DES_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        signal = json.dumps(
            {
                "step_id": step_id,
                "project_id": project_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "task_correlation_id": task_correlation_id,
            }
        )
        _signal_file_for(project_id, step_id).write_text(signal)
        DES_TASK_ACTIVE_FILE.write_text(signal)  # legacy fallback
    except Exception:
        pass
    return task_correlation_id


def _read_des_task_signal(project_id: str = "", step_id: str = "") -> dict | None:
    try:
        if project_id and step_id:
            namespaced = _signal_file_for(project_id, step_id)
            if namespaced.exists():
                return json.loads(namespaced.read_text())
        if DES_TASK_ACTIVE_FILE.exists():
            return json.loads(DES_TASK_ACTIVE_FILE.read_text())
    except Exception:
        pass
    return None


def _remove_des_task_signal(project_id: str = "", step_id: str = "") -> None:
    try:
        if project_id and step_id:
            namespaced = _signal_file_for(project_id, step_id)
            if namespaced.exists():
                namespaced.unlink()
        if DES_TASK_ACTIVE_FILE.exists():
            DES_TASK_ACTIVE_FILE.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service factories (same as claude_code_hook_adapter.py)
# ---------------------------------------------------------------------------


def create_pre_tool_use_service() -> PreToolUseService:
    time_provider = SystemTimeProvider()
    audit_writer = _create_audit_writer()
    return PreToolUseService(
        max_turns_policy=MaxTurnsPolicy(),
        marker_parser=DesMarkerParser(),
        prompt_validator=TemplateValidator(),
        audit_writer=audit_writer,
        time_provider=time_provider,
        enforcement_policy=DesEnforcementPolicy(),
        completeness_policy=MarkerCompletenessPolicy(),
    )


def create_subagent_stop_service() -> SubagentStopService:
    time_provider = SystemTimeProvider()
    audit_writer = _create_audit_writer()
    schema = get_tdd_schema()
    return SubagentStopService(
        log_reader=YamlExecutionLogReader(),
        completion_validator=StepCompletionValidator(schema=schema),
        scope_checker=GitScopeChecker(),
        audit_writer=audit_writer,
        time_provider=time_provider,
        commit_verifier=GitCommitVerifier(),
        integrity_validator=LogIntegrityValidator(
            schema=schema, time_provider=time_provider
        ),
    )


# ---------------------------------------------------------------------------
# Handler: PreToolUse
# ---------------------------------------------------------------------------


def handle_pre_tool_use() -> int:
    """Validate agent tool calls before dispatch.

    Copilot preToolUse input:
      {"toolName": "agent", "toolArgs": {"prompt": "...", "max_turns": N}, ...}

    Copilot preToolUse output (deny):
      {"permissionDecision": "deny", "permissionDecisionReason": "..."}
    Copilot preToolUse output (approve):
      {"permissionDecision": "approve"}
    """
    hook_id = str(uuid.uuid4())
    start_ns = time.perf_counter_ns()
    task_correlation_id: str | None = None
    stderr_buffer = io.StringIO()
    exit_code = 0

    try:
        with contextlib.redirect_stderr(stderr_buffer):
            hook_input, is_empty = _read_and_parse_stdin("pre_tool_use")

            if is_empty or hook_input is None:
                print(json.dumps({"permissionDecision": "approve"}))
                return 0

            # Copilot protocol: toolArgs instead of tool_input
            tool_args = hook_input.get("toolArgs", {})
            prompt = tool_args.get("prompt", "")
            max_turns = tool_args.get("max_turns")

            _log_event(
                "HOOK_INVOKED",
                {
                    "handler": "pre_tool_use",
                    "hook_id": hook_id,
                    "tool_name": hook_input.get("toolName"),
                    "has_max_turns": max_turns is not None,
                },
            )

            service = create_pre_tool_use_service()
            decision = service.validate(
                PreToolUseInput(
                    prompt=prompt,
                    max_turns=max_turns,
                    subagent_type=tool_args.get("subagent_type"),
                ),
                hook_id=hook_id,
            )

            if decision.action == "allow":
                if "DES-VALIDATION" in prompt:
                    parser = DesMarkerParser()
                    markers = parser.parse(prompt)
                    task_correlation_id = _create_des_task_signal(
                        step_id=markers.step_id or "",
                        project_id=markers.project_id or "",
                    )
                print(json.dumps({"permissionDecision": "approve"}))
                return 0
            else:
                reason = decision.reason or "Validation failed"
                recovery = decision.recovery_suggestions or []
                if recovery:
                    reason += "\n\nRecovery:\n" + "\n".join(
                        f"  {i + 1}. {s}" for i, s in enumerate(recovery)
                    )
                print(
                    json.dumps(
                        {
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    )
                )
                return 0  # Copilot reads deny from JSON; always exit 0

    except Exception as e:
        stderr_capture = stderr_buffer.getvalue()[:_STDERR_CAPTURE_MAX_CHARS]
        _log_event(
            "HOOK_ERROR",
            {"handler": "pre_tool_use", "error": str(e), "stderr": stderr_capture},
        )
        # Fail-open for errors: deny would block all agent use if adapter crashes
        print(json.dumps({"permissionDecision": "approve"}))
        return 0
    finally:
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        _log_event(
            "HOOK_COMPLETED",
            {
                "handler": "pre_tool_use",
                "hook_id": hook_id,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "task_correlation_id": task_correlation_id,
                "slow_hook": duration_ms > _SLOW_HOOK_THRESHOLD_MS,
            },
        )


# ---------------------------------------------------------------------------
# Handler: SubagentStop
# ---------------------------------------------------------------------------


def handle_subagent_stop() -> int:
    """Validate TDD phase completion when a subagent finishes.

    Copilot subagentStop input (available fields — transcript_path NOT available):
      {"agentId": "...", "cwd": "...", "stopHookActive": false, ...}

    DES context (project_id, step_id) is recovered from the signal file written
    by handle_pre_tool_use() when the DES task was dispatched.

    Non-DES agents (no signal file) are allowed through silently.
    """
    hook_id = str(uuid.uuid4())
    start_ns = time.perf_counter_ns()
    exit_code = 0
    stderr_buffer = io.StringIO()

    try:
        with contextlib.redirect_stderr(stderr_buffer):
            hook_input, is_empty = _read_and_parse_stdin("subagent_stop")

            if is_empty or hook_input is None:
                print(json.dumps({"permissionDecision": "approve"}))
                return 0

            _log_event(
                "HOOK_INVOKED",
                {
                    "handler": "subagent_stop",
                    "hook_id": hook_id,
                    "agent_id": hook_input.get("agentId"),
                },
            )

            # Copilot does not provide transcript_path. Recover DES context from
            # the signal file created by preToolUse.
            signal_data = _read_des_task_signal()
            if signal_data is None:
                # No signal file: non-DES agent, allow through
                print(json.dumps({"permissionDecision": "approve"}))
                return 0

            project_id = signal_data.get("project_id", "")
            step_id = signal_data.get("step_id", "")
            task_start_time = signal_data.get("created_at", "")
            task_correlation_id = signal_data.get("task_correlation_id")

            if not project_id or not step_id:
                # Malformed signal: allow through and clean up
                _remove_des_task_signal()
                print(json.dumps({"permissionDecision": "approve"}))
                return 0

            # cwd: Copilot may or may not include this; fall back to os.getcwd()
            import os

            cwd = hook_input.get("cwd", "") or os.getcwd()
            execution_log_path = str(
                Path(cwd) / "docs" / "feature" / project_id / "execution-log.yaml"
            )

            # Clean up signal file
            _remove_des_task_signal(project_id=project_id, step_id=step_id)

            from des.ports.driver_ports.subagent_stop_port import SubagentStopContext

            stop_hook_active = bool(hook_input.get("stopHookActive", False))
            service = create_subagent_stop_service()
            decision = service.validate(
                SubagentStopContext(
                    execution_log_path=execution_log_path,
                    project_id=project_id,
                    step_id=step_id,
                    stop_hook_active=stop_hook_active,
                    cwd=cwd,
                    task_start_time=task_start_time,
                ),
                hook_id=hook_id,
            )

            if decision.action == "allow":
                print(json.dumps({"permissionDecision": "approve"}))
                return 0

            # Build block notification
            reason = decision.reason or "Validation failed"
            recovery = decision.recovery_suggestions or []
            recovery_steps = "\n".join(
                f"  {i + 1}. {s}" for i, s in enumerate(recovery)
            )
            notification = (
                f"STOP HOOK VALIDATION FAILED\n\n"
                f"Step: {project_id}/{step_id}\n"
                f"Execution Log: {execution_log_path}\n"
                f"Error: {reason}\n\n"
                f"RECOVERY REQUIRED:\n{recovery_steps}\n\n"
                f"Re-dispatch the agent to complete the missing TDD phases."
            )
            print(
                json.dumps(
                    {
                        "permissionDecision": "deny",
                        "permissionDecisionReason": notification,
                    }
                )
            )
            return 0

    except Exception as e:
        stderr_capture = stderr_buffer.getvalue()[:_STDERR_CAPTURE_MAX_CHARS]
        _log_event(
            "HOOK_ERROR",
            {"handler": "subagent_stop", "error": str(e), "stderr": stderr_capture},
        )
        # Fail-open: do not block on adapter errors
        print(json.dumps({"permissionDecision": "approve"}))
        return 0
    finally:
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        _log_event(
            "HOOK_COMPLETED",
            {
                "handler": "subagent_stop",
                "hook_id": hook_id,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "slow_hook": duration_ms > _SLOW_HOOK_THRESHOLD_MS,
            },
        )


# ---------------------------------------------------------------------------
# Handler: PostToolUse
# ---------------------------------------------------------------------------


def handle_post_tool_use() -> int:
    """Inject DES completion context into the orchestrator after an agent call.

    Copilot postToolUse input:
      {"toolName": "agent", "toolArgs": {...},
       "toolResult": {"resultType": "...", "textResultForLlm": "..."}, ...}

    Copilot postToolUse output:
      {} (no injection) or {"additionalContext": "..."} (injects text)
    """
    hook_id = str(uuid.uuid4())
    start_ns = time.perf_counter_ns()
    stderr_buffer = io.StringIO()

    try:
        with contextlib.redirect_stderr(stderr_buffer):
            hook_input, is_empty = _read_and_parse_stdin("post_tool_use")

            if is_empty or hook_input is None:
                print(json.dumps({}))
                return 0

            _log_event(
                "HOOK_INVOKED",
                {
                    "handler": "post_tool_use",
                    "hook_id": hook_id,
                    "tool_name": hook_input.get("toolName"),
                },
            )

            # Copilot protocol: toolArgs instead of tool_input
            tool_args = hook_input.get("toolArgs", {})
            prompt = tool_args.get("prompt", "")
            is_des_task = "DES-VALIDATION" in prompt

            from des.adapters.driven.logging.jsonl_audit_log_reader import (
                JsonlAuditLogReader,
            )
            from des.application.post_tool_use_service import PostToolUseService

            service = PostToolUseService(audit_reader=JsonlAuditLogReader())
            additional_context = service.check_completion_status(
                is_des_task=is_des_task,
            )

            if additional_context:
                print(json.dumps({"additionalContext": additional_context}))
            else:
                print(json.dumps({}))
            return 0

    except Exception as e:
        stderr_capture = stderr_buffer.getvalue()[:_STDERR_CAPTURE_MAX_CHARS]
        _log_event(
            "HOOK_ERROR",
            {"handler": "post_tool_use", "error": str(e), "stderr": stderr_capture},
        )
        print(json.dumps({}))
        return 0
    finally:
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        _log_event(
            "HOOK_COMPLETED",
            {
                "handler": "post_tool_use",
                "hook_id": hook_id,
                "duration_ms": duration_ms,
            },
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    "pre-tool-use": handle_pre_tool_use,
    "subagent-stop": handle_subagent_stop,
    "post-tool-use": handle_post_tool_use,
}


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m des.adapters.drivers.hooks.copilot_hook_adapter "
            "<pre-tool-use|subagent-stop|post-tool-use>",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]
    handler = _HANDLERS.get(command)
    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

    sys.exit(handler())


if __name__ == "__main__":
    main()
