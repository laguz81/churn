"""Diagnostico adicional (post-hoc a PASO 6, agregado tras ver el ICC de
acuerdo absoluto) -- ICC(C,1) e ICC(C,k): dos vias, efectos aleatorios,
CONSISTENCIA (no acuerdo absoluto).

Es descriptivo. NO reemplaza el ICC de acuerdo absoluto congelado en
decisiones_analisis.md (ICC_TIPO = acuerdo_absoluto) -- ese sigue siendo
el resultado principal de PASO 6.

Motivo: si el ICC de consistencia sale bastante mas alto que el de
acuerdo absoluto, el problema es sesgo de nivel entre evaluadores (ya
registrado como hallazgo de PASO 1: modas 5/4/2, evaluador_1 nunca uso 4)
y no desacuerdo sobre el ordenamiento relativo de los casos.

Misma unidad de sujeto que PASO 6: promedio_por_caso, sin decodificar
sistema/eh2 (promedio de lo que cada evaluador califico como A y como B).
n=15 sujetos, k=3 evaluadores."""
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
    print(f"ICC de CONSISTENCIA (diagnostico) -- {criterio}")
    print("=" * 70)

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
    assert df["caso"].nunique() == 15
    assert df["evaluador"].nunique() == 3
    assert len(df) == 45

    icc = pg.intraclass_corr(data=df, targets="caso", raters="evaluador", ratings="valor").set_index("Type")
    fila_c1 = icc.loc["ICC(C,1)"]
    fila_ck = icc.loc["ICC(C,k)"]
    fila_a1 = icc.loc["ICC(A,1)"]  # ya reportado en PASO 6, se repite aqui solo para comparar
    fila_ak = icc.loc["ICC(A,k)"]

    print(f"\nICC(C,1) -- dos vias, efectos aleatorios, CONSISTENCIA, un solo rater")
    print(f"  ICC = {fila_c1['ICC']:.4f}   IC95% = {fila_c1['CI95']}   F({fila_c1['df1']},{fila_c1['df2']})={fila_c1['F']:.4f}  p={fila_c1['pval']:.6f}")
    print(f"\nICC(C,k) -- dos vias, efectos aleatorios, CONSISTENCIA, promedio de 3 raters")
    print(f"  ICC = {fila_ck['ICC']:.4f}   IC95% = {fila_ck['CI95']}   F({fila_ck['df1']},{fila_ck['df2']})={fila_ck['F']:.4f}  p={fila_ck['pval']:.6f}")

    print(f"\n  Comparacion con PASO 6 (acuerdo absoluto, ya reportado):")
    print(f"    ICC(2,1) absoluto={fila_a1['ICC']:.4f}  vs  ICC(C,1) consistencia={fila_c1['ICC']:.4f}   delta={fila_c1['ICC']-fila_a1['ICC']:+.4f}")
    print(f"    ICC(2,k) absoluto={fila_ak['ICC']:.4f}  vs  ICC(C,k) consistencia={fila_ck['ICC']:.4f}   delta={fila_ck['ICC']-fila_ak['ICC']:+.4f}")
    print()

print("Diagnostico de consistencia completo. No reemplaza el resultado de PASO 6.")
