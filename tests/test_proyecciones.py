import numpy as np
import pandas as pd
import pytest

from src.carga_datos import cargar_datos
from src.proyecciones import (
    ErrorProyeccion,
    METODO_PROMEDIO_ROBUSTO,
    METODO_TENDENCIA,
    detectar_atipicos_mad,
    proyectar_consumo_historico,
    proyectar_serie,
)


def test_detecta_semana_atipica_del_pepperoni() -> None:
    valores = [28, 30, 150, 27, 29, 31]

    mascara = detectar_atipicos_mad(valores)

    assert mascara.tolist() == [False, False, True, False, False, False]


def test_harina_costa_del_este_usa_tendencia() -> None:
    valores = [240, 255, 268, 284, 300, 316]

    resultado = proyectar_serie(valores)

    assert resultado.metodo == METODO_TENDENCIA
    assert resultado.consumo_proyectado == pytest.approx(330.2667, abs=0.001)
    assert resultado.r2_tendencia > 0.99
    assert resultado.cantidad_atipicos == 0


def test_pepperoni_marbella_usa_metodo_robusto() -> None:
    valores = [28, 30, 150, 27, 29, 31]
    semanas = ["S1", "S2", "S3", "S4", "S5", "S6"]

    resultado = proyectar_serie(valores, semanas)

    assert resultado.metodo == METODO_PROMEDIO_ROBUSTO
    assert resultado.consumo_proyectado == pytest.approx(29.2778, abs=0.001)
    assert resultado.semanas_atipicas == ("S3",)
    assert resultado.cantidad_atipicos == 1


def test_proyecta_las_88_combinaciones_reales() -> None:
    datos = cargar_datos()

    proyecciones = proyectar_consumo_historico(
        datos["consumo_historico"]
    )

    assert len(proyecciones) == 88
    assert not proyecciones.duplicated(
        subset=["sucursal", "ingrediente_id"]
    ).any()
    assert (proyecciones["semanas_usadas"] == 6).all()


def test_resultados_reales_identifican_los_casos_clave() -> None:
    datos = cargar_datos()
    proyecciones = proyectar_consumo_historico(
        datos["consumo_historico"]
    )

    harina = proyecciones.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'harina'"
    ).iloc[0]
    pepperoni = proyecciones.query(
        "sucursal == 'Marbella' and ingrediente_id == 'pepperoni'"
    ).iloc[0]

    assert harina["metodo_proyeccion"] == METODO_TENDENCIA
    assert harina["consumo_proyectado_unidad_base"] == pytest.approx(
        330.2667,
        abs=0.001,
    )
    assert pepperoni["metodo_proyeccion"] == METODO_PROMEDIO_ROBUSTO
    assert pepperoni["semanas_atipicas"] == "S3"


def test_ninguna_proyeccion_real_es_negativa() -> None:
    datos = cargar_datos()
    proyecciones = proyectar_consumo_historico(
        datos["consumo_historico"]
    )

    assert (
        proyecciones["consumo_proyectado_unidad_base"] >= 0
    ).all()
    assert np.isfinite(
        proyecciones["consumo_proyectado_unidad_base"]
    ).all()


def test_rechaza_consumos_negativos() -> None:
    historico = pd.DataFrame(
        {
            "sucursal": ["Prueba"] * 3,
            "ingrediente_id": ["harina"] * 3,
            "semana": ["S1", "S2", "S3"],
            "consumo_unidad_base": [10, -2, 12],
        }
    )

    with pytest.raises(ErrorProyeccion, match="negativos"):
        proyectar_consumo_historico(historico)
