from __future__ import annotations

import pandas as pd

from src.aprobaciones import DECISION_APLICAR, construir_casos_aprobacion, registrar_decision
from src.carga_datos import cargar_datos
from src.dashboard import completar_orden_para_editor, construir_analisis
from src.persistencia import (
    crear_clave_orden,
    normalizar_estado_persistido,
    restaurar_decisiones,
    restaurar_edicion,
    serializar_orden,
)


def test_clave_de_orden_es_estable_ante_el_orden_de_filas() -> None:
    orden = cargar_datos()["orden_compra_semana"]

    assert crear_clave_orden(orden) == crear_clave_orden(
        orden.sample(frac=1, random_state=9)
    )


def test_edicion_guardada_restaura_cantidad_y_descarta_filas_ajenas() -> None:
    datos = cargar_datos()
    plantilla = completar_orden_para_editor(
        datos["orden_compra_semana"],
        datos["consumo_historico"],
        datos["ingredientes"],
    )
    registros = serializar_orden(plantilla)
    for fila in registros:
        if fila["sucursal"] == "Brisas del Golf" and fila["ingrediente_id"] == "mozzarella":
            fila["cantidad_formatos"] = 18
    registros.append(
        {"sucursal": "Sucursal falsa", "ingrediente_id": "harina", "cantidad_formatos": 999}
    )

    restaurada = restaurar_edicion(plantilla, registros)
    mozzarella = restaurada.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    ).iloc[0]

    assert mozzarella["cantidad_formatos"] == 18
    assert "Sucursal falsa" not in restaurada["sucursal"].tolist()


def test_decision_guardada_se_revalida_con_el_analisis_actual() -> None:
    analisis = construir_analisis(cargar_datos())
    casos = construir_casos_aprobacion(analisis.resultados)
    caso = casos.query("ingrediente_id == 'harina'").iloc[0]
    decision = registrar_decision(
        caso,
        DECISION_APLICAR,
        motivo_codigo="RECOMENDACION_SISTEMA",
        fecha_hora="2026-08-09T09:00:00-05:00",
    )
    decision["cantidad_aprobada"] = 999

    restauradas = restaurar_decisiones(casos, {str(caso["caso_id"]): decision})

    assert restauradas[str(caso["caso_id"])]["cantidad_aprobada"] == int(
        caso["formatos_recomendados"]
    )
    assert normalizar_estado_persistido("dato inválido")["revisiones"] == {}
