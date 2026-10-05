#!/usr/bin/env python3
"""Fast source guards protecting DEKOPEN's hard invariants.

Run via `make lint`. These are plain greps/regex checks — no orchestration.
The deeper proofs live in the test suites (engine purity tests, pgTAP).
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engine" / "src"
FRONTEND_SRC = ROOT / "frontend" / "src"
SUPABASE_DIR = ROOT / "supabase"

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"  FAIL {message}", flush=True)


def check_no_float_in_engine() -> None:
    """Engine math is Decimal-only; a float literal or call breaks determinism."""
    for path in sorted(ENGINE_SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            if re.search(r"\bfloat\(", line):
                fail(f"float() in engine source: {path}:{lineno}")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue  # syntax errors are reported by the compile/lint tooling
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                fail(f"float literal in engine source: {path}:{node.lineno}")


def check_no_hex_in_frontend() -> None:
    """UI colors come from semantic tokens, not hardcoded hex.

    `styles/tokens.css` is the token definition file — hex lives there by design.
    """
    pattern = re.compile(r"#[0-9a-fA-F]{6}\b")
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".css"} or ".test." in path.name:
            continue
        if path.name == "tokens.css":
            continue
        rel = path.relative_to(FRONTEND_SRC)
        # src/dev/ es el banco de pruebas de desarrollo: la página /dev/ui/mal
        # viola la Constitución a propósito para mostrar el contraste.
        if rel.parts[0] == "dev":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "0x" in line or "var(" in line:
                continue
            if pattern.search(line):
                fail(f"hardcoded hex color in frontend: {path}:{lineno}")


def _frontend_sources() -> list[Path]:
    """Scopes for UI guards: frontend/src except /dev/ (the Bien/Mal
    muestrario violates on purpose), tokens.css (definitions) and tests."""
    paths: list[Path] = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".css"}:
            continue
        rel = path.relative_to(FRONTEND_SRC)
        if rel.parts[0] == "dev":
            continue
        # API generada por orval: se regenera, no se corrige a mano.
        if rel.parts[0] == "api" and "generated" in rel.parts:
            continue
        if path.name == "tokens.css" or ".test." in path.name:
            continue
        paths.append(path)
    return paths


# ---- §10 guard table: each rule name → violations → ratchet baseline ----
#
# The baseline file scripts/guards-baseline.txt holds "RULE count" lines;
# a rule may never exceed its committed count. Fixing code is how the count
# drops — the file is regenerated with `--write-baseline` when a PR claims
# the improvement (or after clearing a category entirely).
GUARD_VIOLATIONS: dict[str, list[str]] = {}


def _violate(rule: str, path: Path, lineno: int, detail: str) -> None:
    rel = path.relative_to(ROOT)
    GUARD_VIOLATIONS.setdefault(rule, []).append(f"{rel}:{lineno}: {detail}")


_HEX_INLINE_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_RGB_INLINE_RE = re.compile(r"\brgba?\(")
_RADIUS_VALUE_RE = re.compile(r"border-(?:top-|bottom-|left-|right-)?(?:start-|end-)?(?:top-|bottom-)?(?:left-|right-)?radius\s*:\s*([^;}]+)")
_RADIUS_PX_RE = re.compile(r"(\d+(?:\.\d+)?)px")
_RADIUS_REM_RE = re.compile(r"(\d+(?:\.\d+)?)rem")
_SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;]+)")
_SHADOW_OK_RE = re.compile(r"^(?:none|0|var\(--(?:shadow-e\d|shadow-sheet|elevation-\d|sheet|shadow-raise|shadow-pop|shadow-modal|shadow-lg)\))$")
_GRADIENT_RE = re.compile(r"(?:linear|radial|conic)-gradient\(")
_BLUR_RE = re.compile(r"backdrop-filter|filter\s*:\s*blur\(")
_WEIGHT_RE = re.compile(r"font-weight\s*:\s*(?:700|800|900|bold|bolder)\b")
_FONTSIZE_PX_RE = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px")
_FONTSIZE_REM_RE = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)rem")
_TRANSITION_RE = re.compile(r"(?:transition(?:-duration)?|animation(?:-duration)?)\s*:\s*[^;]*?(\d+(?:\.\d+)?)(m?s)\b")
_ZINDEX_RE = re.compile(r"z-index\s*:\s*(-?\d+)")
_TOFIXED_RE = re.compile(r"\.toFixed\(")
_PATTERN_ATTR_RE = re.compile(r"(?<![\w-])pattern=")
_RAW_STATUS_RE = re.compile(r"\{[a-zA-Z_][\w.]*\.status\s*\}")
# Exclamaciones solo en texto JSX: `>¡Hola!<` o `>Hola! <` — nunca el `!`
# de código (`!==`, `!v`), por eso el `!` exige espacio o `<` después y el
# `>` previo no puede ser un `=>`.
_EXCLAMATION_TEXT_RE = re.compile(r"(?<!=)>[^<>{}]*?(?:¡|!(?=[\s<]))[^<>{}]*?<")
# UI text in English — the leaks that hurt most, matched as whole JSX text
# nodes or quoted ui strings.
_ENGLISH_WORDS = (
    "Loading", "Saving", "Cancel", "Delete", "Submit", "Retry", "Back",
    "Done", "Error", "Success", "Search", "Filter", "Sort", "Download",
    "Upload", "Preview", "Confirm", "Welcome", "Settings", "Sign in",
    "Log in", "Save changes", "Are you sure", "Coming soon", "Load more",
    "Show more", "Show less", "Read more", "See all", "View all",
    "No results", "Not found", "Try again", "Get started",
)
_ENGLISH_TEXT_RE = re.compile(
    r">\s*(?:" + "|".join(re.escape(w) for w in _ENGLISH_WORDS) + r")\b\s*<"
)
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️\U0001F1E6-\U0001F1FF]"
)


def check_ui_slop_rules() -> None:
    """Constitution §10: the static guards over frontend/src."""
    for path in _frontend_sources():
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            if _GRADIENT_RE.search(line):
                _violate("ui-gradient", path, lineno, stripped[:80])
            if _BLUR_RE.search(line):
                _violate("ui-blur", path, lineno, stripped[:80])
            if _WEIGHT_RE.search(line):
                _violate("ui-weight-700", path, lineno, stripped[:80])
            m = _SHADOW_RE.search(line)
            if m:
                value = m.group(1).strip()
                if not _SHADOW_OK_RE.match(value):
                    _violate("ui-shadow-off", path, lineno, f"box-shadow: {value[:60]}")
            m = _RADIUS_VALUE_RE.search(line)
            if m:
                value = m.group(1)
                if "var(" not in value and "%" not in value and value.strip() != "0":
                    for pmatch in _RADIUS_PX_RE.finditer(value):
                        if float(pmatch.group(1)) > 4:
                            _violate("ui-radius>4", path, lineno, stripped[:80])
                            break
                    for pmatch in _RADIUS_REM_RE.finditer(value):
                        if float(pmatch.group(1)) > 0.25:
                            _violate("ui-radius>4", path, lineno, stripped[:80])
                            break
            for tmatch in _TRANSITION_RE.finditer(line):
                amount = float(tmatch.group(1))
                ms = amount if tmatch.group(2) == "ms" else amount * 1000
                if ms > 280:
                    _violate("ui-motion>280", path, lineno, stripped[:80])
                    break
            if _ZINDEX_RE.search(line) and "var(" not in line:
                _violate("ui-z-literal", path, lineno, stripped[:80])
            m = _FONTSIZE_PX_RE.search(line)
            if m and float(m.group(1)) < 11:
                _violate("ui-font<11", path, lineno, stripped[:80])
            m = _FONTSIZE_REM_RE.search(line)
            if m and float(m.group(1)) < 0.6875:
                _violate("ui-font<11", path, lineno, stripped[:80])
            if path.suffix in {".ts", ".tsx"}:
                if _TOFIXED_RE.search(line):
                    _violate("ui-tofixed", path, lineno, stripped[:80])
                if _PATTERN_ATTR_RE.search(line):
                    _violate("ui-pattern", path, lineno, stripped[:80])
                if _RAW_STATUS_RE.search(line):
                    _violate("ui-raw-status", path, lineno, stripped[:80])
                if _EXCLAMATION_TEXT_RE.search(line):
                    _violate("ui-exclamation", path, lineno, stripped[:80])
                if _ENGLISH_TEXT_RE.search(line):
                    _violate("ui-english", path, lineno, stripped[:80])
                if _EMOJI_RE.search(line):
                    _violate("ui-emoji", path, lineno, stripped[:80])
            if path.suffix == ".css":
                # Hex/rgb fuera de tokens.css (el guard clásico cubre tsx).
                if _HEX_INLINE_RE.search(line) and "var(" not in line:
                    _violate("ui-hex-inline", path, lineno, stripped[:80])
                if _RGB_INLINE_RE.search(line) and "var(" not in line:
                    _violate("ui-rgb-inline", path, lineno, stripped[:80])
        # English inside i18n file values is impossible — that file IS the
        # language; check it apart from the generic .ts loop is unnecessary.


def check_guards_baseline(write: bool) -> None:
    """Ratchet: every rule stays at or below its committed count."""
    baseline_file = ROOT / "scripts" / "guards-baseline.txt"
    if write:
        ordered = sorted(GUARD_VIOLATIONS.items())
        content = "".join(f"{rule} {len(items)}\n" for rule, items in ordered)
        baseline_file.write_text(
            "# Línea base del trinquete §10 — regenerar solo al mejorar.\n"
            "# Regla + conteo máximo permitido; subir el número es la falla.\n" + content,
            encoding="utf-8",
        )
        print(f"  baseline written: {len(ordered)} rules", flush=True)
        return
    baseline: dict[str, int] = {}
    if baseline_file.is_file():
        for line in baseline_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rule, _, count = line.partition(" ")
            baseline[rule] = int(count)
    for rule in sorted(set(GUARD_VIOLATIONS) | set(baseline)):
        count = len(GUARD_VIOLATIONS.get(rule, []))
        limit = baseline.get(rule, 0)
        if count > limit:
            for detail in GUARD_VIOLATIONS.get(rule, []):
                print(f"  NEW  {rule}: {detail}", flush=True)
            fail(f"ui guard '{rule}' grew past baseline: {count} > {limit}")
        elif count:
            print(f"  note  {rule}: {count}/{limit} (baseline)", flush=True)


def check_database_contract() -> None:
    """Every tenant table keeps RLS; money/dimensions never use float SQL types."""
    migrations = sorted((SUPABASE_DIR / "migrations").glob("*.sql"))
    if not migrations:
        fail("no supabase migrations found")
        return
    migration = "\n".join(p.read_text(encoding="utf-8") for p in migrations)
    normalized = " ".join(migration.lower().split())

    tables = set(
        re.findall(r"CREATE TABLE public\.(\w+)\s*\(", migration, flags=re.IGNORECASE)
    )
    if not tables:
        fail("no public.* tables found in migrations")
    for table in sorted(tables):
        rls = f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;"
        if rls not in migration:
            fail(f"RLS is not enabled for table: {table}")

    without_literals = re.sub(r"'(?:''|[^'])*'", "''", migration, flags=re.DOTALL)
    executable_sql = re.sub(r"--[^\n]*", "", without_literals)
    match = re.search(r"\b(?:REAL|FLOAT\d*|DOUBLE\s+PRECISION)\b", executable_sql, re.IGNORECASE)
    if match is not None:
        fail(f"floating point SQL type is forbidden: {match.group(0)}")

    for fragment in (
        "create or replace function private.current_user_org_ids()",
        "security definer set search_path = ''",
        "grant execute on function private.current_user_org_ids() to authenticated",
        "revoke all on public.payment_events from anon, authenticated",
    ):
        if fragment not in normalized:
            fail(f"required database security contract is missing: {fragment}")
    if "public.current_user_org_ids" in normalized:
        fail("RLS policies must call private.current_user_org_ids() explicitly")

    seed_path = SUPABASE_DIR / "seed.sql"
    if not seed_path.is_file() or "'DEMO_60'" not in seed_path.read_text(encoding="utf-8"):
        fail("canonical global DEMO_60 seed is missing")


def main() -> None:
    write_baseline = "--write-baseline" in sys.argv
    print("Source guards", flush=True)
    check_no_float_in_engine()
    check_no_hex_in_frontend()
    check_database_contract()
    check_ui_slop_rules()
    check_guards_baseline(write_baseline)
    if write_baseline:
        return
    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} guard violation(s)", flush=True)
        sys.exit(1)
    print("[PASS] source guards", flush=True)


if __name__ == "__main__":
    main()
