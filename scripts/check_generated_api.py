"""Regenerate OpenAPI and Orval artifacts and reject any source drift."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "backend" / "openapi.yaml"
GENERATED = ROOT / "frontend" / "src" / "api" / "generated"


OPS_CONTRACT = ROOT / "frontend" / "src" / "features" / "commands" / "opsContract.generated.ts"


def snapshot() -> dict[str, bytes]:
    paths = [OPENAPI, OPS_CONTRACT, *sorted(GENERATED.rglob("*.ts"))]
    return {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}


def run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    if not OPENAPI.is_file() or not GENERATED.is_dir():
        raise SystemExit("OpenAPI or generated TypeScript client is missing")
    before = snapshot()
    run(
        [
            sys.executable,
            "backend/manage.py",
            "spectacular",
            "--file",
            "backend/openapi.yaml",
            "--validate",
            "--fail-on-warn",
        ],
        ROOT,
    )
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to verify generated-client drift")
    run([npm, "run", "api:generate"], ROOT / "frontend")
    # IA2 §1 — el contrato tipado de ops también es artefacto generado:
    # el TS derivado del registro debe ser reproducible, no editado a mano.
    run([sys.executable, "scripts/gen_ops_contract.py"], ROOT)
    after = snapshot()
    changed = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    if changed:
        raise SystemExit("Generated API drift detected: " + ", ".join(changed))
    print("OpenAPI and generated TypeScript client are reproducible")


if __name__ == "__main__":
    main()
