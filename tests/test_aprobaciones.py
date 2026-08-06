from __future__ import annotations

import pandas as pd
import pytest

from src.aprobaciones import (
    CONFIANZA_ALTA,
    CONFIANZA_MEDIA,
    CONFIANZA_REVISION,
    DECISION_CATALOGO,
    DECISION_DEVOLVER,
    DECISION_MANTENER,
    ErrorAprobacion,
    aplicar_recomendaciones_alta_confianza,
    clasificar_confianza_operativa,
    construir_casos_aprobacion,
    crear_huella_revision,
    generar_bitacora_decisiones,
    generar_mensaje_proveedor,
    generar_mensaje_sucursal,
    generar_orden_aprobada,
    registrar_decision,
    resumir_aprobacion,
    simular_escenario_demanda,
)
from src.carga_datos import cargar_datos
from src.dashboard import construir_analisis


def _analisis_real():
    return construir_analisis(cargar_datos())


def _revision_completa():
    analisis = _analisis_real()
    casos = construir_casos_aprobacion(analisis.resultados)
    decisiones = aplicar_recomendaciones_alta_confianza(casos)
    desconocido = casos.loc[casos["estado"] == "NO_EVALUABLE"].iloc[0]
    decisiones[str(desconocido["caso_id"])] = registrar_decision(
        desconocido,
        DECISION_CATALOGO,
        motivo_codigo="CORRECCION_CATALOGO",
        fecha_hora="2026-08-06T09:00:00-05:00",
    )
    return analisis, casos, decisiones


def test_confianza_separa_evidencia_y_revision_humana() -> None:
    analisis = _analisis_real()
    casos = construir_casos_aprobacion(analisis.resultados)

    assert (casos["confianza_operativa"] == CONFIANZA_ALTA).sum() == 5
    desconocido = casos.loc[casos["ingrediente_id"] == "aji_chombo"].iloc[0]
    assert desconocido["confianza_operativa"] == CONFIANZA_REVISION

    pepperoni = analisis.resultados.query(
        "sucursal == 'Marbella' and ingrediente_id == 'pepperoni'"
    ).iloc[0]
    assert clasificar_confianza_operativa(pepperoni).nivel == CONFIANZA_MEDIA


def test_aplicacion_masiva_excluye_producto_desconocido() -> None:
    casos = construir_casos_aprobacion(_analisis_real().resultados)
    decisiones = aplicar_recomendaciones_alta_confianza(casos)

    assert len(decisiones) == 5
    desconocido = casos.loc[casos["ingrediente_id"] == "aji_chombo"].iloc[0]
    assert str(desconocido["caso_id"]) not in decisiones


def test_mantener_original_exige_motivo() -> None:
    casos = construir_casos_aprobacion(_analisis_real().resultados)
    caso = casos.loc[casos["ingrediente_id"] == "harina"].iloc[0]

    with pytest.raises(ErrorAprobacion, match="motivo"):
        registrar_decision(caso, DECISION_MANTENER)


def test_orden_aprobada_refleja_decisiones_y_excluye_excepcion() -> None:
    analisis, casos, decisiones = _revision_completa()
    estado = resumir_aprobacion(casos, decisiones)
    orden = generar_orden_aprobada(analisis.evaluacion, casos, decisiones)

    assert estado["lista_para_aprobar"]
    assert estado["lista_con_excepciones"]
    assert estado["excepciones_catalogo"] == 1
    mozzarella = orden.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    ).iloc[0]
    assert mozzarella["cantidad_formatos_aprobada"] == 18
    assert "aji_chombo" not in orden["ingrediente_id"].tolist()


def test_decision_devolver_bloquea_orden_final() -> None:
    analisis = _analisis_real()
    casos = construir_casos_aprobacion(analisis.resultados)
    decisiones = aplicar_recomendaciones_alta_confianza(casos)
    desconocido = casos.loc[casos["estado"] == "NO_EVALUABLE"].iloc[0]
    decisiones[str(desconocido["caso_id"])] = registrar_decision(
        desconocido,
        DECISION_DEVOLVER,
        motivo_codigo="DECISION_GERENCIAL",
    )

    assert not resumir_aprobacion(casos, decisiones)["lista_para_aprobar"]
    with pytest.raises(ErrorAprobacion, match="pendientes o casos devueltos"):
        generar_orden_aprobada(analisis.evaluacion, casos, decisiones)


def test_huella_es_estable_y_cambia_con_la_orden() -> None:
    resultados = _analisis_real().resultados
    huella = crear_huella_revision(resultados)
    reordenados = resultados.sample(frac=1, random_state=7).reset_index(drop=True)
    editados = resultados.copy()
    editados.loc[editados["ingrediente_id"] == "mozzarella", "cantidad_formatos_solicitados"] = 18

    assert crear_huella_revision(reordenados) == huella
    assert crear_huella_revision(editados) != huella


def test_bitacora_y_mensajes_conservan_decisiones_y_tildes() -> None:
    analisis, casos, decisiones = _revision_completa()
    orden = generar_orden_aprobada(analisis.evaluacion, casos, decisiones)
    bitacora = generar_bitacora_decisiones(
        casos,
        decisiones,
        huella_revision=crear_huella_revision(analisis.resultados),
        fuente="Archivo original",
    )
    mensaje_proveedor = generar_mensaje_proveedor(
        orden,
        "Verduras La Huerta",
        semana="S7",
        aprobado=True,
    )
    mensaje_sucursal = generar_mensaje_sucursal(
        casos,
        decisiones,
        "Costa del Este",
        semana="S7",
    )

    assert "cantidad_aprobada" in bitacora.columns
    assert "Piña" in bitacora["nombre"].tolist()
    assert "Piña" in mensaje_proveedor
    assert "ORDEN APROBADA" in mensaje_proveedor
    assert "Harina 00" in mensaje_sucursal
    assert "no fue enviado automáticamente" in mensaje_sucursal


def test_simulador_no_muta_proyecciones_base() -> None:
    analisis = _analisis_real()
    originales = analisis.proyecciones.copy(deep=True)
    escenario = simular_escenario_demanda(
        ingredientes=analisis.datos["ingredientes"],
        inventario_actual=analisis.datos["inventario_actual"],
        orden_compra_semana=analisis.datos["orden_compra_semana"],
        proyecciones=analisis.proyecciones,
        variacion_pct=10,
    )

    pd.testing.assert_frame_equal(analisis.proyecciones, originales)
    assert analisis.resumen["alertas_total"] == 6
    assert escenario.resumen["alertas_total"] == 50
