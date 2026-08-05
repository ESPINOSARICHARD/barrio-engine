
import pandas as pd

from src.carga_datos import cargar_datos
from src.validaciones import auditar_datos, puede_continuar


def test_datos_reales_detectan_los_dos_casos_del_reto() -> None:
    hallazgos = auditar_datos(cargar_datos())

    assert set(hallazgos["codigo"]) == {
        "INGREDIENTE_DESCONOCIDO",
        "ORDEN_INGREDIENTE_OMITIDO",
    }
    assert len(hallazgos) == 2
    assert puede_continuar(hallazgos)


def test_detecta_aji_chombo_como_ingrediente_desconocido() -> None:
    hallazgos = auditar_datos(cargar_datos())

    resultado = hallazgos[
        hallazgos["codigo"].eq("INGREDIENTE_DESCONOCIDO")
    ].iloc[0]

    assert resultado["archivo"] == "orden_compra_semana"
    assert resultado["sucursal"] == "Costa del Este"
    assert resultado["ingrediente_id"] == "aji_chombo"


def test_detecta_mozzarella_omitida_en_brisas_del_golf() -> None:
    hallazgos = auditar_datos(cargar_datos())

    resultado = hallazgos[
        hallazgos["codigo"].eq("ORDEN_INGREDIENTE_OMITIDO")
    ].iloc[0]

    assert resultado["archivo"] == "orden_compra_semana"
    assert resultado["sucursal"] == "Brisas del Golf"
    assert resultado["ingrediente_id"] == "mozzarella"


def test_columna_faltante_es_bloqueante() -> None:
    datos = cargar_datos()
    datos["inventario_actual"] = datos["inventario_actual"].drop(
        columns=["stock_actual_unidad_base"]
    )

    hallazgos = auditar_datos(datos)

    resultado = hallazgos[
        hallazgos["codigo"].eq("COLUMNA_FALTANTE")
        & hallazgos["archivo"].eq("inventario_actual")
    ].iloc[0]

    assert resultado["campo"] == "stock_actual_unidad_base"
    assert bool(resultado["bloqueante"])
    assert not puede_continuar(hallazgos)


def test_detecta_cantidad_negativa() -> None:
    datos = cargar_datos()
    datos["inventario_actual"] = datos["inventario_actual"].copy()
    datos["inventario_actual"].loc[
        0,
        "stock_actual_unidad_base",
    ] = -1

    hallazgos = auditar_datos(datos)

    negativos = hallazgos[
        hallazgos["codigo"].eq("VALOR_NEGATIVO")
        & hallazgos["archivo"].eq("inventario_actual")
    ]

    assert len(negativos) == 1
    assert negativos.iloc[0]["ingrediente_id"] == "harina"


def test_detecta_orden_duplicada() -> None:
    datos = cargar_datos()
    orden = datos["orden_compra_semana"]
    datos["orden_compra_semana"] = pd.concat(
        [orden, orden.iloc[[0]]],
        ignore_index=True,
    )

    hallazgos = auditar_datos(datos)

    duplicados = hallazgos[
        hallazgos["codigo"].eq("REGISTRO_DUPLICADO")
        & hallazgos["archivo"].eq("orden_compra_semana")
    ]

    assert len(duplicados) == 2
    assert set(duplicados["ingrediente_id"]) == {"harina"}
