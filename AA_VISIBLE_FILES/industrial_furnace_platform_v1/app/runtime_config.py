import csv
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
WORKSPACE_TMP_DIR = WORKSPACE_ROOT / ".monkeycode-tmp-files"

AI_ENV_KEYS = (
    "AI_API_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_PROVIDER_NAME",
    "AI_PROVIDER_TYPE",
    "CLAUDE_API_URL",
    "CLAUDE_API_KEY",
    "CLAUDE_MODEL",
    "CLAUDE_PROVIDER_NAME",
    "CLAUDE_API_TYPE",
    "CLAUDE_API_VERSION",
    "TENCENT_API_URL",
    "TENCENT_API_KEY",
    "TENCENT_MODEL",
    "TENCENT_PROVIDER_NAME",
    "TENCENT_API_TYPE",
    "TENCENT_SECRET_ID",
    "TENCENT_SECRET_KEY",
)


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in AI_ENV_KEYS or os.getenv(key):
            continue
        os.environ[key] = _strip_wrapping_quotes(value.strip())


def _candidate_tencent_secret_csv_paths() -> list[Path]:
    candidates = []
    if WORKSPACE_TMP_DIR.exists():
        candidates.extend(sorted(WORKSPACE_TMP_DIR.glob("*SecretKey*.csv")))
    return candidates


def _load_tencent_secret_csv(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader, None)
    if not row:
        return
    secret_id = (row.get("SecretId") or "").strip()
    secret_key = (row.get("SecretKey") or "").strip()
    if secret_id and not os.getenv("TENCENT_SECRET_ID"):
        os.environ["TENCENT_SECRET_ID"] = secret_id
    if secret_key and not os.getenv("TENCENT_SECRET_KEY"):
        os.environ["TENCENT_SECRET_KEY"] = secret_key


def load_runtime_ai_env() -> None:
    for path in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"):
        _load_dotenv_file(path)
    for path in _candidate_tencent_secret_csv_paths():
        _load_tencent_secret_csv(path)
