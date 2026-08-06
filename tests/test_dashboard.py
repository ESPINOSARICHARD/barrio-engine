from __future__ import annotations

import pandas as pd

from src.carga_datos import cargar_datos
from src.dashboard import (
    completar_orden_para_editor,
    construir_analisis,
    dataframe_a_csv_bytes,
    filtrar_resultados,
    porcentaje_orden_correcta,
    preparar_orden_por_proveedor,
    preparar_reparacion_orden,
    preparar_serie_detalle,
)


def _analisis_real():
    return construir_analisis(cargar_datos())


def test_construye_el_analisis_completo_del_reto() -> None:
    analisis = _analisis_real()

    assert analisis.resumen["alertas_total"] == 6
    assert len(analisis.resultados) == 89
    assert len(analisis.orden_corregida) > 0
    assert "aji_chombo" not in analisis.orden_corregida["ingrediente_id"].tolist()


def test_filtro_de_alertas_conserva_solo_prioridad_critica() -> None:
    analisis = _analisis_real()
    filtradas = filtrar_resultados(
        analisis.resultados,
        solo_alertas=True,
        prioridades=["CRITICA"],
    )

    assert len(filtradas) == 2
    assert set(filtradas["estado"]) == {
        "INGREDIENTE_OMITIDO",
        "NO_EVALUABLE",
    }


def test_editor_completa_mozzarella_y_conserva_aji_chombo() -> None:
    datos = cargar_datos()
    orden = completar_orden_para_editor(
        datos["orden_compra_semana"],
        datos["consumo_historico"],
        datos["ingredientes"],
    )

    mozzarella = orden.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    )
    aji = orden.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'aji_chombo'"
    )

    assert len(orden) == 89
    assert len(mozzarella) == 1
    assert mozzarella.iloc[0]["cantidad_formatos"] == 0
    assert len(aji) == 1
    assert aji.iloc[0]["cantidad_formatos"] == 3


def test_serie_de_pepperoni_marca_s3_y_agrega_proyeccion() -> None:
    analisis = _analisis_real()
    serie = preparar_serie_detalle(
        analisis.datos["consumo_historico"],
        analisis.proyecciones,
        sucursal="Marbella",
        ingrediente_id="pepperoni",
    )

    assert len(serie) == 7
    assert serie.iloc[-1]["semana"] == "S7"
    assert serie.iloc[-1]["tipo"] == "Proyección"
    assert serie.loc[serie["semana"] == "S3", "es_atipico"].iloc[0]


def test_orden_por_proveedor_mantiene_orden_estable() -> None:
    analisis = _analisis_real()
    proveedores = analisis.orden_corregida["proveedor"].dropna().unique().tolist()
    proveedor = proveedores[0]

    filtrada = preparar_orden_por_proveedor(
        analisis.orden_corregida,
        proveedores=[proveedor],
    )

    assert not filtrada.empty
    assert set(filtrada["proveedor"]) == {proveedor}
    esperada = filtrada.sort_values(
        ["proveedor", "sucursal", "nombre"], kind="stable"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(filtrada, esperada)


def test_csv_de_descarga_incluye_bom_para_excel() -> None:
    contenido = dataframe_a_csv_bytes(
        pd.DataFrame({"nombre": ["Piña", "Mozzarella"]})
    )

    assert contenido.startswith(b"\xef\xbb\xbf")
    assert "Piña" in contenido.decode("utf-8-sig")


def test_porcentaje_correcto_del_reto() -> None:
    analisis = _analisis_real()
    assert porcentaje_orden_correcta(analisis.resumen) == 94.3


def test_editar_mozzarella_recalcula_y_elimina_una_alerta() -> None:
    datos = cargar_datos()
    orden = completar_orden_para_editor(
        datos["orden_compra_semana"],
        datos["consumo_historico"],
        datos["ingredientes"],
    )
    mascara = (
        (orden["sucursal"] == "Brisas del Golf")
        & (orden["ingrediente_id"] == "mozzarella")
    )
    orden.loc[mascara, "cantidad_formatos"] = 18

    analisis = construir_analisis(datos, orden_compra=orden)

    assert analisis.resumen["alertas_total"] == 5
    mozzarella = analisis.resultados.loc[mascara].iloc[0]
    assert mozzarella["estado"] == "CORRECTO"


def test_reparador_completa_mozzarella_y_separa_aji_chombo() -> None:
    datos = cargar_datos()
    plantilla, excepciones, reporte = preparar_reparacion_orden(
        datos["orden_compra_semana"],
        datos["consumo_historico"],
        datos["ingredientes"],
    )

    assert len(plantilla) == 88
    mozzarella = plantilla.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    ).iloc[0]
    assert mozzarella["cantidad_formatos"] == 0
    assert excepciones["ingrediente_id"].tolist() == ["aji_chombo"]
    assert set(reporte["accion"]) == {
        "COMBINACION_AGREGADA_CON_CERO",
        "FILA_SEPARADA_PARA_REVISION",
    }
