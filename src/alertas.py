from __future__ import annotations

import math

import pandas as pd

from src.calculos import (
    ESTADO_COMPRA_INNECESARIA,
    ESTADO_CORRECTO,
    ESTADO_INSUFICIENTE,
    ESTADO_NO_EVALUABLE,
    ESTADO_OMITIDO,
    ESTADO_SIN_COMPRA,
    ESTADO_SOBREPEDIDO,
)


class ErrorAlertas(Exception):
    """Error controlado al generar mensajes de alertas."""


PLURALES_FORMATO = {
    "saco": "sacos",
    "bolsa": "bolsas",
    "caja": "cajas",
    "lata": "latas",
    "balde": "baldes",
    "paquete": "paquetes",
    "kilo": "kilos",
    "unidad": "unidades",
    "pieza": "piezas",
}


def _formatear_numero(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return "—"

    numero = float(valor)
    if math.isclose(numero, round(numero), abs_tol=1e-9):
        return str(int(round(numero)))

    return f"{numero:.2f}".rstrip("0").rstrip(".")


def _nombre_formato(formato_compra: object, cantidad: int) -> str:
    if formato_compra is None or pd.isna(formato_compra):
        return "formatos"

    singular = str(formato_compra).strip().split()[0].lower()
    if cantidad == 1:
        return singular

    return PLURALES_FORMATO.get(singular, "formatos")


def _detalle_formatos(
    cantidad: int,
    formato_compra: object,
    cantidad_unidad_base: object,
    unidad_base: object,
) -> str:
    nombre_formato = _nombre_formato(formato_compra, cantidad)
    cantidad_base = _formatear_numero(cantidad_unidad_base)
    unidad = "" if unidad_base is None or pd.isna(unidad_base) else str(unidad_base)
    return f"{cantidad} {nombre_formato} ({cantidad_base} {unidad})".strip()


def generar_mensaje_alerta(fila: pd.Series) -> tuple[str, str, str, bool]:
    estado = str(fila["estado"])
    sucursal = str(fila["sucursal"])
    ingrediente_id = str(fila["ingrediente_id"])
    nombre = str(fila.get("nombre", ingrediente_id))

    if estado == ESTADO_NO_EVALUABLE:
        solicitados = int(fila["cantidad_formatos_solicitados"])
        titulo = "Producto no registrado"
        mensaje = (
            f"{sucursal} solicitó {solicitados} formato(s) de {ingrediente_id}, "
            "pero el ingrediente no existe en el catálogo y no puede evaluarse."
        )
        accion = (
            "Corregir el identificador o registrar el ingrediente, su unidad, "
            "formato y proveedor antes de aprobar la orden."
        )
        return titulo, mensaje, accion, True

    formato = fila["formato_compra"]
    unidad = fila["unidad_base"]
    recomendados = int(fila["formatos_recomendados"])
    solicitados = int(fila["cantidad_formatos_solicitados"])

    if estado == ESTADO_OMITIDO:
        recomendado_base = fila["compra_recomendada_unidad_base"]
        detalle = _detalle_formatos(
            recomendados,
            formato,
            recomendado_base,
            unidad,
        )
        titulo = "Ingrediente omitido"
        mensaje = (
            f"{sucursal} no incluyó {nombre} en la orden, pero se recomiendan "
            f"{detalle} para cubrir el consumo proyectado."
        )
        accion = f"Agregar {detalle} de {nombre} a la orden."
        return titulo, mensaje, accion, True

    if estado == ESTADO_INSUFICIENTE:
        faltantes = int(fila["faltante_formatos"])
        faltante_base = faltantes * float(fila["unidad_base_por_formato"])
        detalle = _detalle_formatos(
            faltantes,
            formato,
            faltante_base,
            unidad,
        )
        titulo = "Pedido insuficiente"
        mensaje = (
            f"{sucursal} solicitó {solicitados} formato(s) de {nombre}, pero "
            f"se recomiendan {recomendados}; faltan {detalle} y existe riesgo "
            "de quiebre durante la semana proyectada."
        )
        accion = f"Aumentar la orden en {detalle} de {nombre}."
        return titulo, mensaje, accion, True

    if estado in {ESTADO_SOBREPEDIDO, ESTADO_COMPRA_INNECESARIA}:
        excesos = int(fila["exceso_formatos"])
        exceso_base = excesos * float(fila["unidad_base_por_formato"])
        detalle = _detalle_formatos(
            excesos,
            formato,
            exceso_base,
            unidad,
        )
        perecedero = bool(fila["es_perecedero_bool"])
        riesgo = (
            "aumenta el riesgo de vencimiento"
            if perecedero
            else "inmoviliza inventario innecesariamente"
        )
        titulo = (
            "Compra innecesaria"
            if estado == ESTADO_COMPRA_INNECESARIA
            else "Sobrepedido"
        )
        mensaje = (
            f"{sucursal} solicitó {solicitados} formato(s) de {nombre}, pero "
            f"se recomiendan {recomendados}; sobran {detalle} y esto {riesgo}."
        )
        accion = f"Reducir la orden en {detalle} de {nombre}."
        return titulo, mensaje, accion, True

    if estado == ESTADO_CORRECTO:
        titulo = "Pedido correcto"
        mensaje = (
            f"{sucursal} solicitó los {solicitados} formato(s) recomendados "
            f"de {nombre}."
        )
        accion = "No se requieren cambios."
        return titulo, mensaje, accion, False

    if estado == ESTADO_SIN_COMPRA:
        titulo = "Sin compra necesaria"
        mensaje = (
            f"El inventario actual de {nombre} en {sucursal} cubre el consumo "
            "proyectado y no se solicitaron formatos adicionales."
        )
        accion = "No se requieren cambios."
        return titulo, mensaje, accion, False

    raise ErrorAlertas(f"Estado de orden desconocido: {estado}")


def agregar_mensajes_alerta(evaluacion: pd.DataFrame) -> pd.DataFrame:
    """Añade títulos, mensajes y acciones a la evaluación de compras."""
    if "estado" not in evaluacion.columns:
        raise ErrorAlertas("La evaluación no contiene la columna estado.")

    resultado = evaluacion.copy()
    mensajes = resultado.apply(generar_mensaje_alerta, axis=1)

    resultado[[
        "titulo_alerta",
        "mensaje_alerta",
        "accion_recomendada",
        "es_alerta",
    ]] = pd.DataFrame(mensajes.tolist(), index=resultado.index)

    resultado["es_alerta"] = resultado["es_alerta"].astype(bool)
    return resultado
