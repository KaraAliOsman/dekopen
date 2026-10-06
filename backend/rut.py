"""Validación de RUT chileno (módulo 11).

La misma regla que el frontend (`isValidRut` en format.ts): cuerpo de 1–8
dígitos, dígito verificador calculado por módulo 11. Se usa en la compuerta
de emisión documental y en el RUT que declara quien decide en el portal.
"""

from __future__ import annotations

import re

_CLEAN = re.compile(r"[.\-\s]")
_PATTERN = re.compile(r"^\d{1,8}[\dK]$")


def rut_mod11_valid(value: object) -> bool:
    """True si el RUT es sintácticamente válido y el dígito cuadra.

    Vacío o ausente es inválido: la emisión exige cliente identificado.
    """
    if not isinstance(value, str):
        return False
    cleaned = _CLEAN.sub("", value).upper()
    if not _PATTERN.match(cleaned):
        return False
    body, digit = cleaned[:-1], cleaned[-1]
    total, factor = 0, 2
    for char in reversed(body):
        total += int(char) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return digit == expected
