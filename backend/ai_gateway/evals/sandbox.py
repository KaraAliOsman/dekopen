"""Sandbox de aplicación de operaciones de diseño.

Las ops propuestas por el asistente se aplican sobre una COPIA del producto
de entrada ejecutando el reducer real del frontend (`applyDesignOps` en
frontend/src/features/canvas/designOps.ts, que despacha sobre
`ASSEMBLY_COMMANDS`/`applyDesignOpOn`) dentro de un proceso Node empaquetado
con el esbuild ya presente en `frontend/node_modules`. El arnés nunca
reimplementa la semántica de las operaciones en Python — si el reducer de la
UI rechaza una op, el sandbox la rechaza igual.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
ESBUILD = REPO_ROOT / "frontend" / "node_modules" / ".bin" / "esbuild"
ENTRY = Path(__file__).resolve().with_name("sandbox_apply_entry.ts")


class SandboxUnavailable(RuntimeError):
    """esbuild o node no están disponibles en este entorno."""


class OpsSandbox:
    """Aplica ops sobre copias del producto. El bundle se compila una vez
    por corrida; cada aplicación es un proceso Node aislado sin estado."""

    def __init__(self) -> None:
        self._bundle: Path | None = None

    def _ensure_bundle(self) -> Path:
        if self._bundle is not None:
            return self._bundle
        if not ESBUILD.exists():
            raise SandboxUnavailable(
                f"esbuild no está instalado en {ESBUILD} "
                "(corre `npm --prefix frontend install` primero)."
            )
        if shutil.which("node") is None:
            raise SandboxUnavailable("node no está en el PATH.")
        out = Path(tempfile.gettempdir()) / "dekopen_evals_sandbox_apply.mjs"
        result = subprocess.run(
            [
                str(ESBUILD),
                str(ENTRY),
                "--bundle",
                "--platform=node",
                "--format=esm",
                f"--outfile={out}",
                "--log-level=warning",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            raise SandboxUnavailable(f"esbuild falló: {result.stderr.strip()[:400]}")
        self._bundle = out
        return out

    def apply(
        self,
        product: dict,
        ops: list[dict[str, Any]],
        members: dict[str, Any] | None = None,
    ) -> dict:
        """Devuelve el ProductJson resultante de aplicar `ops` sobre una
        copia de `product`. Lanza SandboxUnavailable si el entorno no puede
        ejecutar el reducer. `members` es la geometría de roles del sistema
        ({frame_mm, sash_mm, mullion_*}) que el canvas resuelve con
        resolveMembers — sin ella las ops estructurales no-opan igual que en
        la UI sin catálogo."""
        bundle = self._ensure_bundle()
        with tempfile.TemporaryDirectory(prefix="eval-ops-") as tmp:
            in_path = Path(tmp) / "in.json"
            out_path = Path(tmp) / "out.json"
            in_path.write_text(
                json.dumps(
                    {"product": product, "ops": ops, "members": members or {}},
                    default=str,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["node", str(bundle), str(in_path), str(out_path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(REPO_ROOT),
            )
            if not out_path.exists():
                raise SandboxUnavailable(
                    f"el sandbox no produjo salida: {result.stderr.strip()[:400]}"
                )
            report = json.loads(out_path.read_text(encoding="utf-8"))
        if not report.get("ok"):
            raise SandboxUnavailable(str(report.get("error") or "sandbox error"))
        return report["product"]
