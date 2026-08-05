import pandas as pd
import pytest

from src.carga_datos import cargar_datos
from src.calculos import (
    ESTADO_INSUFICIENTE,
    ESTADO_NO_EVALUABLE,
    ESTADO_OMITIDO,
    ESTADO_SOBREPEDIDO,
    ErrorCalculoCompras,
    calcular_formatos_recomendados,
    evaluar_ordenes_compra,
)
from src.proyecciones import proyectar_consumo_historico


def _evaluacion_real() -> pd.DataFrame:
    datos = cargar_datos()
    proyecciones = proyectar_consumo_historico(
        datos["consumo_historico"]
    )

    return evaluar_ordenes_compra(
        ingredientes=datos["ingredientes"],
        inventario_actual=datos["inventario_actual"],
        orden_compra_semana=datos["orden_compra_semana"],
        proyecciones=proyecciones,
    )


def test_redondea_a_formatos_completos() -> None:
    assert calcular_formatos_recomendados(0, 25) == 0
    assert calcular_formatos_recomendados(25, 25) == 1
    assert calcular_formatos_recomendados(25.0001, 25) == 2
    assert calcular_formatos_recomendados(5.01, 2.55) == 2
    assert calcular_formatos_recomendados(5.11, 2.55) == 3


def test_evaluacion_real_incluye_88_combinaciones_y_un_desconocido() -> None:
    evaluacion = _evaluacion_real()

    assert len(evaluacion) == 89
    assert (evaluacion["estado"] == ESTADO_NO_EVALUABLE).sum() == 1


def test_mozzarella_omitida_se_recomienda_en_formatos_completos() -> None:
    evaluacion = _evaluacion_real()
    fila = evaluacion.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    ).iloc[0]

    assert fila["estado"] == ESTADO_OMITIDO
    assert fila["cantidad_formatos_solicitados"] == 0
    assert fila["formatos_recomendados"] > 0
    assert fila["orden_enviada"] == False


def test_aji_chombo_no_se_inventa_ni_se_evalua() -> None:
    evaluacion = _evaluacion_real()
    fila = evaluacion.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'aji_chombo'"
    ).iloc[0]

    assert fila["estado"] == ESTADO_NO_EVALUABLE
    assert pd.isna(fila["unidad_base_por_formato"])
    assert pd.isna(fila["formatos_recomendados"])


def test_harina_costa_del_este_es_pedido_insuficiente() -> None:
    evaluacion = _evaluacion_real()
    fila = evaluacion.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'harina'"
    ).iloc[0]

    assert fila["estado"] == ESTADO_INSUFICIENTE
    assert fila["cantidad_formatos_solicitados"] == 6
    assert fila["formatos_recomendados"] == 13
    assert fila["faltante_formatos"] == 7


def test_cebolla_brisas_del_golf_es_sobrepedido() -> None:
    evaluacion = _evaluacion_real()
    fila = evaluacion.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'cebolla'"
    ).iloc[0]

    assert fila["estado"] == ESTADO_SOBREPEDIDO
    assert fila["cantidad_formatos_solicitados"] == 5
    assert fila["formatos_recomendados"] == 2
    assert fila["exceso_formatos"] == 3


def test_rechaza_formatos_fraccionarios() -> None:
    ingredientes = pd.DataFrame(
        {
            "ingrediente_id": ["harina"],
            "nombre": ["Harina"],
            "proveedor": ["Proveedor"],
            "unidad_base": ["kg"],
            "formato_compra": ["Saco 25 kg"],
            "unidad_base_por_formato": [25],
            "es_perecedero": ["No"],
        }
    )
    inventario = pd.DataFrame(
        {
            "sucursal": ["Prueba"],
            "ingrediente_id": ["harina"],
            "stock_actual_unidad_base": [5],
        }
    )
    orden = pd.DataFrame(
        {
            "sucursal": ["Prueba"],
            "ingrediente_id": ["harina"],
            "cantidad_formatos": [1.5],
        }
    )
    proyecciones = pd.DataFrame(
        {
            "sucursal": ["Prueba"],
            "ingrediente_id": ["harina"],
            "consumo_proyectado_unidad_base": [30],
        }
    )

    with pytest.raises(ErrorCalculoCompras, match="fraccionarias"):
        evaluar_ordenes_compra(
            ingredientes,
            inventario,
            orden,
            proyecciones,
        )


def test_resumen_real_consolida_los_estados() -> None:
    from src.calculos import resumir_evaluacion

    resumen = resumir_evaluacion(_evaluacion_real())

    assert resumen["registros_recibidos"] == 89
    assert resumen["combinaciones_evaluables"] == 88
    assert resumen["alertas_total"] == 6
    assert resumen["pedidos_insuficientes"] == 2
    assert resumen["sobrepedidos"] == 2
    assert resumen["ingredientes_omitidos"] == 1
    assert resumen["no_evaluables"] == 1


def test_orden_corregida_excluye_producto_desconocido() -> None:
    from src.calculos import generar_orden_corregida

    orden_corregida = generar_orden_corregida(_evaluacion_real())

    assert "aji_chombo" not in orden_corregida["ingrediente_id"].tolist()
    assert orden_corregida["proveedor"].notna().all()
    assert (
        orden_corregida["cantidad_formatos_recomendada"] > 0
    ).all()
