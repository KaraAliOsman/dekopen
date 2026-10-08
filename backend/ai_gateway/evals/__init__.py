"""Arnés de evaluación por resultado para la IA de DEKOPEN (encargo IA1).

Corre los 26 casos del diagnóstico contra las mismas rutas que usa la UI
(design-assist del editor, el agente del Orbe y la pregunta contextual del
dock), aplica las operaciones propuestas sobre una copia del producto con el
reducer real del frontend y evalúa el modelo resultante — nunca el texto.

Uso:
    cd backend && python -m ai_gateway.evals.run --provider MOCK \
        --out ../docs/ai/evals/<fecha>-mock.json
"""
