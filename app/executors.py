from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from app.models import CalcStep


class ExecutorError(Exception):
    def __init__(self, message: str, error_code: str = "execution_failed") -> None:
        super().__init__(message)
        self.error_code = error_code


class BaseExecutor:
    language: str

    def execute(self, step: CalcStep, context: dict) -> dict:
        raise NotImplementedError


class PythonExecutor(BaseExecutor):
    language = "python"

    def execute(self, step: CalcStep, context: dict) -> dict:
        started_at = time.perf_counter()
        script = self._resolve_script(step)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fp:
            fp.write(script)
            script_path = fp.name

        try:
            process = subprocess.run(
                ["python3", script_path],
                input=json.dumps(context),
                text=True,
                capture_output=True,
                timeout=step.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutorError(f"Python executor timeout after {step.timeout_seconds}s", "timeout") from exc
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if process.returncode != 0:
            raise ExecutorError(process.stderr.strip() or "Python executor failed", "runtime_error")
        payload = self._parse_stdout(process.stdout)
        payload.setdefault("status", "success")
        payload.setdefault("logs", [line for line in process.stderr.splitlines() if line])
        payload.setdefault("metrics", {})
        payload["metrics"]["duration_ms"] = duration_ms
        return payload

    def _resolve_script(self, step: CalcStep) -> str:
        if step.artifact_path:
            target = Path(step.artifact_path)
            if not target.exists():
                raise ExecutorError("Python artifact_path not found", "artifact_missing")
            return target.read_text(encoding="utf-8")
        return step.script_content or self._build_stub_script(step)

    def _build_stub_script(self, step: CalcStep) -> str:
        entry_point = step.entry_point or "run"
        return f'''import json, sys
context = json.load(sys.stdin)
def {entry_point}(ctx):
    return {{
        "status": "success",
        "outputs": {{
            "message": "python stub executed",
            "step_type": {step.step_type!r},
            "node_id": ctx.get("node_id")
        }},
        "logs": ["python stub executed"]
    }}
result = {entry_point}(context)
print(json.dumps(result))
'''

    def _parse_stdout(self, stdout: str) -> dict:
        try:
            return json.loads(stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ExecutorError(f"Invalid Python executor output: {exc}", "invalid_output") from exc


class CSharpExecutor(BaseExecutor):
    language = "csharp"

    def execute(self, step: CalcStep, context: dict) -> dict:
        if not step.artifact_path:
            return {
                "status": "success",
                "outputs": {
                    "message": "csharp stub executed",
                    "step_type": step.step_type,
                    "node_id": context.get("node_id"),
                },
                "logs": ["csharp artifact_path missing, stub response used"],
                "metrics": {"duration_ms": 0},
            }

        target = Path(step.artifact_path)
        if not target.exists():
            raise ExecutorError("C# artifact_path not found", "artifact_missing")

        command = ["dotnet", str(target)] if target.suffix == ".dll" else [str(target)]
        started_at = time.perf_counter()
        try:
            process = subprocess.run(
                command,
                input=json.dumps(context),
                text=True,
                capture_output=True,
                timeout=step.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutorError(f"C# executor timeout after {step.timeout_seconds}s", "timeout") from exc
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if process.returncode != 0:
            raise ExecutorError(process.stderr.strip() or "C# executor failed", "runtime_error")
        try:
            payload = json.loads(process.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ExecutorError(f"Invalid C# executor output: {exc}", "invalid_output") from exc
        payload.setdefault("status", "success")
        payload.setdefault("logs", [line for line in process.stderr.splitlines() if line])
        payload.setdefault("metrics", {})
        payload["metrics"]["duration_ms"] = duration_ms
        return payload


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors = {
            "python": PythonExecutor(),
            "csharp": CSharpExecutor(),
        }

    def get(self, language: str) -> BaseExecutor:
        executor = self._executors.get(language)
        if not executor:
            raise ExecutorError(f"Unsupported executor language: {language}", "unsupported_language")
        return executor
