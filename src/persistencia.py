from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

import pandas as pd

from src.aprobaciones import ErrorAprobacion, registrar_decision


VERSION_ESTADO = 1
COLUMNAS_ORDEN = ["sucursal", "ingrediente_id", "cantidad_formatos"]


def estado_persistido_vacio() -> dict[str, object]:
    """Crea la estructura mínima almacenada en el navegador."""
    return {
        "version": VERSION_ESTADO,
        "fuente_activa": {"tipo": "reto"},
        "editores": {},
        "revisiones": {},
    }


def normalizar_estado_persistido(valor: object) -> dict[str, object]:
    """Acepta únicamente las secciones conocidas del estado del navegador."""
    estado = estado_persistido_vacio()
    if not isinstance(valor, Mapping):
        return estado

    fuente = valor.get("fuente_activa")
    if isinstance(fuente, Mapping) and fuente.get("tipo") in {"reto", "csv"}:
        estado["fuente_activa"] = dict(fuente)

    editores = valor.get("editores")
    if isinstance(editores, Mapping):
        estado["editores"] = {
            str(clave): dict(registro)
            for clave, registro in editores.items()
            if isinstance(registro, Mapping)
        }

    revisiones = valor.get("revisiones")
    if isinstance(revisiones, Mapping):
        estado["revisiones"] = {
            str(clave): dict(registro)
            for clave, registro in revisiones.items()
            if isinstance(registro, Mapping)
        }
    return estado


def serializar_orden(orden: pd.DataFrame) -> list[dict[str, object]]:
    """Convierte una orden validada en registros pequeños y serializables."""
    if not set(COLUMNAS_ORDEN).issubset(orden.columns):
        return []
    trabajo = orden[COLUMNAS_ORDEN].copy()
    trabajo["sucursal"] = trabajo["sucursal"].astype(str)
    trabajo["ingrediente_id"] = trabajo["ingrediente_id"].astype(str)
    trabajo["cantidad_formatos"] = pd.to_numeric(
        trabajo["cantidad_formatos"], errors="coerce"
    )
    trabajo = trabajo.dropna(subset=["cantidad_formatos"])
    trabajo["cantidad_formatos"] = trabajo["cantidad_formatos"].round().astype(int)
    return trabajo.to_dict(orient="records")


def crear_clave_orden(orden: pd.DataFrame) -> str:
    """Identifica la fuente sin depender del nombre del archivo."""
    registros = sorted(
        serializar_orden(orden),
        key=lambda fila: (str(fila["sucursal"]), str(fila["ingrediente_id"])),
    )
    contenido = json.dumps(
        registros,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(contenido.encode("utf-8")).hexdigest()


def restaurar_orden_guardada(registros: object) -> pd.DataFrame | None:
    """Reconstruye una orden cargada y rechaza datos manipulados o incompletos."""
    if not isinstance(registros, list) or not registros or len(registros) > 5000:
        return None
    orden = pd.DataFrame(registros)
    if not set(COLUMNAS_ORDEN).issubset(orden.columns):
        return None
    orden = orden[COLUMNAS_ORDEN].copy()
    orden["sucursal"] = orden["sucursal"].astype(str).str.strip()
    orden["ingrediente_id"] = orden["ingrediente_id"].astype(str).str.strip()
    cantidades = pd.to_numeric(orden["cantidad_formatos"], errors="coerce")
    validas = (
        cantidades.notna()
        & (cantidades >= 0)
        & ((cantidades - cantidades.round()).abs() < 1e-9)
        & orden["sucursal"].ne("")
        & orden["ingrediente_id"].ne("")
    )
    if not bool(validas.all()):
        return None
    orden["cantidad_formatos"] = cantidades.round().astype(int)
    if orden.duplicated(["sucursal", "ingrediente_id"]).any():
        return None
    return orden.reset_index(drop=True)


def restaurar_edicion(
    plantilla: pd.DataFrame,
    registros: object,
) -> pd.DataFrame:
    """Aplica solo cantidades válidas sobre las filas autorizadas de la plantilla."""
    resultado = plantilla.copy()
    guardada = restaurar_orden_guardada(registros)
    if guardada is None:
        return resultado

    cantidades = {
        (fila.sucursal, fila.ingrediente_id): int(fila.cantidad_formatos)
        for fila in guardada.itertuples(index=False)
    }
    for indice, fila in resultado.iterrows():
        clave = (str(fila["sucursal"]), str(fila["ingrediente_id"]))
        if clave in cantidades:
            resultado.at[indice, "cantidad_formatos"] = cantidades[clave]
    return resultado


def restaurar_decisiones(
    casos: pd.DataFrame,
    registros: object,
) -> dict[str, dict[str, object]]:
    """Revalida decisiones del navegador contra los casos calculados actuales."""
    if not isinstance(registros, Mapping):
        return {}

    restauradas: dict[str, dict[str, object]] = {}
    for _, caso in casos.iterrows():
        caso_id = str(caso["caso_id"])
        registro = registros.get(caso_id)
        if not isinstance(registro, Mapping):
            continue
        try:
            restaurada = registrar_decision(
                caso,
                str(registro.get("decision", "")),
                motivo_codigo=str(registro.get("motivo_codigo", "")),
                motivo_detalle=str(registro.get("motivo_detalle", "")),
                responsable=str(registro.get("responsable", "")),
                fecha_hora=(
                    str(registro["fecha_hora"])
                    if registro.get("fecha_hora")
                    else None
                ),
            )
        except (ErrorAprobacion, TypeError, ValueError):
            continue
        restauradas[caso_id] = restaurada
    return restauradas
