from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from src.alertas import agregar_mensajes_alerta
from src.calculos import (
    ESTADO_NO_EVALUABLE,
    evaluar_ordenes_compra,
    generar_orden_corregida,
    resumir_evaluacion,
)
from src.proyecciones import proyectar_consumo_historico
from src.validaciones import auditar_datos, puede_continuar


PRIORIDAD_ORDEN: dict[str, int] = {
    "CRITICA": 0,
    "ALTA": 1,
    "MEDIA": 2,
    "SIN_ALERTA": 3,
}

ESTADO_ETIQUETAS: dict[str, str] = {
    "CORRECTO": "Pedido correcto",
    "SIN_COMPRA_NECESARIA": "Sin compra necesaria",
    "PEDIDO_INSUFICIENTE": "Pedido insuficiente",
    "SOBREPEDIDO": "Sobrepedido",
    "INGREDIENTE_OMITIDO": "Ingrediente omitido",
    "COMPRA_INNECESARIA": "Compra innecesaria",
    "NO_EVALUABLE": "No evaluable",
}

PRIORIDAD_ETIQUETAS: dict[str, str] = {
    "CRITICA": "Crítica",
    "ALTA": "Alta",
    "MEDIA": "Media",
    "SIN_ALERTA": "Sin alerta",
}

METODO_ETIQUETAS: dict[str, str] = {
    "promedio_simple": "Promedio simple",
    "promedio_ponderado": "Promedio ponderado",
    "mediana": "Mediana histórica",
    "promedio_ponderado_robusto": "Promedio ponderado robusto",
    "tendencia_lineal": "Tendencia lineal",
}

COLUMNAS_ORDEN = ["sucursal", "ingrediente_id", "cantidad_formatos"]


class ErrorDashboard(Exception):
    """Error controlado al preparar los datos para el dashboard."""


@dataclass(frozen=True)
class AnalisisCompras:
    datos: dict[str, pd.DataFrame]
    hallazgos: pd.DataFrame
    proyecciones: pd.DataFrame
    evaluacion: pd.DataFrame
    resultados: pd.DataFrame
    resumen: dict[str, int]
    orden_corregida: pd.DataFrame


def leer_orden_csv(contenido: bytes) -> pd.DataFrame:
    """Lee una orden CSV cargada desde la interfaz."""
    if not contenido:
        raise ErrorDashboard("El archivo de orden está vacío.")

    try:
        orden = pd.read_csv(BytesIO(contenido), encoding="utf-8-sig")
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise ErrorDashboard(
            "No se pudo leer la orden. Verifique que sea un CSV válido en UTF-8."
        ) from error

    orden.columns = [
        str(columna).strip().lstrip("\ufeff")
        for columna in orden.columns
    ]
    return orden


def completar_orden_para_editor(
    orden: pd.DataFrame,
    consumo_historico: pd.DataFrame,
    ingredientes: pd.DataFrame,
) -> pd.DataFrame:
    """Completa las combinaciones válidas y conserva filas desconocidas."""
    faltantes = set(COLUMNAS_ORDEN) - set(orden.columns)
    if faltantes:
        raise ErrorDashboard(
            "La orden no contiene las columnas requeridas: "
            + ", ".join(sorted(faltantes))
        )

    sucursales = sorted(
        consumo_historico["sucursal"].dropna().astype(str).unique()
    )
    catalogo = sorted(
        ingredientes["ingrediente_id"].dropna().astype(str).unique()
    )

    esperadas = pd.MultiIndex.from_product(
        [sucursales, catalogo],
        names=["sucursal", "ingrediente_id"],
    ).to_frame(index=False)

    orden_trabajo = orden[COLUMNAS_ORDEN].copy()
    orden_trabajo["sucursal"] = orden_trabajo["sucursal"].astype(str).str.strip()
    orden_trabajo["ingrediente_id"] = (
        orden_trabajo["ingrediente_id"].astype(str).str.strip()
    )

    validas = orden_trabajo.loc[
        orden_trabajo["sucursal"].isin(sucursales)
        & orden_trabajo["ingrediente_id"].isin(catalogo)
    ].copy()

    desconocidas = orden_trabajo.loc[
        ~(
            orden_trabajo["sucursal"].isin(sucursales)
            & orden_trabajo["ingrediente_id"].isin(catalogo)
        )
    ].copy()

    completas = esperadas.merge(
        validas,
        on=["sucursal", "ingrediente_id"],
        how="left",
    )
    completas["cantidad_formatos"] = pd.to_numeric(
        completas["cantidad_formatos"], errors="coerce"
    ).fillna(0)

    if not desconocidas.empty:
        completas = pd.concat(
            [completas, desconocidas],
            ignore_index=True,
            sort=False,
        )

    return completas[COLUMNAS_ORDEN].reset_index(drop=True)


def preparar_reparacion_orden(
    orden: pd.DataFrame,
    consumo_historico: pd.DataFrame,
    ingredientes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separa excepciones y crea una plantilla completa sin corregir IDs."""
    completa = completar_orden_para_editor(
        orden=orden,
        consumo_historico=consumo_historico,
        ingredientes=ingredientes,
    )
    sucursales_validas = set(
        consumo_historico["sucursal"].dropna().astype(str).str.strip()
    )
    ingredientes_validos = set(
        ingredientes["ingrediente_id"].dropna().astype(str).str.strip()
    )

    mascara_valida = (
        completa["sucursal"].isin(sucursales_validas)
        & completa["ingrediente_id"].isin(ingredientes_validos)
    )
    plantilla = completa.loc[mascara_valida, COLUMNAS_ORDEN].copy()
    excepciones = completa.loc[~mascara_valida, COLUMNAS_ORDEN].copy()

    claves_originales = set(
        zip(
            orden["sucursal"].astype(str).str.strip(),
            orden["ingrediente_id"].astype(str).str.strip(),
            strict=True,
        )
    )
    reporte: list[dict[str, object]] = []
    for fila in plantilla.itertuples(index=False):
        clave = (str(fila.sucursal), str(fila.ingrediente_id))
        if clave not in claves_originales:
            reporte.append(
                {
                    "accion": "COMBINACION_AGREGADA_CON_CERO",
                    "sucursal": fila.sucursal,
                    "ingrediente_id": fila.ingrediente_id,
                    "detalle": (
                        "La combinación faltante se añadió con cero para revisión; "
                        "no se modificó ningún identificador."
                    ),
                }
            )
    for fila in excepciones.itertuples(index=False):
        reporte.append(
            {
                "accion": "FILA_SEPARADA_PARA_REVISION",
                "sucursal": fila.sucursal,
                "ingrediente_id": fila.ingrediente_id,
                "detalle": (
                    "La fila se separó porque la sucursal o el ingrediente no existe "
                    "en los catálogos disponibles."
                ),
            }
        )

    return (
        plantilla.sort_values(
            ["sucursal", "ingrediente_id"], kind="stable"
        ).reset_index(drop=True),
        excepciones.reset_index(drop=True),
        pd.DataFrame(
            reporte,
            columns=["accion", "sucursal", "ingrediente_id", "detalle"],
        ),
    )


def construir_analisis(
    datos: dict[str, pd.DataFrame],
    orden_compra: pd.DataFrame | None = None,
) -> AnalisisCompras:
    """Ejecuta el flujo completo que alimenta el dashboard."""
    requeridos = {
        "ingredientes",
        "consumo_historico",
        "inventario_actual",
        "orden_compra_semana",
    }
    faltantes = requeridos - set(datos)
    if faltantes:
        raise ErrorDashboard(
            "Faltan conjuntos de datos requeridos: "
            + ", ".join(sorted(faltantes))
        )

    datos_trabajo = {
        nombre: dataframe.copy()
        for nombre, dataframe in datos.items()
    }
    if orden_compra is not None:
        datos_trabajo["orden_compra_semana"] = orden_compra.copy()

    hallazgos = auditar_datos(datos_trabajo)
    if not puede_continuar(hallazgos):
        bloqueantes = hallazgos.loc[
            hallazgos["bloqueante"].fillna(False)
        ]
        codigos = ", ".join(
            bloqueantes["codigo"].astype(str).drop_duplicates().tolist()
        )
        raise ErrorDashboard(
            "La auditoría encontró errores bloqueantes: " + codigos
        )

    proyecciones = proyectar_consumo_historico(
        datos_trabajo["consumo_historico"]
    )
    evaluacion = evaluar_ordenes_compra(
        ingredientes=datos_trabajo["ingredientes"],
        inventario_actual=datos_trabajo["inventario_actual"],
        orden_compra_semana=datos_trabajo["orden_compra_semana"],
        proyecciones=proyecciones,
    )
    resultados = agregar_mensajes_alerta(evaluacion)
    resumen = resumir_evaluacion(evaluacion)
    orden_corregida = generar_orden_corregida(evaluacion)

    return AnalisisCompras(
        datos=datos_trabajo,
        hallazgos=hallazgos,
        proyecciones=proyecciones,
        evaluacion=evaluacion,
        resultados=resultados,
        resumen=resumen,
        orden_corregida=orden_corregida,
    )


def filtrar_resultados(
    resultados: pd.DataFrame,
    *,
    solo_alertas: bool = False,
    sucursales: Sequence[str] | None = None,
    estados: Sequence[str] | None = None,
    prioridades: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Aplica filtros de interfaz sin modificar el resultado original."""
    filtrados = resultados.copy()

    if solo_alertas:
        filtrados = filtrados.loc[filtrados["es_alerta"].fillna(False)]

    if sucursales:
        filtrados = filtrados.loc[filtrados["sucursal"].isin(sucursales)]

    if estados:
        filtrados = filtrados.loc[filtrados["estado"].isin(estados)]

    if prioridades:
        filtrados = filtrados.loc[filtrados["prioridad"].isin(prioridades)]

    orden = filtrados["prioridad"].map(PRIORIDAD_ORDEN).fillna(99)
    filtrados = filtrados.assign(_orden_prioridad=orden)
    filtrados = filtrados.sort_values(
        ["_orden_prioridad", "sucursal", "nombre"],
        kind="stable",
    ).drop(columns="_orden_prioridad")

    return filtrados.reset_index(drop=True)


def preparar_tabla_alertas(resultados: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una tabla compacta y legible para la gerente."""
    columnas = [
        "prioridad",
        "sucursal",
        "nombre",
        "estado",
        "cantidad_formatos_solicitados",
        "formatos_recomendados",
        "titulo_alerta",
        "accion_recomendada",
    ]
    tabla = resultados.loc[:, columnas].copy()
    tabla["prioridad"] = tabla["prioridad"].map(PRIORIDAD_ETIQUETAS)
    tabla["estado"] = tabla["estado"].map(ESTADO_ETIQUETAS)
    tabla = tabla.rename(
        columns={
            "prioridad": "Prioridad",
            "sucursal": "Sucursal",
            "nombre": "Ingrediente",
            "estado": "Estado",
            "cantidad_formatos_solicitados": "Solicitado",
            "formatos_recomendados": "Recomendado",
            "titulo_alerta": "Alerta",
            "accion_recomendada": "Acción recomendada",
        }
    )
    return tabla


def preparar_serie_detalle(
    consumo_historico: pd.DataFrame,
    proyecciones: pd.DataFrame,
    *,
    sucursal: str,
    ingrediente_id: str,
) -> pd.DataFrame:
    """Combina histórico, atípicos y proyección para la gráfica de detalle."""
    historico = consumo_historico.loc[
        (consumo_historico["sucursal"] == sucursal)
        & (consumo_historico["ingrediente_id"] == ingrediente_id),
        ["semana", "consumo_unidad_base"],
    ].copy()

    if historico.empty:
        raise ErrorDashboard(
            f"No existe histórico para {sucursal} / {ingrediente_id}."
        )

    historico["_orden"] = (
        historico["semana"].astype(str).str.extract(r"(\d+)$")[0].astype(int)
    )
    historico = historico.sort_values("_orden")
    historico["tipo"] = "Histórico"
    historico["es_atipico"] = False

    fila_proyeccion = proyecciones.loc[
        (proyecciones["sucursal"] == sucursal)
        & (proyecciones["ingrediente_id"] == ingrediente_id)
    ]
    if fila_proyeccion.empty:
        raise ErrorDashboard(
            f"No existe proyección para {sucursal} / {ingrediente_id}."
        )

    fila = fila_proyeccion.iloc[0]
    semanas_atipicas = {
        semana.strip()
        for semana in str(fila.get("semanas_atipicas", "")).split(",")
        if semana.strip()
    }
    historico["es_atipico"] = historico["semana"].isin(semanas_atipicas)

    siguiente = int(historico["_orden"].max()) + 1
    proyectado = pd.DataFrame(
        {
            "semana": [f"S{siguiente}"],
            "consumo_unidad_base": [
                float(fila["consumo_proyectado_unidad_base"])
            ],
            "_orden": [siguiente],
            "tipo": ["Proyección"],
            "es_atipico": [False],
        }
    )

    return pd.concat([historico, proyectado], ignore_index=True)


def resumen_por_sucursal(resultados: pd.DataFrame) -> pd.DataFrame:
    """Cuenta alertas por sucursal y prioridad."""
    alertas = resultados.loc[resultados["es_alerta"].fillna(False)].copy()
    if alertas.empty:
        return pd.DataFrame(
            columns=["sucursal", "prioridad", "cantidad"]
        )

    return (
        alertas.groupby(["sucursal", "prioridad"], dropna=False)
        .size()
        .rename("cantidad")
        .reset_index()
    )


def resumen_por_estado(resultados: pd.DataFrame) -> pd.DataFrame:
    """Cuenta combinaciones evaluadas por estado."""
    resumen = (
        resultados.groupby("estado", dropna=False)
        .size()
        .rename("cantidad")
        .reset_index()
    )
    resumen["estado_etiqueta"] = resumen["estado"].map(ESTADO_ETIQUETAS)
    return resumen


def preparar_orden_por_proveedor(
    orden_corregida: pd.DataFrame,
    proveedores: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filtra y ordena la recomendación final por proveedor."""
    resultado = orden_corregida.copy()
    if proveedores:
        resultado = resultado.loc[resultado["proveedor"].isin(proveedores)]

    return resultado.sort_values(
        ["proveedor", "sucursal", "nombre"],
        kind="stable",
    ).reset_index(drop=True)


def dataframe_a_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    """Genera un CSV compatible con Excel conservando tildes."""
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def porcentaje_orden_correcta(resumen: dict[str, int]) -> float:
    """Calcula el porcentaje de combinaciones sin corrección requerida."""
    evaluables = int(resumen.get("combinaciones_evaluables", 0))
    if evaluables <= 0:
        return 0.0

    correctas = int(resumen.get("correctos", 0)) + int(
        resumen.get("sin_compra_necesaria", 0)
    )
    return round(correctas / evaluables * 100.0, 1)


def limpiar_infinito(valor: object) -> float | None:
    """Convierte valores no finitos en None para mostrarlos en la interfaz."""
    if valor is None or pd.isna(valor):
        return None

    numero = float(valor)
    if not np.isfinite(numero):
        return None
    return numero


def obtener_caso(
    resultados: pd.DataFrame,
    *,
    sucursal: str,
    ingrediente_id: str,
) -> pd.Series:
    """Obtiene un caso único para el panel de detalle."""
    caso = resultados.loc[
        (resultados["sucursal"] == sucursal)
        & (resultados["ingrediente_id"] == ingrediente_id)
    ]
    if len(caso) != 1:
        raise ErrorDashboard(
            "No se pudo identificar de forma única el caso seleccionado."
        )
    return caso.iloc[0]


def proyeccion_del_caso(
    proyecciones: pd.DataFrame,
    *,
    sucursal: str,
    ingrediente_id: str,
) -> pd.Series | None:
    """Devuelve la proyección asociada o None si el producto es desconocido."""
    fila = proyecciones.loc[
        (proyecciones["sucursal"] == sucursal)
        & (proyecciones["ingrediente_id"] == ingrediente_id)
    ]
    if fila.empty:
        return None
    return fila.iloc[0]
