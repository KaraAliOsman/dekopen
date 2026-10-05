"""Run real +/-0.01 mm formula mutants in disposable copies, never in the checkout."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = {
    "sash-welding": ("width + loss, height + loss", "width + loss + DELTA, height + loss"),
    "steel-gap": ("- _TWO * article.reinforcement_gap_mm", "- _TWO * article.reinforcement_gap_mm + DELTA"),
    "bead-cut-width": ("length_mm=width_mm + rule.cut_add_mm,", "length_mm=width_mm + rule.cut_add_mm + DELTA,"),
    "bead-cut-height": ("length_mm=height_mm + rule.cut_add_mm,", "length_mm=height_mm + rule.cut_add_mm + DELTA,"),
    "sliding-cut-width": ("cut_width = finished_width + sliding.sliding_end_add_mm", "cut_width = finished_width + sliding.sliding_end_add_mm + DELTA"),
    "sliding-cut-height": ("rect.height_mm - _TWO * sliding.pulley_height_mm", "rect.height_mm - _TWO * sliding.pulley_height_mm + DELTA"),
    "sliding-glass-width": ("width -= sliding.sliding_glazing_deduction_width_mm", "width -= sliding.sliding_glazing_deduction_width_mm + DELTA"),
    "sliding-glass-height": ("height -= sliding.sliding_glazing_deduction_height_mm", "height -= sliding.sliding_glazing_deduction_height_mm + DELTA"),
    "door-jamb": ("length_mm=nominal_height_mm + per_end,", "length_mm=nominal_height_mm + per_end + DELTA,"),
    "door-width": ("clear_width - _TWO * params.door_leaf_side_clearance_mm", "clear_width - _TWO * params.door_leaf_side_clearance_mm + DELTA"),
    "door-height": ("- params.door_bottom_clearance_mm\n        + params.sash_overlap_mm", "- params.door_bottom_clearance_mm\n        + params.sash_overlap_mm + DELTA"),
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dekopen-shot06-mutations-") as directory:
        workspace = Path(directory).resolve()
        if not workspace.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise SystemExit("Mutation workspace escaped the system temporary directory")
        for part in ("src", "tests", "scripts"):
            shutil.copytree(ROOT / "engine" / part, workspace / "engine" / part,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (workspace / "pytest.ini").write_text(
            "[pytest]\npythonpath = . engine/src\naddopts = --strict-config --strict-markers\n",
            encoding="utf-8",
        )
        source = workspace / "engine/src/dekopen_engine/geometry.py"
        original = source.read_text(encoding="utf-8")
        command = [sys.executable, "-m", "pytest", "-c", "pytest.ini",
                   "engine/tests/test_shot06_core.py", "-q", "-W", "error"]
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(command, cwd=workspace, env=env, capture_output=True,
                                  text=True, encoding="utf-8", check=False)

        baseline = run()
        if baseline.returncode != 0:
            raise SystemExit("Unmutated Core tests failed:\n" + baseline.stdout + baseline.stderr)
        for name, (old, template) in MUTATIONS.items():
            if original.count(old) != 1:
                raise SystemExit(f"Mutation site is missing or ambiguous: {name}")
            for delta in ("0.01", "-0.01"):
                source.write_text(original.replace(old, template.replace("DELTA", f'Decimal("{delta}")')),
                                  encoding="utf-8")
                result = run()
                if result.returncode != 1 or "AssertionError" not in result.stdout:
                    raise SystemExit(f"Mutant survived or tests did not assert: {name} {delta}\n"
                                     + result.stdout + result.stderr)
                print(f"  KILLED {name} {delta} mm", flush=True)
        print(f"Core formula mutations: {len(MUTATIONS) * 2}/{len(MUTATIONS) * 2} killed", flush=True)


if __name__ == "__main__":
    main()
