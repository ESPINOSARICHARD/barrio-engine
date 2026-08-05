from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


ARCHIVOS_REQUERIDOS: dict[str, str] = {
    "ingredientes": "ingredientes.csv",
    "consumo_historico": "consumo_historico.csv",
    "inventario_actual": "inventario_actual.csv",
    "orden_compra_semana": "orden_compra_semana.csv",
}


class ErrorCargaDatos(Exception):
    """Error controlado al localizar o leer los archivos del proyecto."""


def _normalizar_columnas(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Elimina espacios y marcas BOM de los encabezados sin cambiar los datos."""
    copia = dataframe.copy()

    copia.columns = [
        str(columna).strip().lstrip("\ufeff")
        for columna in copia.columns
    ]

    return copia


def cargar_csv(ruta: Path) -> pd.DataFrame:
    """Carga un archivo CSV en UTF-8 con BOM."""

    if not ruta.exists():
        raise ErrorCargaDatos(
            f"No se encontró el archivo requerido: {ruta.name}"
        )

    if not ruta.is_file():
        raise ErrorCargaDatos(
            f"La ruta no corresponde a un archivo: {ruta}"
        )

    if ruta.stat().st_size == 0:
        raise ErrorCargaDatos(
            f"El archivo está vacío: {ruta.name}"
        )

    try:
        dataframe = pd.read_csv(
            ruta,
            encoding="utf-8-sig",
        )

    except EmptyDataError as error:
        raise ErrorCargaDatos(
            f"El archivo no contiene datos: {ruta.name}"
        ) from error

    except ParserError as error:
        raise ErrorCargaDatos(
            f"El archivo tiene una estructura CSV inválida: {ruta.name}"
        ) from error

    except UnicodeDecodeError as error:
        raise ErrorCargaDatos(
            f"No se pudo leer la codificación del archivo: {ruta.name}"
        ) from error

    except OSError as error:
        raise ErrorCargaDatos(
            f"No se pudo abrir el archivo: {ruta.name}"
        ) from error

    return _normalizar_columnas(dataframe)


def cargar_datos(
    directorio_datos: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Carga los cuatro archivos requeridos del proyecto."""

    if directorio_datos is None:
        raiz_proyecto = Path(__file__).resolve().parent.parent
        directorio = raiz_proyecto / "datos"
    else:
        directorio = Path(directorio_datos).expanduser().resolve()

    if not directorio.exists():
        raise ErrorCargaDatos(
            f"No se encontró la carpeta de datos: {directorio}"
        )

    if not directorio.is_dir():
        raise ErrorCargaDatos(
            f"La ruta indicada no corresponde a una carpeta: {directorio}"
        )

    return {
        nombre: cargar_csv(directorio / archivo)
        for nombre, archivo in ARCHIVOS_REQUERIDOS.items()
    }