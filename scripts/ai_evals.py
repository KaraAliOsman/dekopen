"""Entry point del arnés de evaluación IA1 desde la raíz del repo.

    python scripts/ai_evals.py --provider MOCK --out docs/ai/evals/<fecha>.json

Envuelve `ai_gateway.evals.run` (vive en backend/): añade backend/ a sys.path
y delega en su main(). La evaluación es no bloqueante por diseño — los casos
fallidos se reportan en el JSON; sólo un error del propio arnés sale != 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ai_gateway.evals.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
