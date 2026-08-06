from __future__ import annotations

import pandas as pd


NOMBRES_INGREDIENTES_ES: dict[str, str] = {
    "semola": "Sémola",
    "oregano": "Orégano seco",
    "jamon": "Jamón",
    "arugula": "Arúgula",
    "pimenton": "Pimentón",
    "pina": "Piña",
}

NOMBRES_INGREDIENTES_EN: dict[str, str] = {
    "pina": "Pineapple",
}


def nombre_ingrediente_visible(
    ingrediente_id: object,
    nombre: object,
    idioma: str = "es",
) -> str:
    """Devuelve una etiqueta legible sin alterar el identificador técnico."""
    identificador = str(ingrediente_id or "").strip()
    original = str(nombre or identificador).strip()
    mapa = (
        NOMBRES_INGREDIENTES_EN
        if str(idioma).lower().startswith("en")
        else NOMBRES_INGREDIENTES_ES
    )
    return mapa.get(identificador, original)


def aplicar_nombres_visibles(
    dataframe: pd.DataFrame,
    *,
    idioma: str = "es",
    columna_id: str = "ingrediente_id",
    columna_nombre: str = "nombre",
) -> pd.DataFrame:
    """Aplica etiquetas a una copia y conserva intactas las claves de negocio."""
    resultado = dataframe.copy()
    if columna_id not in resultado.columns:
        return resultado

    if columna_nombre not in resultado.columns:
        resultado[columna_nombre] = resultado[columna_id]

    resultado[columna_nombre] = [
        nombre_ingrediente_visible(ingrediente_id, nombre, idioma)
        for ingrediente_id, nombre in zip(
            resultado[columna_id],
            resultado[columna_nombre],
            strict=True,
        )
    ]
    return resultado


def reemplazar_nombre_visible(
    texto: object,
    *,
    ingrediente_id: object,
    nombre_original: object,
    idioma: str = "es",
) -> str:
    """Sustituye solo la etiqueta descriptiva; nunca reemplaza el ID."""
    contenido = str(texto)
    original = str(nombre_original)
    visible = nombre_ingrediente_visible(ingrediente_id, original, idioma)
    if original and original != visible:
        return contenido.replace(original, visible)
    return contenido
