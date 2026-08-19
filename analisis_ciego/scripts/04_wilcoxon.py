"""PASO 5 -- Wilcoxon pareado (zero_method=pratt), efecto, bootstrap CI,
y verificaciones de robustez (descriptivas, sin correccion por comparaciones
multiples: no son hipotesis, son verificaciones).

BUGFIX (rehecho): las diferencias se calculaban sobre promedios en float
(suma_de_3_evaluadores / 3), y 1/3 no es exacto en binario. Dos diferencias
matematicamente iguales (p.ej. exactamente 1.0) podian llegar a Wilcoxon
como 0.9999999999999991 y 1.0000000000000018 -- valores distintos en float
aunque identicos en magnitud -- y la correccion de Pratt les asignaba
rangos distintos en vez de un rango promediado (ruido numerico).

Fix: se trabaja con la SUMA entera de los 3 puntajes por evaluador (sin
dividir entre 3). Wilcoxon es invariante a un reescalado positivo comun
(multiplicar todo por 3 no cambia signos ni el orden de |diff|), asi que
usar la suma en vez del promedio da el mismo resultado estadistico, pero
en enteros exactos: cero perdida de precision, cero empates espurios."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CALIF = ROOT / "calificaciones.csv"
DECODE = ROOT / "decode.json"
EVALUADORES = REPO_ROOT / "panel_evaluacion" / "datos" / "evaluadores.json"
RECOMENDACIONES = REPO_ROOT / "camino_b" / "resultados" / "recomendaciones_ia.csv"

SEMILLA = 42
CRITERIOS = ("relevancia", "viabilidad")
CASOS = list(range(1, 16))


def cargar_acumulador():
    """(id_caso, fuente, criterio) -> lista de 3 puntajes enteros (uno por evaluador)."""
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
    return acumulador, evaluador_a_token, decode


ACUMULADOR, EVALUADOR_A_TOKEN, DECODE = cargar_acumulador()


def sumas_enteras(casos: list[int], criterio: str) -> tuple[np.ndarray, np.ndarray]:
    """Suma entera (no promedio) de los 3 puntajes por caso, para sistema y eh2."""
    suma_sistema = np.array([sum(ACUMULADOR[(c, "sistema", criterio)]) for c in casos], dtype=np.int64)
    suma_eh2 = np.array([sum(ACUMULADOR[(c, "eh2", criterio)]) for c in casos], dtype=np.int64)
    return suma_sistema, suma_eh2


def rank_biserial_pratt(diffs: np.ndarray) -> tuple[float, float, float]:
    """R+, R-, r_rb usando ranking de Pratt: se rankean |d| de TODOS los
    pares (incluidos los ceros), con promedio de rangos en empates; los
    rangos de los ceros no se suman a R+ ni a R-.

    Los diffs deben venir de una escala EXACTA (enteros o floats sin error
    de redondeo acumulado) para que la comparacion de igualdad de magnitudes
    sea confiable."""
    abs_d = np.abs(diffs)
    n = len(diffs)
    orden = np.argsort(abs_d, kind="mergesort")
    rangos = np.empty(n)
    valores_ordenados = abs_d[orden]
    elementos_en_grupos_empatados = 0
    i = 0
    r = 1
    while i < n:
        j = i
        while j < n and valores_ordenados[j] == valores_ordenados[i]:
            j += 1
        tam_grupo = j - i
        if tam_grupo > 1:
            elementos_en_grupos_empatados += tam_grupo
        rango_promedio = (r + (r + tam_grupo - 1)) / 2
        rangos[orden[i:j]] = rango_promedio
        r += tam_grupo
        i = j

    # Assert: el conteo de elementos en grupos de rango empatado (via el
    # barrido de ranking) debe coincidir con el conteo de elementos que
    # pertenecen a una magnitud repetida (via Counter independiente).
    conteo_magnitudes = Counter(abs_d.tolist())
    elementos_en_magnitudes_repetidas = sum(cnt for cnt in conteo_magnitudes.values() if cnt > 1)
    assert elementos_en_grupos_empatados == elementos_en_magnitudes_repetidas, (
        f"Inconsistencia de empates: ranking agrupo {elementos_en_grupos_empatados} elementos, "
        f"pero Counter independiente encuentra {elementos_en_magnitudes_repetidas} elementos "
        f"en magnitudes repetidas."
    )

    r_pos = rangos[diffs > 0].sum()
    r_neg = rangos[diffs < 0].sum()
    denom = r_pos + r_neg
    r_rb = (r_pos - r_neg) / denom if denom > 0 else float("nan")
    return r_pos, r_neg, r_rb


def bootstrap_ci_diferencia_medianas(casos: list[int], criterio: str, n_rep=1000, seed=SEMILLA):
    """IC 95% por bootstrap de la diferencia de medianas (sistema - eh2),
    en escala de puntaje promedio por caso (suma/3), remuestreando casos
    con reemplazo y preservando el pareo."""
    sistema_avg = np.array([sum(ACUMULADOR[(c, "sistema", criterio)]) / 3.0 for c in casos])
    eh2_avg = np.array([sum(ACUMULADOR[(c, "eh2", criterio)]) / 3.0 for c in casos])
    rng = np.random.default_rng(seed)
    n = len(casos)
    diffs_medianas = np.empty(n_rep)
    for b in range(n_rep):
        idx = rng.integers(0, n, size=n)
        diffs_medianas[b] = np.median(sistema_avg[idx]) - np.median(eh2_avg[idx])
    lo, hi = np.percentile(diffs_medianas, [2.5, 97.5])
    mediana_diff_puntual = float(np.median(sistema_avg) - np.median(eh2_avg))
    return mediana_diff_puntual, lo, hi


def correr_wilcoxon(suma_sistema: np.ndarray, suma_eh2: np.ndarray, etiqueta: str):
    diffs = suma_sistema.astype(np.float64) - suma_eh2.astype(np.float64)  # enteros exactos en float64
    n_empates = int((diffs == 0).sum())
    res = wilcoxon(diffs, zero_method="pratt", alternative="two-sided", method="auto")
    r_pos, r_neg, r_rb = rank_biserial_pratt(diffs)
    print(f"  [{etiqueta}] n={len(diffs)}  empates={n_empates}")
    print(f"    W (min de rangos +/-) = {res.statistic:.4f}   p-valor = {res.pvalue:.6f}")
    print(f"    R+ = {r_pos:.2f}   R- = {r_neg:.2f}   r_rb (correlacion biserial de rangos pareados) = {r_rb:.4f}")
    return dict(n=len(diffs), empates=n_empates, statistic=float(res.statistic), pvalue=float(res.pvalue), r_rb=float(r_rb))


# =====================================================================
# PRINCIPAL: 15 casos, suma entera de 3 evaluadores (equivalente exacto
# del promedio_por_caso fijado en decisiones_analisis.md; Wilcoxon es
# invariante a la escala x3)
# =====================================================================
print("=" * 70)
print("PRINCIPAL -- 15 casos, suma entera de 3 evaluadores (== promedio_por_caso x3)")
print("=" * 70)

resultados_principales = {}
for criterio in CRITERIOS:
    print(f"\n--- {criterio} ---")
    suma_sistema, suma_eh2 = sumas_enteras(CASOS, criterio)
    resultados_principales[criterio] = correr_wilcoxon(suma_sistema, suma_eh2, "principal, 15 casos")

    mediana_diff, lo, hi = bootstrap_ci_diferencia_medianas(CASOS, criterio)
    print(f"    Bootstrap 1000 replicas, semilla={SEMILLA}: diferencia de medianas (sistema-eh2, escala promedio/caso) = {mediana_diff:.4f}")
    print(f"    IC 95% (percentil): [{lo:.4f}, {hi:.4f}]")
    resultados_principales[criterio]["mediana_diff"] = mediana_diff
    resultados_principales[criterio]["ic95_lo"] = float(lo)
    resultados_principales[criterio]["ic95_hi"] = float(hi)

# =====================================================================
# ROBUSTEZ (descriptiva, NO son pruebas de hipotesis adicionales;
# no se corrige por comparaciones multiples)
# =====================================================================
print("\n" + "=" * 70)
print("ROBUSTEZ -- descriptiva, no son hipotesis adicionales,")
print("NO se corrige por comparaciones multiples (verificaciones, no pruebas)")
print("=" * 70)

# --- (a) mismo contraste por evaluador, sin promediar (ya son enteros,
#         no habia bug aqui -- se recalcula igual por completitud) ---
print("\n(a) Mismo contraste por evaluador (sin promediar, 15 casos c/u):")
for criterio in CRITERIOS:
    print(f"\n  === {criterio} ===")
    for ev in sorted(EVALUADOR_A_TOKEN):
        token = EVALUADOR_A_TOKEN[ev]
        mapa = DECODE[token]
        por_fuente = {"sistema": {}, "eh2": {}}
        with open(CALIF, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["evaluador"] != ev or r["criterio"] != criterio:
                    continue
                fuente = mapa[r["id_caso"]][r["etiqueta"]]
                por_fuente[fuente][int(r["id_caso"])] = int(r["puntaje"])
        sistema = np.array([por_fuente["sistema"][c] for c in CASOS], dtype=np.float64)
        eh2 = np.array([por_fuente["eh2"][c] for c in CASOS], dtype=np.float64)
        correr_wilcoxon(sistema, eh2, f"{ev}")

# --- (b) excluyendo los 3 casos con revision_manual=True ---
with open(RECOMENDACIONES, newline="", encoding="utf-8") as f:
    filas_reco = list(csv.DictReader(f))
casos_revision_manual = {int(r["id_caso"]) for r in filas_reco if r["revision_manual"] == "True"}
casos_sin_revision = [c for c in CASOS if c not in casos_revision_manual]
print(f"\n(b) Excluyendo casos con revision_manual=True: {sorted(casos_revision_manual)} (n excluidos={len(casos_revision_manual)})")
for criterio in CRITERIOS:
    print(f"\n  === {criterio} (n={len(casos_sin_revision)}) ===")
    suma_sistema, suma_eh2 = sumas_enteras(casos_sin_revision, criterio)
    correr_wilcoxon(suma_sistema, suma_eh2, f"sin revision_manual, {criterio}")

# --- (c) excluyendo casos marcados identifica_origen en PASO 2 ---
# clasificacion_cegado.md (PASO 2): identifica_origen = 0, sospecha_ambigua = 0
# -> no hay casos que excluir; el conjunto es identico al principal.
print("\n(c) Excluyendo casos marcados identifica_origen en PASO 2:")
print("    clasificacion_cegado.md reporta identifica_origen=0, sospecha_ambigua=0.")
print("    No hay casos que excluir -> resultado identico al PRINCIPAL (no se re-corre).")

print("\nPASO 5 completo (rehecho).")
