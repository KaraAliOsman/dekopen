"""OGUC art. 4.1.10 — datos normativos transcritos del texto oficial.

Fuente: Decreto Supremo que modifica la OGUC, publicado en el Diario Oficial
N° 43.860 del lunes 27 de mayo de 2024 (CVE 2494861), MINVU — vigente desde
el 28 de noviembre de 2025 (18 meses de vacatio). La transcripción está
congelada en ``tests/test_oguc_4110.py``: una doble entrada de cada celda
comparada contra esta tabla falla si algún valor se desvía del oficial.

- TABLA 3: porcentaje máximo de superficie de ventanas por orientación y
  valor U, por zona térmica (uso residencial, numeral 1).
- TABLA 4: rangos angulares de las orientaciones (0° = norte geográfico).
- TABLA 5: Upvm máximo ponderado ventana+muro por orientación y U de ventana
  (alternativa a la Tabla 3, zonas B–I).
- TABLA 9 / TABLA 16: clase final de permeabilidad al aire medida a 100 Pa
  (NCh 3296/3297) mínima para puertas opacas y ventanas — idénticas entre
  uso residencial y equipamiento.
- TABLA 12: transmitancia U máxima de ventanas para equipamiento (educación
  y salud, y hoteles del uso residencial) por zona térmica.
- Regla de techumbre: complejo de ventanas en plano con inclinación ≤60°
  desde la horizontal, zonas B a I inclusive → U ≤ 3,6 W/(m²K).
"""

from decimal import Decimal

ZONES = ("A", "B", "C", "D", "E", "F", "G", "H", "I")

# Orientaciones de paramentos verticales según la Tabla 3: Norte,
# Oriente-Poniente, Sur y Orientación Global Teórica (OGT).
ORIENTATIONS = ("N", "OP", "S", "OGT")

# Umbrales de la columna de U de la Tabla 3 (W/m²K): una ventana con U ≤
# 0,6 calza en la primera columna; con U > 5,8 la tabla no le da porcentaje.
U_THRESHOLDS = (
    Decimal("0.6"), Decimal("0.8"), Decimal("1.2"), Decimal("1.6"),
    Decimal("2.0"), Decimal("2.4"), Decimal("2.8"), Decimal("3.2"),
    Decimal("3.6"), Decimal("4.0"), Decimal("4.4"), Decimal("5.8"),
)

# TABLA 3 — % máximo de superficie de ventanas. zone → orientation →
# 12 valores, uno por umbral de U_THRESHOLDS.
WINDOW_MAX_PCT: dict[str, dict[str, tuple[int, ...]]] = {
    "A": {
        "N":   (100, 100, 100, 100, 100, 98, 97, 95, 94, 91, 88, 50),
        "OP":  (100, 100, 99, 96, 94, 91, 87, 84, 80, 75, 69, 30),
        "S":   (94, 93, 91, 89, 85, 82, 78, 74, 69, 63, 57, 25),
        "OGT": (54, 53, 52, 51, 50, 49, 48, 46, 44, 42, 40, 25),
    },
    "B": {
        "N":   (100, 99, 98, 97, 96, 94, 92, 90, 88, 85, 82, 30),
        "OP":  (92, 91, 89, 87, 84, 81, 78, 75, 71, 66, 60, 20),
        "S":   (86, 84, 81, 78, 75, 71, 68, 64, 59, 54, 47, 10),
        "OGT": (52, 51, 49, 47, 46, 45, 43, 42, 40, 38, 35, 10),
    },
    "C": {
        "N":   (96, 95, 94, 93, 91, 90, 88, 85, 83, 79, 75, 40),
        "OP":  (82, 81, 79, 77, 75, 72, 69, 66, 62, 58, 52, 35),
        "S":   (75, 73, 70, 67, 64, 61, 58, 54, 49, 44, 38, 15),
        "OGT": (47, 46, 45, 44, 42, 41, 39, 37, 35, 33, 30, 15),
    },
    "D": {
        "N":   (94, 93, 91, 89, 87, 85, 83, 80, 77, 73, 69, 25),
        "OP":  (73, 72, 70, 68, 65, 63, 60, 57, 53, 49, 44, 15),
        "S":   (62, 61, 59, 57, 54, 51, 48, 44, 40, 35, 29, 10),
        "OGT": (43, 42, 41, 40, 38, 37, 35, 33, 31, 28, 25, 10),
    },
    "E": {
        "N":   (90, 89, 87, 85, 83, 80, 78, 75, 71, 67, 61, 10),
        "OP":  (63, 62, 60, 58, 56, 54, 51, 48, 45, 41, 35, 8),
        "S":   (51, 50, 48, 46, 44, 41, 38, 35, 31, 26, 20, 5),
        "OGT": (39, 38, 37, 36, 34, 32, 30, 28, 26, 23, 19, 5),
    },
    "F": {
        "N":   (88, 86, 83, 80, 78, 76, 73, 69, 65, 60, 54, 0),
        "OP":  (54, 53, 51, 49, 47, 45, 42, 40, 36, 32, 27, 0),
        "S":   (41, 40, 38, 36, 34, 31, 28, 25, 21, 17, 12, 0),
        "OGT": (36, 35, 33, 31, 30, 28, 26, 24, 21, 17, 13, 0),
    },
    "G": {
        "N":   (84, 82, 79, 76, 74, 71, 67, 64, 59, 54, 46, 0),
        "OP":  (43, 42, 41, 40, 38, 36, 34, 31, 28, 24, 20, 0),
        "S":   (31, 30, 28, 26, 24, 21, 19, 16, 13, 8, 0, 0),
        "OGT": (32, 31, 29, 27, 26, 24, 21, 19, 16, 12, 0, 0),
    },
    "H": {
        "N":   (77, 76, 74, 72, 69, 66, 62, 58, 53, 47, 38, 0),
        "OP":  (34, 33, 32, 31, 29, 27, 25, 23, 20, 16, 12, 0),
        "S":   (30, 29, 27, 25, 23, 20, 18, 15, 12, 7, 0, 0),
        "OGT": (31, 30, 28, 26, 25, 23, 20, 18, 15, 11, 0, 0),
    },
    "I": {
        "N":   (75, 73, 70, 67, 64, 61, 57, 52, 46, 39, 30, 0),
        "OP":  (43, 42, 41, 40, 38, 36, 34, 31, 28, 24, 20, 0),
        "S":   (28, 27, 25, 23, 21, 18, 16, 13, 10, 5, 0, 0),
        "OGT": (29, 28, 26, 24, 23, 21, 18, 16, 13, 10, 0, 0),
    },
}

# TABLA 4 — rangos angulares de cada orientación (grados sexagesimales,
# dirección normal al plano de fachada; 0° = norte geográfico).
ORIENTATION_RANGES_DEG = {
    "N": (Decimal("315"), Decimal("45")),
    "E": (Decimal("45"), Decimal("135")),
    "S": (Decimal("135"), Decimal("225")),
    "W": (Decimal("225"), Decimal("315")),
}

# TABLA 9 (residencial) / TABLA 16 (equipamiento) — clase final de
# permeabilidad al aire mínima a 100 Pa (NCh 3296/3297). None = sin exigencia.
AIR_CLASS_MIN: dict[str, int | None] = {
    "A": None,
    "B": 1,
    "C": 1,
    "D": 2,
    "E": 2,
    "F": 2,
    "G": 3,
    "H": 3,
    "I": 3,
}

# TABLA 12 — U máxima del complejo de ventanas para equipamiento (educación
# y salud) y para hoteles del uso residencial, por zona térmica.
EQUIPMENT_WINDOW_U_MAX: dict[str, Decimal] = {
    "A": Decimal("5.80"),
    "B": Decimal("3.60"),
    "C": Decimal("3.60"),
    "D": Decimal("3.60"),
    "E": Decimal("3.00"),
    "F": Decimal("3.00"),
    "G": Decimal("3.00"),
    "H": Decimal("2.40"),
    "I": Decimal("3.00"),
}

# Regla de techumbre: ventanas en plano ≤60° desde la horizontal en zonas
# B a I (ambas inclusive) deben tener U ≤ 3,6 W/(m²K). La zona A no la exige.
ROOF_WINDOW_U_MAX = Decimal("3.6")
ROOF_WINDOW_ZONES = frozenset(ZONES) - {"A"}


def orientation_group(degrees: Decimal) -> str | None:
    """Tabla 4: rango angular → grupo de orientación de la Tabla 3.

    Norte [315°, 45°), Oriente [45°, 135°), Sur [135°, 225°),
    Poniente [225°, 315°). E y O comparten la fila O-P.
    """
    value = degrees % Decimal("360")
    if value >= Decimal("315") or value < Decimal("45"):
        return "N"
    if value < Decimal("135"):
        return "OP"
    if value < Decimal("225"):
        return "S"
    return "OP"


def u_threshold_index(uw: Decimal) -> int | None:
    """Columna de la Tabla 3 para un valor U — el primer umbral ≥ uw."""
    for index, threshold in enumerate(U_THRESHOLDS):
        if uw <= threshold:
            return index
    return None


def window_max_pct(zone: str, orientation: str, uw: Decimal) -> int | None:
    """Tabla 3 (residencial): % máximo de superficie de ventanas para la
    orientación y la columna de U que corresponde al Uw. None si el Uw
    supera el último umbral (5,8) — la tabla no le asigna porcentaje."""
    index = u_threshold_index(uw)
    if index is None:
        return None
    return WINDOW_MAX_PCT[zone][orientation][index]
