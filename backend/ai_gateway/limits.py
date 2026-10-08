"""IA2 §6 — límites configurables del runtime del agente.

Un solo módulo con los topes que un job puede gastar: pasos por turno,
consultas por ronda, rondas de observación y el presupuesto total de
tiempo. Los valores son constantes de proceso (env-overridable para el
job runner); ninguno viaja en el payload del modelo.
"""

from __future__ import annotations

import os

# Pasos que una sola respuesta puede proponer (ops/tool/prepare/navigate).
MAX_STEPS = int(os.environ.get("AI_MAX_STEPS", "20"))
# Consultas de contexto que una ronda puede pedir.
MAX_QUERIES = int(os.environ.get("AI_MAX_QUERIES", "6"))
# Invocaciones: meta → hasta N-1 rondas de observar-y-replanificar.
MAX_ROUNDS = int(os.environ.get("AI_MAX_ROUNDS", "6"))
# Presupuesto total del job en segundos — expira honestamente en vez de
# colgar la sesión cuando el proveedor itera sin converger.
TOTAL_TIMEOUT_SECONDS = int(os.environ.get("AI_TOTAL_TIMEOUT_SECONDS", "240"))
# Correcciones de grounding permitidas tras una respuesta no citable.
MAX_REGROUNDS = int(os.environ.get("AI_MAX_REGROUNDS", "1"))
