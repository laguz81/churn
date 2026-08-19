"""PASO 1 -- Validacion de calificaciones.csv contra decisiones_analisis.md."""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
import statistics as stats

ROOT = Path(__file__).resolve().parent.parent
CALIF = ROOT / "calificaciones.csv"
DECODE = ROOT / "decode.json"

# --- 0. decode.json NO debe estar en esta carpeta ---
if DECODE.exists():
    print("DETENIDO: decode.json encontrado en analisis_ciego/. No continuar.")
    sys.exit(1)
print(f"OK decode.json ausente de {ROOT}")

# --- 1. Carga ---
with open(CALIF, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"Filas totales: {len(rows)} (esperado 180)")
assert len(rows) == 180, "filas != 180"

evaluadores = sorted({r["evaluador"] for r in rows})
casos = sorted({int(r["id_caso"]) for r in rows})
print(f"Evaluadores unicos: {len(evaluadores)} -> {evaluadores}")
print(f"Casos unicos: {len(casos)} -> min={min(casos)} max={max(casos)}")
assert len(evaluadores) == 3
assert len(casos) == 15

# --- 2. Completitud sin duplicados ---
combos = Counter((r["evaluador"], r["id_caso"], r["etiqueta"], r["criterio"]) for r in rows)
dups = {k: v for k, v in combos.items() if v > 1}
expected_keys = {
    (ev, str(c), et, cr)
    for ev in evaluadores
    for c in casos
    for et in ("A", "B")
    for cr in ("relevancia", "viabilidad")
}
missing = expected_keys - set(combos.keys())
extra = set(combos.keys()) - expected_keys

print(f"Combinaciones esperadas: {len(expected_keys)}")
print(f"Duplicados: {len(dups)}")
if dups:
    for k, v in dups.items():
        print(f"  DUP {k} x{v}")
print(f"Faltantes: {len(missing)}")
if missing:
    for k in sorted(missing):
        print(f"  FALTA {k}")
print(f"Combinaciones inesperadas (no en la matriz 3x15x2x2): {len(extra)}")
if extra:
    for k in sorted(extra):
        print(f"  EXTRA {k}")

# --- 3. Rango de puntaje ---
bad_puntaje = []
for r in rows:
    try:
        p = int(r["puntaje"])
    except (ValueError, TypeError):
        bad_puntaje.append(r)
        continue
    if p < 1 or p > 5:
        bad_puntaje.append(r)
print(f"Puntajes fuera de rango o no enteros/nulos: {len(bad_puntaje)}")
for r in bad_puntaje:
    print(f"  {r}")

# --- 4. Valores permitidos en etiqueta y criterio ---
etiquetas_bad = {r["etiqueta"] for r in rows} - {"A", "B"}
criterios_bad = {r["criterio"] for r in rows} - {"relevancia", "viabilidad"}
print(f"Valores de etiqueta fuera de {{A,B}}: {etiquetas_bad or 'ninguno'}")
print(f"Valores de criterio fuera de {{relevancia,viabilidad}}: {criterios_bad or 'ninguno'}")

# --- 5. Distribucion de frecuencias 1-5 ---
def dist(rows_subset):
    c = Counter(int(r["puntaje"]) for r in rows_subset)
    return {k: c.get(k, 0) for k in range(1, 6)}

print("\nDistribucion de puntajes por evaluador:")
for ev in evaluadores:
    subset = [r for r in rows if r["evaluador"] == ev]
    print(f"  {ev}: {dist(subset)}  (n={len(subset)})")

print("\nDistribucion de puntajes por criterio:")
for cr in ("relevancia", "viabilidad"):
    subset = [r for r in rows if r["criterio"] == cr]
    print(f"  {cr}: {dist(subset)}  (n={len(subset)})")

# --- 6. Varianza por evaluador ---
print("\nVarianza de puntaje por evaluador (poblacional, sobre sus 60 filas):")
for ev in evaluadores:
    vals = [int(r["puntaje"]) for r in rows if r["evaluador"] == ev]
    var = stats.pvariance(vals)
    moda = Counter(vals).most_common(1)[0]
    frac_moda = moda[1] / len(vals)
    flag = "  <-- POSIBLE BAJA VARIANZA" if var < 1.0 or frac_moda > 0.6 else ""
    print(f"  {ev}: var={var:.3f}  moda={moda[0]} ({frac_moda:.0%} de sus filas){flag}")

print("\nPASO 1 completo.")
