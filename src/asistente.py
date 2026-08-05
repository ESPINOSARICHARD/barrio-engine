from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import pandas as pd

from src.dashboard import AnalisisCompras, ESTADO_ETIQUETAS, PRIORIDAD_ETIQUETAS


MODELO_GEMINI_PREDETERMINADO = "gemini-2.5-flash"


class ErrorAsistente(Exception):
    """Error controlado al preparar o responder una consulta del asistente."""


@dataclass(frozen=True)
class RespuestaAsistente:
    respuesta: str
    modo: str
    intencion: str
    evidencia: tuple[str, ...]
    advertencia: str | None = None


def normalizar_texto(texto: object) -> str:
    """Normaliza tildes, mayúsculas y signos para comparar preguntas."""
    valor = unicodedata.normalize("NFKD", str(texto))
    valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
    valor = valor.lower().replace("_", " ")
    valor = re.sub(r"[^a-z0-9]+", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def _formatear_numero(valor: object, decimales: int = 2) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    numero = float(valor)
    if not math.isfinite(numero):
        return "—"
    if math.isclose(numero, round(numero), abs_tol=1e-9):
        return f"{int(round(numero)):,}"
    return f"{numero:,.{decimales}f}".rstrip("0").rstrip(".")


def _plural_formato(formato_compra: object, cantidad: int) -> str:
    if formato_compra is None or pd.isna(formato_compra):
        return "formatos"
    singular = str(formato_compra).strip().split()[0].lower()
    if cantidad == 1:
        return singular
    plurales = {
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
    return plurales.get(singular, "formatos")


def _contiene_alguno(texto: str, expresiones: Iterable[str]) -> bool:
    return any(expresion in texto for expresion in expresiones)


def _encontrar_entidad(
    pregunta_normalizada: str,
    pares: Iterable[tuple[str, str]],
) -> str | None:
    """Encuentra la entidad cuyo alias más largo está contenido en la pregunta."""
    coincidencias: list[tuple[int, str]] = []
    for valor, alias in pares:
        alias_normalizado = normalizar_texto(alias)
        if alias_normalizado and alias_normalizado in pregunta_normalizada:
            coincidencias.append((len(alias_normalizado), valor))
    if not coincidencias:
        return None
    coincidencias.sort(reverse=True)
    return coincidencias[0][1]


def _detectar_sucursal(pregunta: str, analisis: AnalisisCompras) -> str | None:
    sucursales = sorted(
        analisis.resultados["sucursal"].dropna().astype(str).unique().tolist()
    )
    pares: list[tuple[str, str]] = []
    for sucursal in sucursales:
        pares.append((sucursal, sucursal))
        normalizada = normalizar_texto(sucursal)
        if normalizada == "via argentina":
            pares.extend([(sucursal, "vía argentina"), (sucursal, "argentina")])
        elif normalizada == "brisas del golf":
            pares.extend([(sucursal, "brisas"), (sucursal, "brisas del golf")])
        elif normalizada == "costa del este":
            pares.extend([(sucursal, "costa"), (sucursal, "costa del este")])
    return _encontrar_entidad(pregunta, pares)


def _detectar_ingrediente(pregunta: str, analisis: AnalisisCompras) -> str | None:
    catalogo = analisis.datos["ingredientes"]
    pares: list[tuple[str, str]] = []
    for fila in catalogo.itertuples(index=False):
        ingrediente_id = str(fila.ingrediente_id)
        nombre = str(fila.nombre)
        pares.extend(
            [
                (ingrediente_id, ingrediente_id),
                (ingrediente_id, nombre),
            ]
        )

    alias_adicionales = {
        "harina": ["harina 00", "harina normal"],
        "harina_gf": ["harina gluten free", "harina sin gluten"],
        "salsa_pelatti": ["salsa pelatti", "pelatti"],
        "aceite_oliva": ["aceite de oliva"],
        "queso_vegano": ["queso vegano"],
        "cajas_pizza": ["cajas de pizza", "caja de pizza"],
        "pina": ["piña", "pina"],
        "jamon": ["jamón", "jamon"],
        "oregano": ["orégano", "oregano"],
        "semola": ["sémola", "semola"],
        "pimenton": ["pimentón", "pimenton"],
        "arugula": ["rúcula", "rucula", "arúgula", "arugula"],
    }
    for ingrediente_id, alias in alias_adicionales.items():
        pares.extend((ingrediente_id, valor) for valor in alias)

    return _encontrar_entidad(pregunta, pares)


def _filas_relevantes(
    analisis: AnalisisCompras,
    sucursal: str | None,
    ingrediente_id: str | None,
) -> pd.DataFrame:
    filas = analisis.resultados.copy()
    if sucursal is not None:
        filas = filas.loc[filas["sucursal"] == sucursal]
    if ingrediente_id is not None:
        filas = filas.loc[filas["ingrediente_id"] == ingrediente_id]
    return filas.reset_index(drop=True)


def _respuesta_recomendacion(
    filas: pd.DataFrame,
    sucursal: str | None,
    ingrediente_id: str,
) -> tuple[str, tuple[str, ...]]:
    evaluables = filas.loc[filas["estado"] != "NO_EVALUABLE"].copy()
    if evaluables.empty:
        return (
            "Ese producto no puede evaluarse con los datos disponibles porque no está registrado correctamente en el catálogo.",
            ("Producto no evaluable",),
        )

    lineas: list[str] = []
    evidencia: list[str] = []
    for fila in evaluables.itertuples(index=False):
        recomendados = int(fila.formatos_recomendados)
        unidad = str(fila.unidad_base)
        cantidad_base = float(fila.compra_recomendada_unidad_base)
        formato = _plural_formato(fila.formato_compra, recomendados)
        solicitado = int(fila.cantidad_formatos_solicitados)
        estado = ESTADO_ETIQUETAS.get(str(fila.estado), str(fila.estado))
        lineas.append(
            f"{fila.sucursal}: recomiendo {recomendados} {formato} "
            f"({_formatear_numero(cantidad_base)} {unidad}). La orden actual tiene "
            f"{solicitado} y el resultado es {estado.lower()}."
        )
        evidencia.append(
            f"{fila.sucursal} | proyectado={_formatear_numero(fila.consumo_proyectado_unidad_base)} {unidad} | "
            f"inventario={_formatear_numero(fila.stock_actual_unidad_base)} {unidad} | "
            f"recomendado={recomendados} {formato}"
        )

    nombre = str(evaluables.iloc[0]["nombre"])
    if sucursal is not None:
        encabezado = f"Para {nombre} en {sucursal}:"
    else:
        encabezado = f"Recomendación de compra para {nombre} por sucursal:"
    return encabezado + "\n\n" + "\n".join(f"- {linea}" for linea in lineas), tuple(evidencia)


def _respuesta_inventario(
    filas: pd.DataFrame,
    sucursal: str | None,
    ingrediente_id: str,
) -> tuple[str, tuple[str, ...]]:
    evaluables = filas.loc[filas["estado"] != "NO_EVALUABLE"].copy()
    if evaluables.empty:
        return "No hay inventario evaluable para ese producto.", ("Sin inventario evaluable",)
    nombre = str(evaluables.iloc[0]["nombre"])
    lineas = [
        f"{fila.sucursal}: {_formatear_numero(fila.stock_actual_unidad_base)} {fila.unidad_base}."
        for fila in evaluables.itertuples(index=False)
    ]
    evidencia = tuple(
        f"{fila.sucursal} | stock={_formatear_numero(fila.stock_actual_unidad_base)} {fila.unidad_base}"
        for fila in evaluables.itertuples(index=False)
    )
    encabezado = (
        f"Inventario actual de {nombre} en {sucursal}:"
        if sucursal
        else f"Inventario actual de {nombre} por sucursal:"
    )
    return encabezado + "\n\n" + "\n".join(f"- {linea}" for linea in lineas), evidencia


def _respuesta_proyeccion(
    filas: pd.DataFrame,
    sucursal: str | None,
    ingrediente_id: str,
) -> tuple[str, tuple[str, ...]]:
    evaluables = filas.loc[filas["estado"] != "NO_EVALUABLE"].copy()
    if evaluables.empty:
        return "No existe una proyección válida para ese producto.", ("Sin proyección válida",)
    nombre = str(evaluables.iloc[0]["nombre"])
    lineas: list[str] = []
    evidencia: list[str] = []
    for fila in evaluables.itertuples(index=False):
        lineas.append(
            f"{fila.sucursal}: {_formatear_numero(fila.consumo_proyectado_unidad_base)} {fila.unidad_base}."
        )
        evidencia.append(
            f"{fila.sucursal} | consumo_proyectado={_formatear_numero(fila.consumo_proyectado_unidad_base)} {fila.unidad_base}"
        )
    encabezado = (
        f"Consumo proyectado de {nombre} en {sucursal}:"
        if sucursal
        else f"Consumo proyectado de {nombre} por sucursal:"
    )
    return encabezado + "\n\n" + "\n".join(f"- {linea}" for linea in lineas), tuple(evidencia)


def _respuesta_proveedor(
    analisis: AnalisisCompras,
    ingrediente_id: str,
) -> tuple[str, tuple[str, ...]]:
    catalogo = analisis.datos["ingredientes"]
    fila = catalogo.loc[catalogo["ingrediente_id"] == ingrediente_id]
    if fila.empty:
        return "Ese ingrediente no está registrado en el catálogo.", ("Ingrediente fuera del catálogo",)
    registro = fila.iloc[0]
    respuesta = (
        f"{registro['nombre']} se compra a **{registro['proveedor']}** en el formato "
        f"**{registro['formato_compra']}**."
    )
    evidencia = (
        f"ingrediente={registro['nombre']} | proveedor={registro['proveedor']} | formato={registro['formato_compra']}",
    )
    return respuesta, evidencia


def _respuesta_alertas(
    analisis: AnalisisCompras,
    sucursal: str | None,
    tipo: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    alertas = analisis.resultados.loc[analisis.resultados["es_alerta"].fillna(False)].copy()
    if sucursal is not None:
        alertas = alertas.loc[alertas["sucursal"] == sucursal]
    if tipo == "faltantes":
        alertas = alertas.loc[
            alertas["estado"].isin(["PEDIDO_INSUFICIENTE", "INGREDIENTE_OMITIDO"])
        ]
    elif tipo == "excesos":
        alertas = alertas.loc[
            alertas["estado"].isin(["SOBREPEDIDO", "COMPRA_INNECESARIA"])
        ]

    orden_prioridad = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2}
    alertas = alertas.assign(
        _orden=alertas["prioridad"].map(orden_prioridad).fillna(9)
    ).sort_values(["_orden", "sucursal", "nombre"], kind="stable")

    if alertas.empty:
        alcance = f" en {sucursal}" if sucursal else ""
        return f"No encontré alertas de ese tipo{alcance}.", ("0 alertas",)

    lineas: list[str] = []
    evidencia: list[str] = []
    for fila in alertas.itertuples(index=False):
        prioridad = PRIORIDAD_ETIQUETAS.get(str(fila.prioridad), str(fila.prioridad))
        lineas.append(
            f"**{prioridad} · {fila.sucursal} · {fila.nombre}:** {fila.accion_recomendada}"
        )
        evidencia.append(
            f"{fila.prioridad} | {fila.sucursal} | {fila.ingrediente_id} | {fila.estado} | {fila.accion_recomendada}"
        )

    titulo = "Alertas detectadas"
    if tipo == "faltantes":
        titulo = "Pedidos insuficientes e ingredientes omitidos"
    elif tipo == "excesos":
        titulo = "Sobrepedidos y compras innecesarias"
    if sucursal:
        titulo += f" en {sucursal}"
    return f"{titulo} ({len(alertas)}):\n\n" + "\n".join(f"- {linea}" for linea in lineas), tuple(evidencia)


def _respuesta_conteo(
    pregunta: str,
    analisis: AnalisisCompras,
) -> tuple[str, tuple[str, ...], str]:
    resumen = analisis.resumen
    if _contiene_alguno(pregunta, ["proveedor", "proveedores"]):
        cantidad = int(analisis.datos["ingredientes"]["proveedor"].nunique())
        return f"Hay **{cantidad} proveedores** registrados en el catálogo.", (f"proveedores={cantidad}",), "conteo_proveedores"
    if _contiene_alguno(pregunta, ["sucursal", "sucursales", "locales"]):
        cantidad = int(analisis.resultados["sucursal"].nunique())
        return f"El análisis actual incluye **{cantidad} sucursales**.", (f"sucursales={cantidad}",), "conteo_sucursales"
    if _contiene_alguno(pregunta, ["ingrediente", "ingredientes", "productos"]):
        cantidad = int(len(analisis.datos["ingredientes"]))
        return f"El catálogo contiene **{cantidad} ingredientes válidos**.", (f"ingredientes={cantidad}",), "conteo_ingredientes"
    if _contiene_alguno(pregunta, ["alerta", "alertas", "problemas"]):
        cantidad = int(resumen["alertas_total"])
        return (
            f"Hay **{cantidad} alertas por revisar**: {resumen['prioridad_critica']} críticas, "
            f"{resumen['prioridad_alta']} altas y {resumen['prioridad_media']} de prioridad media.",
            (
                f"alertas_total={cantidad}",
                f"criticas={resumen['prioridad_critica']}",
                f"altas={resumen['prioridad_alta']}",
                f"medias={resumen['prioridad_media']}",
            ),
            "conteo_alertas",
        )
    return "", (), ""


def responder_local(
    pregunta: str,
    analisis: AnalisisCompras,
) -> RespuestaAsistente:
    """Responde preguntas frecuentes exclusivamente con resultados calculados."""
    pregunta_normalizada = normalizar_texto(pregunta)
    if not pregunta_normalizada:
        raise ErrorAsistente("La pregunta está vacía.")

    sucursal = _detectar_sucursal(pregunta_normalizada, analisis)
    ingrediente_id = _detectar_ingrediente(pregunta_normalizada, analisis)
    filas = _filas_relevantes(analisis, sucursal, ingrediente_id)

    es_conteo = _contiene_alguno(
        pregunta_normalizada,
        ["cuantos", "cuantas", "cantidad de", "numero de", "total de"],
    )
    if es_conteo and ingrediente_id is None:
        respuesta, evidencia, intencion = _respuesta_conteo(pregunta_normalizada, analisis)
        if respuesta:
            return RespuestaAsistente(respuesta, "local", intencion, evidencia)

    if ingrediente_id and _contiene_alguno(
        pregunta_normalizada,
        ["proveedor", "provee", "quien vende", "quien suministra", "donde se compra"],
    ):
        respuesta, evidencia = _respuesta_proveedor(analisis, ingrediente_id)
        return RespuestaAsistente(respuesta, "local", "proveedor_ingrediente", evidencia)

    if ingrediente_id and _contiene_alguno(
        pregunta_normalizada,
        ["inventario", "stock", "existencia", "disponible", "hay actualmente"],
    ):
        respuesta, evidencia = _respuesta_inventario(filas, sucursal, ingrediente_id)
        return RespuestaAsistente(respuesta, "local", "inventario", evidencia)

    if ingrediente_id and _contiene_alguno(
        pregunta_normalizada,
        ["proyect", "consumo", "demanda", "espera consumir"],
    ) and not _contiene_alguno(pregunta_normalizada, ["comprar", "pedir", "ordenar", "recomiend"]):
        respuesta, evidencia = _respuesta_proyeccion(filas, sucursal, ingrediente_id)
        return RespuestaAsistente(respuesta, "local", "proyeccion", evidencia)

    if ingrediente_id and _contiene_alguno(
        pregunta_normalizada,
        [
            "comprar",
            "pedir",
            "ordenar",
            "recomiend",
            "necesita",
            "necesito",
            "cuanto",
            "cuanta",
            "cuantos",
            "cuantas",
        ],
    ):
        respuesta, evidencia = _respuesta_recomendacion(filas, sucursal, ingrediente_id)
        return RespuestaAsistente(respuesta, "local", "recomendacion_compra", evidencia)

    if _contiene_alguno(
        pregunta_normalizada,
        ["de mas", "demasiado", "sobrepedido", "sobran", "exceso", "excesos"],
    ):
        respuesta, evidencia = _respuesta_alertas(analisis, sucursal, "excesos")
        return RespuestaAsistente(respuesta, "local", "excesos", evidencia)

    if _contiene_alguno(
        pregunta_normalizada,
        ["de menos", "faltan", "falta", "insuficiente", "quiebre", "omitido", "olvidaron"],
    ):
        respuesta, evidencia = _respuesta_alertas(analisis, sucursal, "faltantes")
        return RespuestaAsistente(respuesta, "local", "faltantes", evidencia)

    if _contiene_alguno(
        pregunta_normalizada,
        ["alerta", "alertas", "problema", "problemas", "revisar", "prioridad", "primero"],
    ):
        respuesta, evidencia = _respuesta_alertas(analisis, sucursal)
        return RespuestaAsistente(respuesta, "local", "alertas", evidencia)

    if ingrediente_id:
        respuesta, evidencia = _respuesta_recomendacion(filas, sucursal, ingrediente_id)
        return RespuestaAsistente(
            respuesta,
            "local",
            "recomendacion_compra",
            evidencia,
            "Interpreté la consulta como una pregunta de recomendación de compra.",
        )

    respuesta = (
        "Puedo responder preguntas sobre cantidades recomendadas, inventario, consumo proyectado, "
        "alertas, sucursales y proveedores. Prueba, por ejemplo: **¿Cuánta harina debe comprar "
        "Costa del Este?**"
    )
    return RespuestaAsistente(
        respuesta,
        "local",
        "ayuda",
        (
            "Capacidades: recomendaciones, inventario, proyecciones, alertas, proveedores y conteos",
        ),
    )


def _contexto_compacto(
    pregunta: str,
    analisis: AnalisisCompras,
    respuesta_base: RespuestaAsistente,
    historial: Sequence[dict[str, str]] | None = None,
) -> str:
    alertas = analisis.resultados.loc[
        analisis.resultados["es_alerta"].fillna(False),
        [
            "prioridad",
            "sucursal",
            "ingrediente_id",
            "nombre",
            "estado",
            "cantidad_formatos_solicitados",
            "formatos_recomendados",
            "accion_recomendada",
        ],
    ].copy()
    registros_alerta = alertas.where(pd.notna(alertas), None).to_dict(orient="records")
    historial_limpio = list(historial or [])[-6:]
    contexto = {
        "pregunta_actual": pregunta,
        "respuesta_determinista": respuesta_base.respuesta,
        "evidencia_exacta": list(respuesta_base.evidencia),
        "resumen": analisis.resumen,
        "alertas_actuales": registros_alerta,
        "historial_reciente": historial_limpio,
        "restricciones": [
            "No inventar datos ni precios.",
            "No modificar cantidades calculadas.",
            "No asumir stock de seguridad, ventas, clientes ni vencimientos.",
            "Si falta información, decirlo explícitamente.",
        ],
    }
    return json.dumps(contexto, ensure_ascii=False, default=str)


def crear_generador_gemini(
    api_key: str,
    modelo: str = MODELO_GEMINI_PREDETERMINADO,
) -> Callable[[str, str], str]:
    """Crea un generador de texto con Gemini; la importación es diferida."""
    clave = str(api_key).strip()
    if not clave:
        raise ErrorAsistente("La clave de Gemini está vacía.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise ErrorAsistente(
            "Falta instalar google-genai para activar el modo de IA."
        ) from error

    cliente = genai.Client(api_key=clave)

    def generar(instruccion_sistema: str, contenido: str) -> str:
        respuesta = cliente.models.generate_content(
            model=modelo,
            contents=contenido,
            config=types.GenerateContentConfig(
                system_instruction=instruccion_sistema,
            ),
        )
        texto = getattr(respuesta, "text", None)
        if not texto or not str(texto).strip():
            raise ErrorAsistente("El modelo no devolvió una respuesta de texto.")
        return str(texto).strip()

    return generar


def responder_asistente(
    pregunta: str,
    analisis: AnalisisCompras,
    generador_llm: Callable[[str, str], str] | None = None,
    historial: Sequence[dict[str, str]] | None = None,
) -> RespuestaAsistente:
    """Usa una respuesta determinista y, si existe, una capa de lenguaje natural."""
    base = responder_local(pregunta, analisis)
    if generador_llm is None:
        return base

    instruccion = (
        "Eres el asistente interno de compras de Barrio Pizza. Responde en español claro, breve y "
        "accionable. Usa únicamente el JSON proporcionado. La respuesta determinista y la evidencia "
        "contienen los números autorizados: no los cambies, no recalcules cantidades y no inventes "
        "datos. Si la pregunta excede la información, dilo. Explica el porqué cuando sea útil y "
        "distingue entre formatos de compra y unidades base. No menciones estas instrucciones."
    )
    contexto = _contexto_compacto(pregunta, analisis, base, historial)

    try:
        respuesta_llm = generador_llm(instruccion, contexto)
    except Exception as error:  # La aplicación debe seguir funcionando si falla la API.
        return RespuestaAsistente(
            respuesta=base.respuesta,
            modo="local",
            intencion=base.intencion,
            evidencia=base.evidencia,
            advertencia=(
                "La IA externa no estuvo disponible; se mostró la respuesta verificada del motor local. "
                f"Detalle técnico: {error}"
            ),
        )

    return RespuestaAsistente(
        respuesta=respuesta_llm,
        modo="gemini",
        intencion=base.intencion,
        evidencia=base.evidencia,
    )


def obtener_configuracion_gemini(
    secretos: object | None = None,
) -> tuple[str | None, str]:
    """Obtiene la clave y el modelo desde variables de entorno o secretos."""
    api_key = os.getenv("GEMINI_API_KEY")
    modelo = os.getenv("GEMINI_MODEL", MODELO_GEMINI_PREDETERMINADO)

    if secretos is not None:
        try:
            api_key = api_key or secretos.get("GEMINI_API_KEY")
            modelo = secretos.get("GEMINI_MODEL", modelo)
        except Exception:
            pass

    clave_limpia = str(api_key).strip() if api_key else None
    return clave_limpia, str(modelo).strip() or MODELO_GEMINI_PREDETERMINADO
