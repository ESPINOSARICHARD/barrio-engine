from pathlib import Path

import pandas as pd
import pytest

from src.carga_datos import (
    ARCHIVOS_REQUERIDOS,
    ErrorCargaDatos,
    cargar_datos,
)


def test_carga_los_cuatro_archivos_reales() -> None:
    datos = cargar_datos()

    assert set(datos) == set(ARCHIVOS_REQUERIDOS)

    assert all(
        isinstance(dataframe, pd.DataFrame)
        for dataframe in datos.values()
    )

    assert all(
        not dataframe.empty
        for dataframe in datos.values()
    )


def test_detecta_archivos_requeridos_faltantes(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ErrorCargaDatos,
        match="ingredientes.csv",
    ):
        cargar_datos(tmp_path)


def test_los_encabezados_no_conservan_bom() -> None:
    datos = cargar_datos()

    for dataframe in datos.values():
        assert all(
            not columna.startswith("\ufeff")
            for columna in dataframe.columns
        )