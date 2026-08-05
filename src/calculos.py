from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


ESTADO_CORRECTO = "CORRECTO"
ESTADO_SIN_COMPRA = "SIN_COMPRA_NECESARIA"
ESTADO_INSUFICIENTE = "PEDIDO_INSUFICIENTE"
ESTADO_SOBREPEDIDO = "SOBREPEDIDO"
ESTADO_OMITIDO = "INGREDIENTE_OMITIDO"
ESTADO_COMPRA_INNECESARIA = "COMPRA_INNECESARIA"
ESTADO_NO_EVALUABLE = "NO_EVALUABLE"

PRIORIDAD_CRITICA = "CRITICA"
PRIORIDAD_ALTA = "ALTA"
PRIORIDAD_MEDIA = "MEDIA"
PRIORIDAD_SIN_ALERTA = "SIN_ALERTA"

COLUMNAS_CATALOGO = {
    "ingrediente_id",
    "nombre",
    "proveedor",
    "unidad_base",
    "formato_compra",
    "unidad_base_por_formato",
    "es_perecedero",
}
COLUMNAS_INVENTARIO = {
    "sucursal",
    "ingrediente_id",
    "stock_actual_unidad_base",
}
COLUMNAS_ORDEN = {
    "sucursal",
    "ingrediente_id",
    "cantidad_formatos",
}
COLUMNAS_PROYECCIONES = {
    "sucursal",
    "ingrediente_id",
    "consumo_proyectado_unidad_base",
}

TOLERANCIA_NUMERICA = 1e-9


class ErrorCalculoCompras(Exception):
    """Error controlado al evaluar las órdenes de compra."""


def _verificar_columnas(
    dataframe: pd.DataFrame,
    requeridas: set[str],
    nombre: str,
) -> None:
    faltantes = requeridas - set(dataframe.columns)
    if faltantes:
        raise ErrorCalculoCompras(
            f"Faltan columnas requeridas en {nombre}: "
            + ", ".join(sorted(faltantes))
        )


def _verificar_clave_unica(
    dataframe: pd.DataFrame,
    columnas: list[str],
    nombre: str,
) -> None:
    if dataframe.duplicated(subset=columnas, keep=False).any():
        raise ErrorCalculoCompras(
            f"Existen registros duplicados en {nombre} para la clave: "
            + ", ".join(columnas)
        )


def _convertir_numerico_no_negativo(
    serie: pd.Series,
    nombre_campo: str,
) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce")

    if valores.isna().any() or not np.isfinite(valores.astype(float)).all():
        raise ErrorCalculoCompras(
            f"El campo {nombre_campo} contiene valores vacíos o no numéricos."
        )

    if (valores < 0).any():
        raise ErrorCalculoCompras(
            f"El campo {nombre_campo} contiene valores negativos."
        )

    return valores.astype(float)


def _convertir_formatos_enteros(serie: pd.Series) -> pd.Series:
    valores = _convertir_numerico_no_negativo(
        serie,
        "cantidad_formatos",
    )

    if not np.isclose(valores, np.round(valores), atol=TOLERANCIA_NUMERICA).all():
        raise ErrorCalculoCompras(
            "La orden contiene cantidades fraccionarias de formatos."
        )

    return np.round(valores).astype("int64")


def _normalizar_perecedero(valor: object) -> bool:
    texto = str(valor).strip().lower()

    if texto in {"si", "sí", "s", "true", "1"}:
        return True

    if texto in {"no", "n", "false", "0"}:
        return False

    raise ErrorCalculoCompras(
        f"Valor inválido en es_perecedero: {valor!r}."
    )


def calcular_formatos_recomendados(
    necesidad_compra: float,
    unidad_base_por_formato: float,
) -> int:
    """Redondea la necesidad hacia arriba a formatos completos."""
    necesidad = float(necesidad_compra)
    formato = float(unidad_base_por_formato)

    if not math.isfinite(necesidad) or necesidad < 0:
        raise ErrorCalculoCompras(
            "La necesidad de compra debe ser un número no negativo."
        )

    if not math.isfinite(formato) or formato <= 0:
        raise ErrorCalculoCompras(
            "La unidad base por formato debe ser mayor que cero."
        )

    if necesidad <= TOLERANCIA_NUMERICA:
        return 0

    cociente = necesidad / formato
    return int(math.ceil(cociente - TOLERANCIA_NUMERICA))


def _clasificar_estado(fila: pd.Series) -> str:
    solicitados = int(fila["cantidad_formatos_solicitados"])
    recomendados = int(fila["formatos_recomendados"])
    orden_enviada = bool(fila["orden_enviada"])

    if not orden_enviada and recomendados > 0:
        return ESTADO_OMITIDO

    if recomendados == 0 and solicitados == 0:
        return ESTADO_SIN_COMPRA

    if recomendados == 0 and solicitados > 0:
        return ESTADO_COMPRA_INNECESARIA

    if solicitados < recomendados:
        return ESTADO_INSUFICIENTE

    if solicitados > recomendados:
        return ESTADO_SOBREPEDIDO

    return ESTADO_CORRECTO


def _clasificar_prioridad(estado: str, es_perecedero: bool) -> str:
    if estado in {ESTADO_NO_EVALUABLE, ESTADO_OMITIDO}:
        return PRIORIDAD_CRITICA

    if estado == ESTADO_INSUFICIENTE:
        return PRIORIDAD_ALTA

    if estado in {ESTADO_SOBREPEDIDO, ESTADO_COMPRA_INNECESARIA}:
        return PRIORIDAD_ALTA if es_perecedero else PRIORIDAD_MEDIA

    return PRIORIDAD_SIN_ALERTA


def _riesgo_operativo(estado: str, es_perecedero: bool) -> str:
    if estado == ESTADO_NO_EVALUABLE:
        return "ERROR_DE_DATOS"

    if estado in {ESTADO_OMITIDO, ESTADO_INSUFICIENTE}:
        return "RIESGO_DE_QUIEBRE"

    if estado in {ESTADO_SOBREPEDIDO, ESTADO_COMPRA_INNECESARIA}:
        return (
            "RIESGO_DE_VENCIMIENTO"
            if es_perecedero
            else "CAPITAL_INMOVILIZADO"
        )

    return "SIN_RIESGO_DETECTADO"


def _preparar_catalogo(ingredientes: pd.DataFrame) -> pd.DataFrame:
    _verificar_columnas(ingredientes, COLUMNAS_CATALOGO, "ingredientes")
    _verificar_clave_unica(ingredientes, ["ingrediente_id"], "ingredientes")

    catalogo = ingredientes.copy()
    catalogo["unidad_base_por_formato"] = _convertir_numerico_no_negativo(
        catalogo["unidad_base_por_formato"],
        "unidad_base_por_formato",
    )

    if (catalogo["unidad_base_por_formato"] <= 0).any():
        raise ErrorCalculoCompras(
            "Existen formatos de compra iguales o menores que cero."
        )

    catalogo["es_perecedero_bool"] = catalogo["es_perecedero"].map(
        _normalizar_perecedero
    )
    return catalogo


def _preparar_inventario(inventario: pd.DataFrame) -> pd.DataFrame:
    _verificar_columnas(inventario, COLUMNAS_INVENTARIO, "inventario_actual")
    _verificar_clave_unica(
        inventario,
        ["sucursal", "ingrediente_id"],
        "inventario_actual",
    )

    preparado = inventario.copy()
    preparado["stock_actual_unidad_base"] = _convertir_numerico_no_negativo(
        preparado["stock_actual_unidad_base"],
        "stock_actual_unidad_base",
    )
    return preparado


def _preparar_proyecciones(proyecciones: pd.DataFrame) -> pd.DataFrame:
    _verificar_columnas(
        proyecciones,
        COLUMNAS_PROYECCIONES,
        "proyecciones",
    )
    _verificar_clave_unica(
        proyecciones,
        ["sucursal", "ingrediente_id"],
        "proyecciones",
    )

    preparado = proyecciones.copy()
    preparado["consumo_proyectado_unidad_base"] = (
        _convertir_numerico_no_negativo(
            preparado["consumo_proyectado_unidad_base"],
            "consumo_proyectado_unidad_base",
        )
    )
    return preparado


def _preparar_orden(orden: pd.DataFrame) -> pd.DataFrame:
    _verificar_columnas(orden, COLUMNAS_ORDEN, "orden_compra_semana")
    _verificar_clave_unica(
        orden,
        ["sucursal", "ingrediente_id"],
        "orden_compra_semana",
    )

    preparada = orden.copy()
    preparada["cantidad_formatos"] = _convertir_formatos_enteros(
        preparada["cantidad_formatos"]
    )
    return preparada


def _construir_filas_desconocidas(
    orden: pd.DataFrame,
    catalogo: pd.DataFrame,
) -> pd.DataFrame:
    desconocidas = orden.loc[
        ~orden["ingrediente_id"].isin(catalogo["ingrediente_id"])
    ].copy()

    if desconocidas.empty:
        return pd.DataFrame()

    resultado = desconocidas.rename(
        columns={"cantidad_formatos": "cantidad_formatos_solicitados"}
    )
    resultado["nombre"] = "Ingrediente no registrado"
    resultado["proveedor"] = pd.NA
    resultado["unidad_base"] = pd.NA
    resultado["formato_compra"] = pd.NA
    resultado["unidad_base_por_formato"] = np.nan
    resultado["es_perecedero"] = pd.NA
    resultado["es_perecedero_bool"] = pd.NA
    resultado["consumo_proyectado_unidad_base"] = np.nan
    resultado["stock_actual_unidad_base"] = np.nan
    resultado["necesidad_neta_unidad_base"] = np.nan
    resultado["necesidad_compra_unidad_base"] = np.nan
    resultado["formatos_recomendados"] = pd.NA
    resultado["compra_recomendada_unidad_base"] = np.nan
    resultado["orden_enviada"] = True
    resultado["cantidad_solicitada_unidad_base"] = np.nan
    resultado["diferencia_formatos"] = pd.NA
    resultado["faltante_formatos"] = pd.NA
    resultado["exceso_formatos"] = pd.NA
    resultado["diferencia_unidad_base_vs_recomendacion"] = np.nan
    resultado["balance_final_unidad_base"] = np.nan
    resultado["cobertura_proyectada_pct"] = np.nan
    resultado["estado"] = ESTADO_NO_EVALUABLE
    resultado["prioridad"] = PRIORIDAD_CRITICA
    resultado["riesgo_operativo"] = "ERROR_DE_DATOS"

    return resultado


def evaluar_ordenes_compra(
    ingredientes: pd.DataFrame,
    inventario_actual: pd.DataFrame,
    orden_compra_semana: pd.DataFrame,
    proyecciones: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula la necesidad y compara la orden con formatos completos."""
    catalogo = _preparar_catalogo(ingredientes)
    inventario = _preparar_inventario(inventario_actual)
    orden = _preparar_orden(orden_compra_semana)
    pronosticos = _preparar_proyecciones(proyecciones)

    base = pronosticos.merge(
        catalogo,
        on="ingrediente_id",
        how="left",
        validate="many_to_one",
    )

    if base["nombre"].isna().any():
        faltantes = sorted(base.loc[base["nombre"].isna(), "ingrediente_id"].unique())
        raise ErrorCalculoCompras(
            "Las proyecciones contienen ingredientes que no existen en el catálogo: "
            + ", ".join(faltantes)
        )

    base = base.merge(
        inventario,
        on=["sucursal", "ingrediente_id"],
        how="left",
        validate="one_to_one",
    )

    if base["stock_actual_unidad_base"].isna().any():
        faltantes = base.loc[
            base["stock_actual_unidad_base"].isna(),
            ["sucursal", "ingrediente_id"],
        ]
        detalle = "; ".join(
            f"{fila.sucursal} / {fila.ingrediente_id}"
            for fila in faltantes.itertuples(index=False)
        )
        raise ErrorCalculoCompras(
            "Falta inventario actual para: " + detalle
        )

    orden_valida = orden.loc[
        orden["ingrediente_id"].isin(catalogo["ingrediente_id"])
    ].copy()
    orden_valida["orden_enviada"] = True

    base = base.merge(
        orden_valida,
        on=["sucursal", "ingrediente_id"],
        how="left",
        validate="one_to_one",
    )

    base["orden_enviada"] = base["orden_enviada"].eq(True)
    base["cantidad_formatos"] = base["cantidad_formatos"].fillna(0).astype("int64")
    base = base.rename(
        columns={"cantidad_formatos": "cantidad_formatos_solicitados"}
    )

    base["necesidad_neta_unidad_base"] = (
        base["consumo_proyectado_unidad_base"]
        - base["stock_actual_unidad_base"]
    )
    base["necesidad_compra_unidad_base"] = base[
        "necesidad_neta_unidad_base"
    ].clip(lower=0.0)

    base["formatos_recomendados"] = [
        calcular_formatos_recomendados(necesidad, formato)
        for necesidad, formato in zip(
            base["necesidad_compra_unidad_base"],
            base["unidad_base_por_formato"],
            strict=True,
        )
    ]
    base["formatos_recomendados"] = base[
        "formatos_recomendados"
    ].astype("int64")

    base["compra_recomendada_unidad_base"] = (
        base["formatos_recomendados"]
        * base["unidad_base_por_formato"]
    )
    base["cantidad_solicitada_unidad_base"] = (
        base["cantidad_formatos_solicitados"]
        * base["unidad_base_por_formato"]
    )
    base["diferencia_formatos"] = (
        base["cantidad_formatos_solicitados"]
        - base["formatos_recomendados"]
    ).astype("int64")
    base["faltante_formatos"] = (-base["diferencia_formatos"]).clip(
        lower=0
    ).astype("int64")
    base["exceso_formatos"] = base["diferencia_formatos"].clip(
        lower=0
    ).astype("int64")
    base["diferencia_unidad_base_vs_recomendacion"] = (
        base["cantidad_solicitada_unidad_base"]
        - base["compra_recomendada_unidad_base"]
    )
    base["balance_final_unidad_base"] = (
        base["stock_actual_unidad_base"]
        + base["cantidad_solicitada_unidad_base"]
        - base["consumo_proyectado_unidad_base"]
    )

    consumo = base["consumo_proyectado_unidad_base"]
    disponible = (
        base["stock_actual_unidad_base"]
        + base["cantidad_solicitada_unidad_base"]
    )
    base["cobertura_proyectada_pct"] = np.where(
        consumo > TOLERANCIA_NUMERICA,
        disponible / consumo * 100.0,
        np.where(disponible > TOLERANCIA_NUMERICA, np.inf, 100.0),
    )

    base["estado"] = base.apply(_clasificar_estado, axis=1)
    base["prioridad"] = [
        _clasificar_prioridad(estado, perecedero)
        for estado, perecedero in zip(
            base["estado"],
            base["es_perecedero_bool"],
            strict=True,
        )
    ]
    base["riesgo_operativo"] = [
        _riesgo_operativo(estado, perecedero)
        for estado, perecedero in zip(
            base["estado"],
            base["es_perecedero_bool"],
            strict=True,
        )
    ]

    desconocidas = _construir_filas_desconocidas(orden, catalogo)
    if not desconocidas.empty:
        columnas_faltantes = set(base.columns) - set(desconocidas.columns)
        for columna in columnas_faltantes:
            desconocidas[columna] = pd.NA
        desconocidas = desconocidas[base.columns]
        registros = base.to_dict(orient="records")
        registros.extend(desconocidas.to_dict(orient="records"))
        base = pd.DataFrame.from_records(registros, columns=base.columns)

    prioridad_orden = {
        PRIORIDAD_CRITICA: 0,
        PRIORIDAD_ALTA: 1,
        PRIORIDAD_MEDIA: 2,
        PRIORIDAD_SIN_ALERTA: 3,
    }
    base["_orden_prioridad"] = base["prioridad"].map(prioridad_orden)
    base = base.sort_values(
        ["_orden_prioridad", "sucursal", "ingrediente_id"],
        kind="stable",
    ).drop(columns="_orden_prioridad")

    columnas_redondeo: Iterable[str] = (
        "consumo_proyectado_unidad_base",
        "stock_actual_unidad_base",
        "necesidad_neta_unidad_base",
        "necesidad_compra_unidad_base",
        "compra_recomendada_unidad_base",
        "cantidad_solicitada_unidad_base",
        "diferencia_unidad_base_vs_recomendacion",
        "balance_final_unidad_base",
        "cobertura_proyectada_pct",
    )
    for columna in columnas_redondeo:
        base[columna] = pd.to_numeric(base[columna], errors="coerce").round(4)

    return base.reset_index(drop=True)


def resumir_evaluacion(evaluacion: pd.DataFrame) -> dict[str, int]:
    """Genera indicadores listos para el resumen ejecutivo."""
    requeridas = {"estado", "prioridad"}
    faltantes = requeridas - set(evaluacion.columns)
    if faltantes:
        raise ErrorCalculoCompras(
            "La evaluación no contiene las columnas necesarias: "
            + ", ".join(sorted(faltantes))
        )

    estados = evaluacion["estado"]
    prioridades = evaluacion["prioridad"]
    no_evaluables = int((estados == ESTADO_NO_EVALUABLE).sum())
    sin_alerta = estados.isin({ESTADO_CORRECTO, ESTADO_SIN_COMPRA})

    return {
        "registros_recibidos": int(len(evaluacion)),
        "combinaciones_evaluables": int(len(evaluacion) - no_evaluables),
        "no_evaluables": no_evaluables,
        "correctos": int((estados == ESTADO_CORRECTO).sum()),
        "sin_compra_necesaria": int((estados == ESTADO_SIN_COMPRA).sum()),
        "pedidos_insuficientes": int((estados == ESTADO_INSUFICIENTE).sum()),
        "sobrepedidos": int((estados == ESTADO_SOBREPEDIDO).sum()),
        "ingredientes_omitidos": int((estados == ESTADO_OMITIDO).sum()),
        "compras_innecesarias": int(
            (estados == ESTADO_COMPRA_INNECESARIA).sum()
        ),
        "alertas_total": int((~sin_alerta).sum()),
        "prioridad_critica": int((prioridades == PRIORIDAD_CRITICA).sum()),
        "prioridad_alta": int((prioridades == PRIORIDAD_ALTA).sum()),
        "prioridad_media": int((prioridades == PRIORIDAD_MEDIA).sum()),
    }


def generar_orden_corregida(
    evaluacion: pd.DataFrame,
    incluir_cantidades_cero: bool = False,
) -> pd.DataFrame:
    """Genera una orden recomendada y lista para agrupar por proveedor."""
    requeridas = {
        "sucursal",
        "ingrediente_id",
        "nombre",
        "proveedor",
        "formato_compra",
        "unidad_base",
        "formatos_recomendados",
        "compra_recomendada_unidad_base",
        "cantidad_formatos_solicitados",
        "diferencia_formatos",
        "estado",
    }
    faltantes = requeridas - set(evaluacion.columns)
    if faltantes:
        raise ErrorCalculoCompras(
            "La evaluación no contiene las columnas necesarias: "
            + ", ".join(sorted(faltantes))
        )

    corregida = evaluacion.loc[
        evaluacion["estado"] != ESTADO_NO_EVALUABLE,
        list(requeridas),
    ].copy()

    if not incluir_cantidades_cero:
        corregida = corregida.loc[
            corregida["formatos_recomendados"] > 0
        ].copy()

    corregida = corregida.rename(
        columns={
            "formatos_recomendados": "cantidad_formatos_recomendada",
            "compra_recomendada_unidad_base": (
                "cantidad_unidad_base_recomendada"
            ),
            "cantidad_formatos_solicitados": (
                "cantidad_formatos_original"
            ),
            "diferencia_formatos": "ajuste_formatos_original_menos_recomendado",
        }
    )

    columnas = [
        "proveedor",
        "sucursal",
        "ingrediente_id",
        "nombre",
        "formato_compra",
        "unidad_base",
        "cantidad_formatos_original",
        "cantidad_formatos_recomendada",
        "cantidad_unidad_base_recomendada",
        "ajuste_formatos_original_menos_recomendado",
        "estado",
    ]

    return corregida[columnas].sort_values(
        ["proveedor", "sucursal", "nombre"],
        kind="stable",
    ).reset_index(drop=True)
