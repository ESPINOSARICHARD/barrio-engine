
from __future__ import annotations

from typing import Any

import pandas as pd


COLUMNAS_REQUERIDAS: dict[str, list[str]] = {
    "ingredientes": [
        "ingrediente_id",
        "nombre",
        "proveedor",
        "unidad_base",
        "formato_compra",
        "unidad_base_por_formato",
        "es_perecedero",
    ],
    "consumo_historico": [
        "sucursal",
        "ingrediente_id",
        "semana",
        "consumo_unidad_base",
    ],
    "inventario_actual": [
        "sucursal",
        "ingrediente_id",
        "stock_actual_unidad_base",
    ],
    "orden_compra_semana": [
        "sucursal",
        "ingrediente_id",
        "cantidad_formatos",
    ],
}

CLAVES_UNICAS: dict[str, list[str]] = {
    "ingredientes": ["ingrediente_id"],
    "consumo_historico": ["sucursal", "ingrediente_id", "semana"],
    "inventario_actual": ["sucursal", "ingrediente_id"],
    "orden_compra_semana": ["sucursal", "ingrediente_id"],
}

COLUMNAS_NUMERICAS: dict[str, list[str]] = {
    "ingredientes": ["unidad_base_por_formato"],
    "consumo_historico": ["consumo_unidad_base"],
    "inventario_actual": ["stock_actual_unidad_base"],
    "orden_compra_semana": ["cantidad_formatos"],
}

SEMANAS_ESPERADAS = ["S1", "S2", "S3", "S4", "S5", "S6"]

COLUMNAS_HALLAZGOS = [
    "codigo",
    "nivel",
    "archivo",
    "mensaje",
    "sucursal",
    "ingrediente_id",
    "campo",
    "valor",
    "bloqueante",
]


def _nuevo_hallazgo(
    *,
    codigo: str,
    nivel: str,
    archivo: str,
    mensaje: str,
    sucursal: Any = None,
    ingrediente_id: Any = None,
    campo: Any = None,
    valor: Any = None,
    bloqueante: bool = False,
) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "nivel": nivel,
        "archivo": archivo,
        "mensaje": mensaje,
        "sucursal": sucursal,
        "ingrediente_id": ingrediente_id,
        "campo": campo,
        "valor": valor,
        "bloqueante": bloqueante,
    }


def _agregar_registros(
    hallazgos: list[dict[str, Any]],
    dataframe: pd.DataFrame,
    *,
    codigo: str,
    nivel: str,
    archivo: str,
    mensaje: str,
    campo: str | None = None,
    bloqueante: bool = False,
) -> None:
    for _, fila in dataframe.iterrows():
        hallazgos.append(
            _nuevo_hallazgo(
                codigo=codigo,
                nivel=nivel,
                archivo=archivo,
                mensaje=mensaje,
                sucursal=fila.get("sucursal"),
                ingrediente_id=fila.get("ingrediente_id"),
                campo=campo,
                valor=fila.get(campo) if campo else None,
                bloqueante=bloqueante,
            )
        )


def _estructura_valida(
    datos: dict[str, pd.DataFrame],
    archivo: str,
) -> bool:
    dataframe = datos.get(archivo)
    return (
        dataframe is not None
        and not dataframe.empty
        and set(COLUMNAS_REQUERIDAS[archivo]).issubset(dataframe.columns)
    )


def _validar_estructura(
    datos: dict[str, pd.DataFrame],
    hallazgos: list[dict[str, Any]],
) -> None:
    for archivo, columnas_requeridas in COLUMNAS_REQUERIDAS.items():
        dataframe = datos.get(archivo)

        if dataframe is None:
            hallazgos.append(
                _nuevo_hallazgo(
                    codigo="ARCHIVO_AUSENTE",
                    nivel="ERROR",
                    archivo=archivo,
                    mensaje="No se recibió el archivo requerido.",
                    bloqueante=True,
                )
            )
            continue

        if dataframe.empty:
            hallazgos.append(
                _nuevo_hallazgo(
                    codigo="ARCHIVO_SIN_FILAS",
                    nivel="ERROR",
                    archivo=archivo,
                    mensaje="El archivo no contiene registros.",
                    bloqueante=True,
                )
            )

        faltantes = [
            columna
            for columna in columnas_requeridas
            if columna not in dataframe.columns
        ]
        adicionales = [
            columna
            for columna in dataframe.columns
            if columna not in columnas_requeridas
        ]

        for columna in faltantes:
            hallazgos.append(
                _nuevo_hallazgo(
                    codigo="COLUMNA_FALTANTE",
                    nivel="ERROR",
                    archivo=archivo,
                    mensaje="Falta una columna obligatoria.",
                    campo=columna,
                    bloqueante=True,
                )
            )

        for columna in adicionales:
            hallazgos.append(
                _nuevo_hallazgo(
                    codigo="COLUMNA_ADICIONAL",
                    nivel="ADVERTENCIA",
                    archivo=archivo,
                    mensaje="Se encontró una columna no prevista.",
                    campo=columna,
                )
            )


def _validar_contenido(
    datos: dict[str, pd.DataFrame],
    hallazgos: list[dict[str, Any]],
) -> None:
    for archivo in COLUMNAS_REQUERIDAS:
        if not _estructura_valida(datos, archivo):
            continue

        dataframe = datos[archivo]

        for columna in COLUMNAS_REQUERIDAS[archivo]:
            nulos = dataframe[dataframe[columna].isna()]
            _agregar_registros(
                hallazgos,
                nulos,
                codigo="VALOR_NULO",
                nivel="ERROR",
                archivo=archivo,
                mensaje="Se encontró un valor nulo.",
                campo=columna,
            )

        duplicados = dataframe[
            dataframe.duplicated(
                subset=CLAVES_UNICAS[archivo],
                keep=False,
            )
        ]
        _agregar_registros(
            hallazgos,
            duplicados,
            codigo="REGISTRO_DUPLICADO",
            nivel="ERROR",
            archivo=archivo,
            mensaje="La clave del registro está duplicada.",
        )

        for columna in COLUMNAS_NUMERICAS[archivo]:
            numericos = pd.to_numeric(
                dataframe[columna],
                errors="coerce",
            )

            no_numericos = dataframe[
                dataframe[columna].notna() & numericos.isna()
            ]
            _agregar_registros(
                hallazgos,
                no_numericos,
                codigo="VALOR_NO_NUMERICO",
                nivel="ERROR",
                archivo=archivo,
                mensaje="Se esperaba un valor numérico.",
                campo=columna,
            )

            negativos = dataframe[numericos.lt(0).fillna(False)]
            _agregar_registros(
                hallazgos,
                negativos,
                codigo="VALOR_NEGATIVO",
                nivel="ERROR",
                archivo=archivo,
                mensaje="No se permiten cantidades negativas.",
                campo=columna,
            )

    if _estructura_valida(datos, "ingredientes"):
        ingredientes = datos["ingredientes"]
        formatos = pd.to_numeric(
            ingredientes["unidad_base_por_formato"],
            errors="coerce",
        )

        no_positivos = ingredientes[formatos.le(0).fillna(False)]
        _agregar_registros(
            hallazgos,
            no_positivos,
            codigo="FORMATO_NO_POSITIVO",
            nivel="ERROR",
            archivo="ingredientes",
            mensaje="El tamaño del formato debe ser mayor que cero.",
            campo="unidad_base_por_formato",
            bloqueante=True,
        )

        perecedero = (
            ingredientes["es_perecedero"]
            .astype("string")
            .str.strip()
        )
        invalidos = ingredientes[
            perecedero.notna() & ~perecedero.isin(["Si", "No"])
        ]
        _agregar_registros(
            hallazgos,
            invalidos,
            codigo="PERECEDERO_INVALIDO",
            nivel="ERROR",
            archivo="ingredientes",
            mensaje="El valor debe ser 'Si' o 'No'.",
            campo="es_perecedero",
        )

    if _estructura_valida(datos, "orden_compra_semana"):
        orden = datos["orden_compra_semana"]
        cantidades = pd.to_numeric(
            orden["cantidad_formatos"],
            errors="coerce",
        )
        fraccionarios = orden[
            cantidades.notna() & cantidades.mod(1).ne(0)
        ]
        _agregar_registros(
            hallazgos,
            fraccionarios,
            codigo="FORMATOS_NO_ENTEROS",
            nivel="ERROR",
            archivo="orden_compra_semana",
            mensaje="Los formatos de compra deben ser enteros.",
            campo="cantidad_formatos",
        )


def _validar_referencias_y_completitud(
    datos: dict[str, pd.DataFrame],
    hallazgos: list[dict[str, Any]],
) -> None:
    if not (
        _estructura_valida(datos, "ingredientes")
        and _estructura_valida(datos, "consumo_historico")
    ):
        return

    ingredientes = datos["ingredientes"]
    consumo = datos["consumo_historico"]

    catalogo = sorted(
        ingredientes["ingrediente_id"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )
    sucursales = sorted(
        consumo["sucursal"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    for archivo in [
        "consumo_historico",
        "inventario_actual",
        "orden_compra_semana",
    ]:
        if not _estructura_valida(datos, archivo):
            continue

        dataframe = datos[archivo]
        ids = dataframe["ingrediente_id"].astype("string").str.strip()
        desconocidos = dataframe[
            ids.notna() & ~ids.isin(catalogo)
        ]
        _agregar_registros(
            hallazgos,
            desconocidos,
            codigo="INGREDIENTE_DESCONOCIDO",
            nivel="ERROR",
            archivo=archivo,
            mensaje="El ingrediente no existe en el catálogo.",
        )

    combinaciones_esperadas = pd.MultiIndex.from_product(
        [sucursales, catalogo],
        names=["sucursal", "ingrediente_id"],
    ).to_frame(index=False)

    for archivo in ["inventario_actual", "orden_compra_semana"]:
        if not _estructura_valida(datos, archivo):
            continue

        dataframe = datos[archivo]
        combinaciones_validas = dataframe[
            dataframe["sucursal"].isin(sucursales)
            & dataframe["ingrediente_id"].isin(catalogo)
        ][["sucursal", "ingrediente_id"]].drop_duplicates()

        comparacion = combinaciones_esperadas.merge(
            combinaciones_validas,
            on=["sucursal", "ingrediente_id"],
            how="left",
            indicator=True,
        )
        faltantes = comparacion[
            comparacion["_merge"].eq("left_only")
        ][["sucursal", "ingrediente_id"]]

        if archivo == "inventario_actual":
            codigo = "INVENTARIO_FALTANTE"
            nivel = "ERROR"
            mensaje = "Falta el inventario de este ingrediente."
        else:
            codigo = "ORDEN_INGREDIENTE_OMITIDO"
            nivel = "ADVERTENCIA"
            mensaje = "La orden omitió este ingrediente."

        _agregar_registros(
            hallazgos,
            faltantes,
            codigo=codigo,
            nivel=nivel,
            archivo=archivo,
            mensaje=mensaje,
        )

    historico_esperado = pd.MultiIndex.from_product(
        [sucursales, catalogo, SEMANAS_ESPERADAS],
        names=["sucursal", "ingrediente_id", "semana"],
    ).to_frame(index=False)

    historico_valido = consumo[
        consumo["sucursal"].isin(sucursales)
        & consumo["ingrediente_id"].isin(catalogo)
        & consumo["semana"].isin(SEMANAS_ESPERADAS)
    ][["sucursal", "ingrediente_id", "semana"]].drop_duplicates()

    comparacion = historico_esperado.merge(
        historico_valido,
        on=["sucursal", "ingrediente_id", "semana"],
        how="left",
        indicator=True,
    )
    semanas_faltantes = comparacion[
        comparacion["_merge"].eq("left_only")
    ][["sucursal", "ingrediente_id", "semana"]]

    _agregar_registros(
        hallazgos,
        semanas_faltantes,
        codigo="HISTORICO_INCOMPLETO",
        nivel="ERROR",
        archivo="consumo_historico",
        mensaje="Falta una semana del histórico.",
        campo="semana",
    )


def auditar_datos(
    datos: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Devuelve todos los problemas encontrados en los cuatro archivos."""

    hallazgos: list[dict[str, Any]] = []

    _validar_estructura(datos, hallazgos)
    _validar_contenido(datos, hallazgos)
    _validar_referencias_y_completitud(datos, hallazgos)

    return pd.DataFrame(
        hallazgos,
        columns=COLUMNAS_HALLAZGOS,
    )


def puede_continuar(hallazgos: pd.DataFrame) -> bool:
    """Indica si no existen errores estructurales bloqueantes."""

    if hallazgos.empty:
        return True

    return not hallazgos["bloqueante"].fillna(False).any()
