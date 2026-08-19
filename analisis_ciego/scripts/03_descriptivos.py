"""PASO 4 -- Descriptivos antes que pruebas.
Unidad de analisis: promedio_por_caso (15 pares), segun decisiones_analisis.md.
Sin p-valores."""
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
TABLA = ROOT / "scripts" / "_tabla_pareada.json"
FIGURAS = ROOT / "figuras"
FIGURAS.mkdir(exist_ok=True)

with open(TABLA, encoding="utf-8") as f:
    tabla = json.load(f)

assert len(tabla) == 15, "la tabla pareada debe tener 15 filas"

CRITERIOS = ("relevancia", "viabilidad")
QUANTILE_METHOD = "linear"  # numpy default (= R type 7); no especificado en decisiones_analisis.md

print(f"Metodo de cuartiles: numpy.percentile, interpolation='{QUANTILE_METHOD}' (no fijado en decisiones_analisis.md, se documenta aqui por reproducibilidad)")

resumen = {}
for criterio in CRITERIOS:
    print(f"\n=== {criterio} ===")
    for fuente in ("sistema", "eh2"):
        vals = np.array([fila[f"{fuente}_{criterio}"] for fila in tabla])
        mediana = np.percentile(vals, 50, method=QUANTILE_METHOD)
        q1 = np.percentile(vals, 25, method=QUANTILE_METHOD)
        q3 = np.percentile(vals, 75, method=QUANTILE_METHOD)
        vmin, vmax = vals.min(), vals.max()
        print(f"  {fuente}: mediana={mediana:.4f}  Q1={q1:.4f}  Q3={q3:.4f}  min={vmin:.4f}  max={vmax:.4f}")
        resumen[(criterio, fuente)] = dict(mediana=mediana, q1=q1, q3=q3, min=vmin, max=vmax)

    diffs = np.array([fila[f"sistema_{criterio}"] - fila[f"eh2_{criterio}"] for fila in tabla])
    a_favor_sistema = int((diffs > 0).sum())
    a_favor_eh2 = int((diffs < 0).sum())
    empatados = int((diffs == 0).sum())
    print(f"\n  Diferencias pareadas (sistema - eh2), 15 casos:")
    for fila, d in zip(tabla, diffs):
        print(f"    caso {fila['caso']:>2}: {d:+.4f}")
    print(f"  A favor de sistema: {a_favor_sistema}  |  A favor de EH2: {a_favor_eh2}  |  Empatados: {empatados}")
    assert a_favor_sistema + a_favor_eh2 + empatados == 15

    resumen[(criterio, "diffs")] = diffs.tolist()
    resumen[(criterio, "conteo")] = dict(sistema=a_favor_sistema, eh2=a_favor_eh2, empate=empatados)

# --- Grafico simple de las diferencias ---
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
for ax, criterio in zip(axes, CRITERIOS):
    diffs = resumen[(criterio, "diffs")]
    casos = [fila["caso"] for fila in tabla]
    colores = ["#2a7f2a" if d > 0 else ("#a83232" if d < 0 else "#888888") for d in diffs]
    ax.bar(casos, diffs, color=colores)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(criterio)
    ax.set_xlabel("caso")
    ax.set_xticks(casos)
ax_left = axes[0]
ax_left.set_ylabel("diferencia (sistema - eh2)")
fig.suptitle("Diferencias pareadas por caso, sistema vs EH2 (promedio de 3 evaluadores)")
fig.tight_layout()
out_png = FIGURAS / "04_diferencias_pareadas.png"
fig.savefig(out_png, dpi=150)
print(f"\nGrafico guardado: {out_png}")

print("\nPASO 4 completo. Sin p-valores (segun instruccion).")
