from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


METODO_PROMEDIO_SIMPLE = "promedio_simple"
METODO_PROMEDIO_PONDERADO = "promedio_ponderado"
METODO_MEDIANA = "mediana"
METODO_PROMEDIO_ROBUSTO = "promedio_ponderado_robusto"
METODO_TENDENCIA = "tendencia_lineal"

METODOS_CANDIDATOS: tuple[str, ...] = (
    METODO_PROMEDIO_SIMPLE,
    METODO_PROMEDIO_PONDERADO,
    METODO_MEDIANA,
    METODO_PROMEDIO_ROBUSTO,
    METODO_TENDENCIA,
)

COLUMNAS_CONSUMO_REQUERIDAS: set[str] = {
    "sucursal",
    "ingrediente_id",
    "semana",
    "consumo_unidad_base",
}

UMBRAL_MAD = 3.5
UMBRAL_R2_TENDENCIA = 0.85
UMBRAL_PENDIENTE_RELATIVA = 0.025
UMBRAL_CONSISTENCIA_TENDENCIA = 0.75
TOLERANCIA_MODELO_SIMPLE = 0.05
TOLERANCIA_TENDENCIA = 0.10


class ErrorProyeccion(Exception):
    """Error controlado al calcular una proyección de consumo."""


@dataclass(frozen=True)
class ResultadoProyeccion:
    consumo_proyectado: float
    metodo: str
    explicacion: str
    semanas_usadas: int
    cantidad_atipicos: int
    semanas_atipicas: tuple[str, ...]
    mae_backtest: float
    wape_backtest_pct: float
    pendiente_semanal: float
    r2_tendencia: float


def _convertir_valores(valores: Iterable[float]) -> np.ndarray:
    arreglo = np.asarray(list(valores), dtype=float)

    if arreglo.ndim != 1:
        raise ErrorProyeccion("La serie de consumo debe ser unidimensional.")

    if len(arreglo) < 3:
        raise ErrorProyeccion(
            "Se requieren al menos 3 semanas para proyectar el consumo."
        )

    if not np.isfinite(arreglo).all():
        raise ErrorProyeccion(
            "La serie contiene valores vacíos, infinitos o no numéricos."
        )

    if (arreglo < 0).any():
        raise ErrorProyeccion(
            "La serie contiene consumos negativos y no puede proyectarse."
        )

    return arreglo


def detectar_atipicos_mad(
    valores: Iterable[float],
    umbral: float = UMBRAL_MAD,
) -> np.ndarray:
    """Devuelve una máscara booleana de valores atípicos usando MAD."""
    arreglo = _convertir_valores(valores)
    mediana = float(np.median(arreglo))
    desviacion_absoluta = np.abs(arreglo - mediana)
    mad = float(np.median(desviacion_absoluta))

    if mad > 1e-12:
        puntajes_modificados = 0.6745 * (arreglo - mediana) / mad
        return np.abs(puntajes_modificados) > umbral

    q1, q3 = np.percentile(arreglo, [25, 75])
    rango_intercuartil = float(q3 - q1)

    if rango_intercuartil <= 1e-12:
        return np.zeros(len(arreglo), dtype=bool)

    limite_inferior = q1 - 1.5 * rango_intercuartil
    limite_superior = q3 + 1.5 * rango_intercuartil

    return (arreglo < limite_inferior) | (arreglo > limite_superior)


def _datos_limpios(
    valores: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    posiciones = np.arange(1, len(valores) + 1, dtype=float)
    mascara_atipicos = detectar_atipicos_mad(valores)
    valores_limpios = valores[~mascara_atipicos]
    posiciones_limpias = posiciones[~mascara_atipicos]

    if len(valores_limpios) < 2:
        return valores, posiciones, np.zeros(len(valores), dtype=bool)

    return valores_limpios, posiciones_limpias, mascara_atipicos


def _pronosticar_metodo(
    valores: Sequence[float] | np.ndarray,
    metodo: str,
) -> float:
    arreglo = _convertir_valores(valores)
    posiciones = np.arange(1, len(arreglo) + 1, dtype=float)

    if metodo == METODO_PROMEDIO_SIMPLE:
        proyeccion = float(np.mean(arreglo))

    elif metodo == METODO_PROMEDIO_PONDERADO:
        proyeccion = float(np.average(arreglo, weights=posiciones))

    elif metodo == METODO_MEDIANA:
        proyeccion = float(np.median(arreglo))

    elif metodo == METODO_PROMEDIO_ROBUSTO:
        valores_limpios, posiciones_limpias, _ = _datos_limpios(arreglo)
        proyeccion = float(
            np.average(valores_limpios, weights=posiciones_limpias)
        )

    elif metodo == METODO_TENDENCIA:
        valores_limpios, posiciones_limpias, _ = _datos_limpios(arreglo)
        pendiente, intercepto = np.polyfit(
            posiciones_limpias,
            valores_limpios,
            deg=1,
        )
        proyeccion = float(
            pendiente * (len(arreglo) + 1) + intercepto
        )

    else:
        raise ErrorProyeccion(f"Método de proyección desconocido: {metodo}")

    return max(0.0, proyeccion)


def _metricas_backtest(
    valores: np.ndarray,
    metodo: str,
) -> tuple[float, float]:
    errores_absolutos: list[float] = []
    valores_reales: list[float] = []

    for indice_objetivo in range(3, len(valores)):
        entrenamiento = valores[:indice_objetivo]
        valor_real = float(valores[indice_objetivo])
        proyeccion = _pronosticar_metodo(entrenamiento, metodo)

        errores_absolutos.append(abs(proyeccion - valor_real))
        valores_reales.append(abs(valor_real))

    if not errores_absolutos:
        return float("nan"), float("nan")

    mae = float(np.mean(errores_absolutos))
    suma_reales = float(np.sum(valores_reales))
    wape = (
        float(np.sum(errores_absolutos) / suma_reales * 100)
        if suma_reales > 0
        else 0.0
    )

    return mae, wape


def _estadisticas_tendencia(
    valores: np.ndarray,
) -> tuple[float, float, float, bool]:
    valores_limpios, posiciones_limpias, _ = _datos_limpios(valores)

    pendiente, intercepto = np.polyfit(
        posiciones_limpias,
        valores_limpios,
        deg=1,
    )
    ajustados = pendiente * posiciones_limpias + intercepto

    suma_residuos = float(np.sum((valores_limpios - ajustados) ** 2))
    suma_total = float(
        np.sum((valores_limpios - np.mean(valores_limpios)) ** 2)
    )
    r2 = 1.0 - suma_residuos / suma_total if suma_total > 1e-12 else 0.0

    media_limpia = abs(float(np.mean(valores_limpios)))
    pendiente_relativa = (
        abs(float(pendiente)) / media_limpia
        if media_limpia > 1e-12
        else 0.0
    )

    diferencias = np.diff(valores_limpios)
    if pendiente > 0:
        consistencia = float(np.mean(diferencias > 0))
    elif pendiente < 0:
        consistencia = float(np.mean(diferencias < 0))
    else:
        consistencia = 0.0

    tendencia_fuerte = (
        r2 >= UMBRAL_R2_TENDENCIA
        and pendiente_relativa >= UMBRAL_PENDIENTE_RELATIVA
        and consistencia >= UMBRAL_CONSISTENCIA_TENDENCIA
    )

    return float(pendiente), float(r2), consistencia, tendencia_fuerte


def _seleccionar_metodo(
    valores: np.ndarray,
) -> tuple[str, dict[str, tuple[float, float]], bool]:
    metricas = {
        metodo: _metricas_backtest(valores, metodo)
        for metodo in METODOS_CANDIDATOS
    }

    mascara_atipicos = detectar_atipicos_mad(valores)
    _, _, _, tendencia_fuerte = _estadisticas_tendencia(valores)

    mae_robusto = metricas[METODO_PROMEDIO_ROBUSTO][0]
    mae_tendencia = metricas[METODO_TENDENCIA][0]

    if mascara_atipicos.any():
        if (
            tendencia_fuerte
            and np.isfinite(mae_tendencia)
            and (
                not np.isfinite(mae_robusto)
                or mae_tendencia <= mae_robusto * 1.05
            )
        ):
            return METODO_TENDENCIA, metricas, tendencia_fuerte

        return METODO_PROMEDIO_ROBUSTO, metricas, tendencia_fuerte

    metodos_base = (
        METODO_PROMEDIO_SIMPLE,
        METODO_PROMEDIO_PONDERADO,
        METODO_MEDIANA,
        METODO_PROMEDIO_ROBUSTO,
    )

    maes_base = {
        metodo: metricas[metodo][0]
        for metodo in metodos_base
    }
    mejor_base = min(
        maes_base,
        key=lambda metodo: (
            float("inf")
            if not np.isfinite(maes_base[metodo])
            else maes_base[metodo]
        ),
    )
    mejor_mae_base = maes_base[mejor_base]

    if (
        tendencia_fuerte
        and np.isfinite(mae_tendencia)
        and (
            not np.isfinite(mejor_mae_base)
            or mae_tendencia
            <= mejor_mae_base * (1 + TOLERANCIA_TENDENCIA)
        )
    ):
        return METODO_TENDENCIA, metricas, tendencia_fuerte

    orden_simplicidad = (
        METODO_PROMEDIO_SIMPLE,
        METODO_MEDIANA,
        METODO_PROMEDIO_PONDERADO,
        METODO_PROMEDIO_ROBUSTO,
    )

    if not np.isfinite(mejor_mae_base):
        return METODO_PROMEDIO_ROBUSTO, metricas, tendencia_fuerte

    limite_simplicidad = mejor_mae_base * (
        1 + TOLERANCIA_MODELO_SIMPLE
    )

    for metodo in orden_simplicidad:
        mae = maes_base[metodo]
        if np.isfinite(mae) and mae <= limite_simplicidad:
            return metodo, metricas, tendencia_fuerte

    return mejor_base, metricas, tendencia_fuerte


def _crear_explicacion(
    metodo: str,
    semanas_atipicas: tuple[str, ...],
    pendiente: float,
    r2: float,
    mae: float,
) -> str:
    mae_texto = f"{mae:.2f}" if np.isfinite(mae) else "no disponible"

    if metodo == METODO_TENDENCIA:
        direccion = "creciente" if pendiente > 0 else "decreciente"
        return (
            f"Tendencia {direccion} consistente: pendiente de "
            f"{pendiente:.2f} unidades por semana, R²={r2:.3f} y "
            f"MAE retrospectivo={mae_texto}."
        )

    if metodo == METODO_PROMEDIO_ROBUSTO and semanas_atipicas:
        semanas = ", ".join(semanas_atipicas)
        return (
            "Promedio ponderado robusto: se redujo la influencia de "
            f"{len(semanas_atipicas)} semana(s) atípica(s) ({semanas}) "
            f"y se dio más peso a las semanas recientes. MAE "
            f"retrospectivo={mae_texto}."
        )

    if metodo == METODO_PROMEDIO_PONDERADO:
        return (
            "Promedio ponderado: las semanas recientes reciben mayor "
            f"importancia. MAE retrospectivo={mae_texto}."
        )

    if metodo == METODO_MEDIANA:
        return (
            "Mediana histórica: representa el nivel central sin dejarse "
            f"dominar por variaciones puntuales. MAE retrospectivo={mae_texto}."
        )

    return (
        "Promedio simple: fue el método más parsimonioso dentro del margen "
        f"de error aceptado. MAE retrospectivo={mae_texto}."
    )


def proyectar_serie(
    valores: Iterable[float],
    etiquetas: Sequence[str] | None = None,
) -> ResultadoProyeccion:
    """Selecciona y ejecuta un método explicable para una serie."""
    arreglo = _convertir_valores(valores)

    if etiquetas is None:
        etiquetas_normalizadas = tuple(
            f"S{indice}" for indice in range(1, len(arreglo) + 1)
        )
    else:
        etiquetas_normalizadas = tuple(str(etiqueta) for etiqueta in etiquetas)

    if len(etiquetas_normalizadas) != len(arreglo):
        raise ErrorProyeccion(
            "La cantidad de etiquetas no coincide con la serie de consumo."
        )

    mascara_atipicos = detectar_atipicos_mad(arreglo)
    semanas_atipicas = tuple(
        etiqueta
        for etiqueta, es_atipica in zip(
            etiquetas_normalizadas,
            mascara_atipicos,
            strict=True,
        )
        if es_atipica
    )

    metodo, metricas, _ = _seleccionar_metodo(arreglo)
    consumo_proyectado = _pronosticar_metodo(arreglo, metodo)
    pendiente, r2, _, _ = _estadisticas_tendencia(arreglo)
    mae, wape = metricas[metodo]

    explicacion = _crear_explicacion(
        metodo=metodo,
        semanas_atipicas=semanas_atipicas,
        pendiente=pendiente,
        r2=r2,
        mae=mae,
    )

    return ResultadoProyeccion(
        consumo_proyectado=consumo_proyectado,
        metodo=metodo,
        explicacion=explicacion,
        semanas_usadas=len(arreglo),
        cantidad_atipicos=int(mascara_atipicos.sum()),
        semanas_atipicas=semanas_atipicas,
        mae_backtest=mae,
        wape_backtest_pct=wape,
        pendiente_semanal=pendiente,
        r2_tendencia=r2,
    )


def _extraer_numero_semana(serie: pd.Series) -> pd.Series:
    numeros = serie.astype(str).str.extract(r"(\d+)$", expand=False)

    if numeros.isna().any():
        etiquetas_invalidas = sorted(
            serie.loc[numeros.isna()].astype(str).unique().tolist()
        )
        raise ErrorProyeccion(
            "No se pudo determinar el orden de estas semanas: "
            + ", ".join(etiquetas_invalidas)
        )

    return numeros.astype(int)


def proyectar_consumo_historico(
    consumo_historico: pd.DataFrame,
) -> pd.DataFrame:
    """Proyecta cada combinación de sucursal e ingrediente."""
    faltantes = COLUMNAS_CONSUMO_REQUERIDAS - set(consumo_historico.columns)

    if faltantes:
        raise ErrorProyeccion(
            "Faltan columnas requeridas en consumo_historico: "
            + ", ".join(sorted(faltantes))
        )

    trabajo = consumo_historico.copy()
    trabajo["consumo_unidad_base"] = pd.to_numeric(
        trabajo["consumo_unidad_base"],
        errors="coerce",
    )

    if trabajo["consumo_unidad_base"].isna().any():
        raise ErrorProyeccion(
            "Existen consumos vacíos o no numéricos en el histórico."
        )

    if (trabajo["consumo_unidad_base"] < 0).any():
        raise ErrorProyeccion(
            "Existen consumos negativos en el histórico."
        )

    if trabajo.duplicated(
        subset=["sucursal", "ingrediente_id", "semana"],
        keep=False,
    ).any():
        raise ErrorProyeccion(
            "Existen semanas duplicadas para una sucursal e ingrediente."
        )

    trabajo["_orden_semana"] = _extraer_numero_semana(trabajo["semana"])
    trabajo = trabajo.sort_values(
        ["sucursal", "ingrediente_id", "_orden_semana"]
    )

    resultados: list[dict[str, object]] = []

    for (sucursal, ingrediente_id), grupo in trabajo.groupby(
        ["sucursal", "ingrediente_id"],
        sort=True,
    ):
        resultado = proyectar_serie(
            valores=grupo["consumo_unidad_base"].tolist(),
            etiquetas=grupo["semana"].astype(str).tolist(),
        )

        resultados.append(
            {
                "sucursal": sucursal,
                "ingrediente_id": ingrediente_id,
                "consumo_proyectado_unidad_base": round(
                    resultado.consumo_proyectado,
                    4,
                ),
                "metodo_proyeccion": resultado.metodo,
                "explicacion_proyeccion": resultado.explicacion,
                "semanas_usadas": resultado.semanas_usadas,
                "cantidad_atipicos": resultado.cantidad_atipicos,
                "semanas_atipicas": ", ".join(resultado.semanas_atipicas),
                "mae_backtest": round(resultado.mae_backtest, 4),
                "wape_backtest_pct": round(
                    resultado.wape_backtest_pct,
                    4,
                ),
                "pendiente_semanal": round(
                    resultado.pendiente_semanal,
                    4,
                ),
                "r2_tendencia": round(resultado.r2_tendencia, 4),
            }
        )

    return pd.DataFrame(resultados)
