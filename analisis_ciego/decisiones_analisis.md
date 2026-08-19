# Decisiones de análisis — estudio ciego
# Congeladas el: 17/08/2026
# Firmado: Luis Guzmán, Alex Ibarra

UNIDAD_ANALISIS  = promedio_por_caso    # 15 pares, no 45. Los 3 evaluadores
                                        # califican los mismos casos: no hay
                                        # independencia para tratarlos como 45
EMPATES          = pratt                # corrección de Pratt, no descartar
ICC_MODELO       = dos_vias_aleatorio   # los 3 evaluadores son una muestra
ICC_TIPO         = acuerdo_absoluto     # no consistencia
ICC_REPORTAR     = ICC(2,1) e ICC(2,k), ambos con IC95
REVISION_MANUAL  = incluir              # los 3 casos borde entran en el
                                        # análisis principal + sensibilidad
MARGEN_TOST      = 0,5 puntos Likert
SEMILLA          = 42

# Estas ocho decisiones no se modifican después de ver ningún resultado.