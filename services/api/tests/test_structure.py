"""Structural guards. These run in CI to keep the ethos honest:

- No direct boto3 / botocore import anywhere under app/. Storage is
  delegated to genblaze-s3, which owns the boto3 client (and sets its
  own b2ai-genblaze user agent on it).
- All genblaze_* imports live inside app/repo/ (the runtime/handlers
  see Genblaze types only via Pydantic models returned upward).
- repo/pipelines.py stays under the documented ceiling (170 today; see
  `test_pipelines_file_stays_lean` for the per-gap rationale) so the
  sample remains a readable reference, not a framework.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
REPO_DIR = APP_ROOT / "repo"
FORBIDDEN_TOP = {"boto3", "botocore"}
GENBLAZE_PREFIXES = ("genblaze_", "genblaze.")


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imports(path: Path) -> list[ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]


def test_no_direct_boto3_import() -> None:
    """Nothing under app/ may `import boto3` or `from boto3 ...` (or botocore)."""
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        for node in _imports(path):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_TOP:
                        offenders.append(f"{path}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                if top in FORBIDDEN_TOP:
                    offenders.append(f"{path}:{node.lineno} from {node.module} import ...")
    assert not offenders, "Direct boto3/botocore imports are forbidden:\n" + "\n".join(offenders)


def test_genblaze_imports_only_in_repo() -> None:
    """`genblaze_*` may only be imported from app/repo/. Handlers consume
    Genblaze types via the Pydantic models the repo layer returns.

    Exception: app/main.py is allowed to reference genblaze_core.exceptions
    so it can catch ProviderError directly. The exception type IS the
    contract surfaced to the client; mirroring it would be ceremony.
    """
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        if REPO_DIR in path.parents:
            continue
        for node in _imports(path):
            module = (
                ".".join(a.name for a in node.names)
                if isinstance(node, ast.Import)
                else (node.module or "")
            )
            if not any(module.startswith(p) for p in GENBLAZE_PREFIXES):
                continue
            # Allow main.py exception/enum/asset imports — these ARE the
            # public contract (typed exceptions surfaced to clients; Asset
            # reconstructed from BriefingRequest fields for external_inputs=).
            if path.name == "main.py" and module in {
                "genblaze_core.exceptions",
                "genblaze_core.models.enums",
                "genblaze_core.models.asset",
            }:
                continue
            offenders.append(f"{path}:{node.lineno} -> {module}")
    assert not offenders, (
        "genblaze_* imports outside app/repo/ (or unallowlisted main.py imports):\n"
        + "\n".join(offenders)
    )


def test_pipelines_file_stays_lean() -> None:
    """Keep the canonical example small enough to read in one sitting."""
    pipelines = REPO_DIR / "pipelines.py"
    line_count = sum(1 for _ in pipelines.read_text(encoding="utf-8").splitlines())
    assert line_count < 200, f"pipelines.py grew to {line_count} lines (>=200)"
