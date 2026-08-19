"""PASO 6 -- Concordancia entre evaluadores.
ICC(2,1) e ICC(2,k): dos vias, efectos aleatorios, acuerdo absoluto.
Por separado para relevancia y viabilidad.

Unidad de sujeto: igual que UNIDAD_ANALISIS en decisiones_analisis.md
(promedio_por_caso) -- para cada evaluador y caso, se promedia lo que ese
evaluador califico como A y como B (sin decodificar sistema/eh2: es la
calificacion global del evaluador para ese caso). n=15 sujetos, k=3
evaluadores (raters).

Formulas de Shrout & Fleiss (1979) / McGraw & Wong (1996), calculadas por
pingouin.intraclass_corr (paquete instalado para este paso: no estaba
disponible en el entorno, se instalo via pip)."""
import csv
from pathlib import Path

import pandas as pd
import pingouin as pg

ROOT = Path(__file__).resolve().parent.parent
CALIF = ROOT / "calificaciones.csv"
CRITERIOS = ("relevancia", "viabilidad")

with open(CALIF, newline="", encoding="utf-8") as f:
    filas = list(csv.DictReader(f))

for criterio in CRITERIOS:
    print("=" * 70)
    print(f"ICC -- {criterio}")
    print("=" * 70)

    # (caso, evaluador) -> [puntaje_A, puntaje_B]
    acumulador = {}
    for r in filas:
        if r["criterio"] != criterio:
            continue
        clave = (int(r["id_caso"]), r["evaluador"])
        acumulador.setdefault(clave, {})[r["etiqueta"]] = int(r["puntaje"])

    registros = []
    for (caso, evaluador), pares in acumulador.items():
        assert set(pares.keys()) == {"A", "B"}, f"{caso},{evaluador}: {pares}"
        valor = (pares["A"] + pares["B"]) / 2.0
        registros.append(dict(caso=caso, evaluador=evaluador, valor=valor))

    df = pd.DataFrame(registros)
    n_sujetos = df["caso"].nunique()
    n_raters = df["evaluador"].nunique()
    assert n_sujetos == 15, f"esperaba 15 casos, hay {n_sujetos}"
    assert n_raters == 3, f"esperaba 3 evaluadores, hay {n_raters}"
    assert len(df) == 45, f"esperaba 15x3=45 filas, hay {len(df)}"

    icc = pg.intraclass_corr(data=df, targets="caso", raters="evaluador", ratings="valor")
    icc = icc.set_index("Type")

    # pingouin 0.6.1 nombra Shrout-Fleiss ICC(2,1)/ICC(2,k) como ICC(A,1)/ICC(A,k)
    # ("A" = absolute agreement, dos vias efectos aleatorios).
    fila_211 = icc.loc["ICC(A,1)"]
    fila_21k = icc.loc["ICC(A,k)"]

    print(f"\nn sujetos (casos) = {n_sujetos}, k raters (evaluadores) = {n_raters}")
    print(f"\nICC(2,1) [pingouin: ICC(A,1)] -- dos vias, efectos aleatorios, acuerdo absoluto, un solo rater")
    print(f"  ICC = {fila_211['ICC']:.4f}   IC95% = {fila_211['CI95']}   F({fila_211['df1']},{fila_211['df2']})={fila_211['F']:.4f}  p={fila_211['pval']:.6f}")
    print(f"\nICC(2,k) [pingouin: ICC(A,k)] -- dos vias, efectos aleatorios, acuerdo absoluto, promedio de {n_raters} raters")
    print(f"  ICC = {fila_21k['ICC']:.4f}   IC95% = {fila_21k['CI95']}   F({fila_21k['df1']},{fila_21k['df2']})={fila_21k['F']:.4f}  p={fila_21k['pval']:.6f}")
    print()

print("PASO 6 completo.")
