"""IA2 §1 — exporta el registro tipado de ops a TypeScript.

``backend/projects/ops_registry.py`` es la única fuente: este script
vuelca ``contract_document()`` a
``frontend/src/features/commands/opsContract.generated.ts`` para que el
decode de comandos de la UI valide contra el MISMO contrato que el
validador del asistente y el prompt del agente — sin copias manuales que
deriven (check_generated_api lo regenera y rechaza deriva).

Uso: ``.venv/bin/python scripts/gen_ops_contract.py`` desde la raíz.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "features" / "commands" / "opsContract.generated.ts"

# El registro solo usa dataclasses+typing — no Django: importar el
# backend como path es suficiente sin bootear settings.
sys.path.insert(0, str(ROOT / "backend"))

from projects.ops_registry import contract_document  # noqa: E402


def main() -> None:
    document = contract_document()
    body = json.dumps(document, ensure_ascii=False, indent=2)
    op_names = " | ".join(f'"{op["name"]}"' for op in document["ops"])
    scopes = " | ".join(f'"{scope}"' for scope in document["scopes"])
    OUT.write_text(
        "// GENERADO por scripts/gen_ops_contract.py — la fuente es\n"
        "// backend/projects/ops_registry.py; no editar a mano.\n"
        "/* eslint-disable prettier/prettier */\n\n"
        "export const OPS_CONTRACT_VERSION = "
        f"{document['version']} as const;\n\n"
        "export type OpsScope = " + scopes + ";\n\n"
        "export type OpsContractOpName = " + op_names + ";\n\n"
        "export interface OpsContractParam {\n"
        "  name: string;\n"
        "  kind: string;\n"
        "  required: boolean;\n"
        "  enum: string[];\n"
        "  numeric: boolean;\n"
        "  ref: string;\n"
        "  allow_wildcard: boolean;\n"
        "  nullable: boolean;\n"
        "  catalog: string;\n"
        "  description: string;\n"
        "}\n\n"
        "export interface OpsContractEntry {\n"
        "  name: OpsContractOpName;\n"
        "  scope: OpsScope;\n"
        "  batchable: boolean;\n"
        "  structural: boolean;\n"
        "  description: string;\n"
        "  params: OpsContractParam[];\n"
        "  examples: Record<string, unknown>[];\n"
        "}\n\n"
        "export const OPS_CONTRACT: {\n"
        "  version: number;\n"
        "  scopes: OpsScope[];\n"
        "  ops: OpsContractEntry[];\n"
        "  schema: Record<string, unknown>;\n"
        "} = " + body + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({len(document['ops'])} ops)")


if __name__ == "__main__":
    main()
