"""PASO 3 -- Abrir el decode, verificar cobertura y balance A/B, construir
tabla pareada (15 casos x fuente x criterio, promedio de 3 evaluadores)."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CALIF = ROOT / "calificaciones.csv"
DECODE = ROOT / "decode.json"
EVALUADORES = REPO_ROOT / "panel_evaluacion" / "datos" / "evaluadores.json"

with open(DECODE, encoding="utf-8") as f:
    decode = json.load(f)
with open(EVALUADORES, encoding="utf-8") as f:
    evaluadores_meta = json.load(f)

# --- Token -> evaluador_id (solo los 3 reales; excluir es_prueba) ---
token_a_evaluador = {}
for token, meta in evaluadores_meta.items():
    if not meta["es_prueba"]:
        token_a_evaluador[token] = meta["evaluador_id"]

evaluador_a_token = {v: k for k, v in token_a_evaluador.items()}
print(f"Tokens reales en evaluadores.json: {len(token_a_evaluador)} -> {sorted(token_a_evaluador.values())}")
print(f"Tokens totales en decode.json: {len(decode)} (incluye token de prueba, se descarta)")

tokens_prueba = set(decode.keys()) - set(token_a_evaluador.keys())
print(f"Tokens en decode.json que NO son de evaluador real (prueba): {len(tokens_prueba)}")

# --- Cobertura: 15 casos x 3 evaluadores ---
CASOS = [str(i) for i in range(1, 16)]
problemas_cobertura = []
for ev, token in evaluador_a_token.items():
    mapa = decode.get(token)
    if mapa is None:
        problemas_cobertura.append(f"{ev}: token {token} no esta en decode.json")
        continue
    faltantes = [c for c in CASOS if c not in mapa]
    if faltantes:
        problemas_cobertura.append(f"{ev}: faltan casos {faltantes}")
    for c in CASOS:
        par = mapa.get(c, {})
        valores = {par.get("A"), par.get("B")}
        if valores != {"sistema", "eh2"}:
            problemas_cobertura.append(f"{ev} caso {c}: par invalido {par}")

if problemas_cobertura:
    print("PROBLEMAS DE COBERTURA:")
    for p in problemas_cobertura:
        print(f"  {p}")
else:
    print("Cobertura OK: decode.json cubre los 15 casos para los 3 evaluadores reales, pares {A,B}={sistema,eh2} completos.")

# --- Balance real A/B por evaluador ---
print("\nBalance real de asignacion A/B por evaluador (cuantos de los 15 casos tuvieron sistema=A):")
for ev, token in sorted(evaluador_a_token.items()):
    mapa = decode[token]
    sistema_es_a = sum(1 for c in CASOS if mapa[c]["A"] == "sistema")
    eh2_es_a = 15 - sistema_es_a
    print(f"  {ev}: sistema=A en {sistema_es_a}/15 casos, eh2=A en {eh2_es_a}/15 casos")

# --- Cargar calificaciones y traducir etiqueta -> fuente ---
with open(CALIF, newline="", encoding="utf-8") as f:
    filas = list(csv.DictReader(f))

# acumulador[(id_caso, fuente, criterio)] = lista de puntajes (uno por evaluador)
acumulador = defaultdict(list)
errores_traduccion = []
for r in filas:
    ev = r["evaluador"]
    token = evaluador_a_token.get(ev)
    if token is None:
        errores_traduccion.append(f"evaluador desconocido en calificaciones.csv: {ev}")
        continue
    mapa_caso = decode[token].get(r["id_caso"])
    if mapa_caso is None:
        errores_traduccion.append(f"{ev} caso {r['id_caso']}: sin entrada en decode")
        continue
    fuente = mapa_caso[r["etiqueta"]]
    acumulador[(int(r["id_caso"]), fuente, r["criterio"])].append(int(r["puntaje"]))

if errores_traduccion:
    print("\nERRORES DE TRADUCCION:")
    for e in errores_traduccion:
        print(f"  {e}")

# --- Verificar 3 puntajes por celda (uno por evaluador) ---
faltan_3 = [k for k, v in acumulador.items() if len(v) != 3]
if faltan_3:
    print(f"\nCeldas sin exactamente 3 puntajes (uno por evaluador): {len(faltan_3)}")
    for k in faltan_3:
        print(f"  {k}: {acumulador[k]}")
else:
    print("\nOK: cada (caso, fuente, criterio) tiene exactamente 3 puntajes (uno por evaluador).")

# --- Tabla pareada: 15 filas, promedio de 3 evaluadores por fuente y criterio ---
print("\nTabla pareada completa (promedio de 3 evaluadores, 15 filas):")
header = f"{'caso':>4} | {'sistema_relevancia':>18} | {'eh2_relevancia':>15} | {'sistema_viabilidad':>18} | {'eh2_viabilidad':>15}"
print(header)
print("-" * len(header))
tabla = []
for caso in range(1, 16):
    fila = {"caso": caso}
    for fuente in ("sistema", "eh2"):
        for criterio in ("relevancia", "viabilidad"):
            vals = acumulador[(caso, fuente, criterio)]
            fila[f"{fuente}_{criterio}"] = sum(vals) / len(vals)
    tabla.append(fila)
    print(
        f"{fila['caso']:>4} | {fila['sistema_relevancia']:>18.4f} | {fila['eh2_relevancia']:>15.4f} | "
        f"{fila['sistema_viabilidad']:>18.4f} | {fila['eh2_viabilidad']:>15.4f}"
    )

assert len(tabla) == 15, "la tabla pareada debe tener 15 filas"

# Guardar para pasos posteriores
out = ROOT / "scripts" / "_tabla_pareada.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(tabla, f, indent=2, ensure_ascii=False)
print(f"\nGuardado: {out}")
print("\nPASO 3 completo.")
