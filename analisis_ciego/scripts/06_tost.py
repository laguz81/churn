"""PASO 7 -- Equivalencia (TOST), por dos vias.

El Wilcoxon de PASO 5 no detecto diferencia (p=0.197 relevancia,
p=0.603 viabilidad). Ausencia de diferencia NO es evidencia de
equivalencia: se corre TOST (two one-sided tests) contra el margen
de equivalencia congelado en decisiones_analisis.md (+-0.5 puntos
Likert, escala promedio_por_caso).

alfa = 0.05, fijado en este paso (no estaba en decisiones_analisis.md
original). La conclusion del PASO 5 es invariante a cualquier alfa
convencional (0.01, 0.05 o 0.10): los p-valores 0.197 y 0.603 estan
muy por encima de los tres. Ver decisiones_analisis.md para el
registro del alfa como decision anadida con posterioridad.

Via 1 -- TOST por dos Wilcoxon de una cola:
  Se trabaja sobre la SUMA ENTERA de los 3 evaluadores (misma
  correccion de escala x3 que PASO 5, misma correccion de Pratt).
  El margen 0.5 (escala promedio_por_caso) equivale a 1.5 en escala
  suma entera -- 1.5 es exacto en float64, no reintroduce el bug de
  precision de PASO 5.
    H01: mediana(diff) <= -0.5   vs   > -0.5   (desplazar +1.5, alternative='greater')
    H02: mediana(diff) >= +0.5   vs   < +0.5   (desplazar -1.5, alternative='less')
  Equivalencia solo si AMBAS H0 se rechazan (p1 < alfa y p2 < alfa).

Via 2 -- IC 90% bootstrap de la diferencia de medianas (sistema-eh2,
  escala promedio_por_caso), 1000 replicas, semilla=42. 90% (no 95%)
  porque es el IC que corresponde a un TOST de alfa=0.05 por cola.
  Equivalencia solo si el IC90 completo cae dentro de [-0.5, +0.5].

Se reportan ambas vias aunque se contradigan. No se suaviza el
resultado si, con n=15, el IC90 resulta demasiado ancho para concluir
equivalencia."""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CALIF = ROOT / "calificaciones.csv"
DECODE = ROOT / "decode.json"
EVALUADORES = REPO_ROOT / "panel_evaluacion" / "datos" / "evaluadores.json"

ALFA = 0.05
MARGEN_AVG = 0.5          # escala promedio_por_caso, congelado en decisiones_analisis.md
MARGEN_SUMA = 1.5         # MARGEN_AVG * 3, exacto en float64
SEMILLA = 42
CRITERIOS = ("relevancia", "viabilidad")
CASOS = list(range(1, 16))


def cargar_acumulador():
    with open(DECODE, encoding="utf-8") as f:
        decode = json.load(f)
    with open(EVALUADORES, encoding="utf-8") as f:
        evaluadores_meta = json.load(f)
    token_a_evaluador = {t: m["evaluador_id"] for t, m in evaluadores_meta.items() if not m["es_prueba"]}
    evaluador_a_token = {v: k for k, v in token_a_evaluador.items()}

    with open(CALIF, newline="", encoding="utf-8") as f:
        filas_calif = list(csv.DictReader(f))

    acumulador = defaultdict(list)
    for r in filas_calif:
        token = evaluador_a_token[r["evaluador"]]
        fuente = decode[token][r["id_caso"]][r["etiqueta"]]
        acumulador[(int(r["id_caso"]), fuente, r["criterio"])].append(int(r["puntaje"]))
    for k, v in acumulador.items():
        assert len(v) == 3, f"{k} no tiene 3 puntajes: {v}"
    return acumulador


ACUMULADOR = cargar_acumulador()


def sumas_enteras(criterio: str) -> np.ndarray:
    """diff = suma_sistema - suma_eh2, entera, 15 casos."""
    suma_sistema = np.array([sum(ACUMULADOR[(c, "sistema", criterio)]) for c in CASOS], dtype=np.float64)
    suma_eh2 = np.array([sum(ACUMULADOR[(c, "eh2", criterio)]) for c in CASOS], dtype=np.float64)
    return suma_sistema - suma_eh2


def tost_wilcoxon(diffs: np.ndarray):
    """Dos Wilcoxon de una cola, correccion de Pratt, escala suma entera."""
    p1 = wilcoxon(diffs + MARGEN_SUMA, zero_method="pratt", alternative="greater", method="auto").pvalue
    p2 = wilcoxon(diffs - MARGEN_SUMA, zero_method="pratt", alternative="less", method="auto").pvalue
    return float(p1), float(p2)


def bootstrap_ic90(criterio: str, n_rep=1000, seed=SEMILLA):
    sistema_avg = np.array([sum(ACUMULADOR[(c, "sistema", criterio)]) / 3.0 for c in CASOS])
    eh2_avg = np.array([sum(ACUMULADOR[(c, "eh2", criterio)]) / 3.0 for c in CASOS])
    rng = np.random.default_rng(seed)
    n = len(CASOS)
    diffs_medianas = np.empty(n_rep)
    for b in range(n_rep):
        idx = rng.integers(0, n, size=n)
        diffs_medianas[b] = np.median(sistema_avg[idx]) - np.median(eh2_avg[idx])
    lo, hi = np.percentile(diffs_medianas, [5, 95])
    mediana_puntual = float(np.median(sistema_avg) - np.median(eh2_avg))
    return mediana_puntual, float(lo), float(hi)


print("=" * 70)
print(f"PASO 7 -- TOST de equivalencia, margen +-{MARGEN_AVG} (escala promedio_por_caso), alfa={ALFA}")
print("=" * 70)

resultados = {}
for criterio in CRITERIOS:
    print(f"\n--- {criterio} ---")
    diffs = sumas_enteras(criterio)

    print("\n  Via 1: TOST por dos Wilcoxon de una cola (Pratt, escala suma entera)")
    p1, p2 = tost_wilcoxon(diffs)
    rechaza_h01 = p1 < ALFA
    rechaza_h02 = p2 < ALFA
    equivalencia_via1 = rechaza_h01 and rechaza_h02
    print(f"    H01: mediana(diff) <= -{MARGEN_AVG}  vs  > -{MARGEN_AVG}   -> p = {p1:.6f}  ({'rechaza H01' if rechaza_h01 else 'NO rechaza H01'} a alfa={ALFA})")
    print(f"    H02: mediana(diff) >= +{MARGEN_AVG}  vs  < +{MARGEN_AVG}   -> p = {p2:.6f}  ({'rechaza H02' if rechaza_h02 else 'NO rechaza H02'} a alfa={ALFA})")
    print(f"    Conclusion via 1: {'EQUIVALENCIA' if equivalencia_via1 else 'NO se concluye equivalencia'} (se requieren ambas H0 rechazadas)")

    print("\n  Via 2: IC90% bootstrap de la diferencia de medianas (1000 replicas, semilla=42)")
    mediana_puntual, lo, hi = bootstrap_ic90(criterio)
    contenido = (lo >= -MARGEN_AVG) and (hi <= MARGEN_AVG)
    print(f"    diferencia de medianas (sistema-eh2) = {mediana_puntual:.4f}")
    print(f"    IC90% (percentil): [{lo:.4f}, {hi:.4f}]")
    print(f"    Conclusion via 2: {'EQUIVALENCIA' if contenido else 'NO se concluye equivalencia'} "
          f"(IC90 {'contenido en' if contenido else 'NO contenido en'} [-{MARGEN_AVG}, +{MARGEN_AVG}])")
    if not contenido:
        ancho = hi - lo
        print(f"    IC90 de ancho {ancho:.4f} excede el margen de equivalencia (+-{MARGEN_AVG} = ancho {2*MARGEN_AVG}).")
        print(f"    Con n=15 el intervalo es demasiado ancho para concluir equivalencia. No se suaviza este resultado.")

    if equivalencia_via1 != contenido:
        print(f"\n  *** Las dos vias se CONTRADICEN para {criterio}: via1={'equivalencia' if equivalencia_via1 else 'no equivalencia'}, "
              f"via2={'equivalencia' if contenido else 'no equivalencia'}. Se reportan ambas, sin resolver la contradiccion a favor de ninguna.")

    resultados[criterio] = dict(
        p_h01=p1, p_h02=p2, equivalencia_via1=equivalencia_via1,
        mediana_diff=mediana_puntual, ic90_lo=lo, ic90_hi=hi, equivalencia_via2=contenido,
    )

print("\n" + "=" * 70)
print("RESUMEN PASO 7")
print("=" * 70)
for criterio in CRITERIOS:
    r = resultados[criterio]
    print(f"  {criterio}: via1={'EQUIVALENCIA' if r['equivalencia_via1'] else 'no equivalencia'} "
          f"(p_H01={r['p_h01']:.4f}, p_H02={r['p_h02']:.4f})  |  "
          f"via2={'EQUIVALENCIA' if r['equivalencia_via2'] else 'no equivalencia'} "
          f"(IC90=[{r['ic90_lo']:.4f}, {r['ic90_hi']:.4f}])")

print("\nPASO 7 completo.")
