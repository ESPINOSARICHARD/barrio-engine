import pandas as pd

from src.alertas import agregar_mensajes_alerta
from src.carga_datos import cargar_datos
from src.calculos import evaluar_ordenes_compra
from src.proyecciones import proyectar_consumo_historico


def _resultado_real() -> pd.DataFrame:
    datos = cargar_datos()
    proyecciones = proyectar_consumo_historico(
        datos["consumo_historico"]
    )
    evaluacion = evaluar_ordenes_compra(
        datos["ingredientes"],
        datos["inventario_actual"],
        datos["orden_compra_semana"],
        proyecciones,
    )
    return agregar_mensajes_alerta(evaluacion)


def test_alerta_mozzarella_es_clara_y_accionable() -> None:
    resultado = _resultado_real()
    fila = resultado.query(
        "sucursal == 'Brisas del Golf' and ingrediente_id == 'mozzarella'"
    ).iloc[0]

    assert fila["es_alerta"]
    assert fila["titulo_alerta"] == "Ingrediente omitido"
    assert "no incluyó Mozzarella" in fila["mensaje_alerta"]
    assert "Agregar" in fila["accion_recomendada"]


def test_alerta_aji_chombo_no_inventa_informacion() -> None:
    resultado = _resultado_real()
    fila = resultado.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'aji_chombo'"
    ).iloc[0]

    assert fila["es_alerta"]
    assert fila["titulo_alerta"] == "Producto no registrado"
    assert "no existe en el catálogo" in fila["mensaje_alerta"]
    assert "registrar el ingrediente" in fila["accion_recomendada"]


def test_alerta_harina_indica_faltante_exacto() -> None:
    resultado = _resultado_real()
    fila = resultado.query(
        "sucursal == 'Costa del Este' and ingrediente_id == 'harina'"
    ).iloc[0]

    assert "faltan 7 sacos (175 kg)" in fila["mensaje_alerta"]
    assert "Aumentar la orden" in fila["accion_recomendada"]


def test_pedidos_correctos_no_se_marcan_como_alerta() -> None:
    resultado = _resultado_real()
    correctos = resultado.loc[resultado["estado"] == "CORRECTO"]

    assert not correctos.empty
    assert (~correctos["es_alerta"]).all()
