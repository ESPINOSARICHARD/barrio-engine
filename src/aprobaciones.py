from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from src.alertas import agregar_mensajes_alerta
from src.calculos import evaluar_ordenes_compra, resumir_evaluacion
from src.presentacion import aplicar_nombres_visibles, nombre_ingrediente_visible


CONFIANZA_ALTA = "ALTA"
CONFIANZA_MEDIA = "MEDIA"
CONFIANZA_REVISION = "REVISION_OBLIGATORIA"

DECISION_APLICAR = "APLICAR_RECOMENDACION"
DECISION_MANTENER = "MANTENER_ORIGINAL"
DECISION_DEVOLVER = "DEVOLVER_SUCURSAL"
DECISION_CATALOGO = "SEPARAR_CATALOGO"

DECISIONES_EVALUABLES = {
    DECISION_APLICAR,
    DECISION_MANTENER,
    DECISION_DEVOLVER,
}
DECISIONES_NO_EVALUABLES = {
    DECISION_CATALOGO,
    DECISION_DEVOLVER,
}

DECISION_ETIQUETAS_ES = {
    DECISION_APLICAR: "Aplicar recomendación",
    DECISION_MANTENER: "Mantener pedido original",
    DECISION_DEVOLVER: "Devolver a la sucursal",
    DECISION_CATALOGO: "Separar y corregir catálogo",
}

DECISION_ETIQUETAS_EN = {
    DECISION_APLICAR: "Apply recommendation",
    DECISION_MANTENER: "Keep original order",
    DECISION_DEVOLVER: "Return to location",
    DECISION_CATALOGO: "Separate and correct catalog",
}


class ErrorAprobacion(Exception):
    """Error controlado de la capa de revisión humana."""


@dataclass(frozen=True)
class ClasificacionConfianza:
    nivel: str
    motivo: str
    requiere_revision_humana: bool


@dataclass(frozen=True)
class ResultadoEscenario:
    resultados: pd.DataFrame
    resumen: dict[str, int]


def _numero_finito(valor: object) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


def _entero_no_negativo(valor: object, campo: str) -> int:
    numero = _numero_finito(valor)
    if numero is None or numero < 0 or abs(numero - round(numero)) > 1e-9:
        raise ErrorAprobacion(f"{campo} debe ser un entero no negativo.")
    return int(round(numero))


def clave_caso(sucursal: object, ingrediente_id: object) -> str:
    """Crea una clave de sesión estable sin utilizar nombres visibles."""
    contenido = f"{str(sucursal).strip()}\x1f{str(ingrediente_id).strip()}"
    return sha256(contenido.encode("utf-8")).hexdigest()[:16]


def clasificar_confianza_operativa(
    fila: Mapping[str, object] | pd.Series,
) -> ClasificacionConfianza:
    """Clasifica evidencia histórica; no representa probabilidad de acierto."""
    estado = str(fila.get("estado", ""))
    semanas = _numero_finito(fila.get("semanas_usadas"))
    wape = _numero_finito(fila.get("wape_backtest_pct"))
    atipicos = _numero_finito(fila.get("cantidad_atipicos"))

    if estado == "NO_EVALUABLE" or semanas is None or wape is None or atipicos is None:
        return ClasificacionConfianza(
            CONFIANZA_REVISION,
            "Faltan datos de catálogo o evidencia retrospectiva para respaldar la recomendación.",
            True,
        )

    if semanas >= 6 and wape <= 5 and atipicos == 0:
        return ClasificacionConfianza(
            CONFIANZA_ALTA,
            f"Se usaron {int(semanas)} semanas, sin atípicos, con WAPE retrospectivo de {wape:.1f}%.",
            False,
        )

    if semanas >= 6 and wape <= 10:
        detalle_atipicos = (
            "sin semanas atípicas"
            if atipicos == 0
            else f"con {int(atipicos)} semana(s) atípica(s)"
        )
        return ClasificacionConfianza(
            CONFIANZA_MEDIA,
            f"Se usaron {int(semanas)} semanas, {detalle_atipicos}, con WAPE retrospectivo de {wape:.1f}%.",
            True,
        )

    return ClasificacionConfianza(
        CONFIANZA_REVISION,
        "La serie tiene menos de seis semanas o un WAPE retrospectivo superior a 10%.",
        True,
    )


def construir_casos_aprobacion(
    resultados: pd.DataFrame,
) -> pd.DataFrame:
    """Prepara únicamente las alertas que requieren una decisión humana."""
    if "es_alerta" not in resultados.columns:
        raise ErrorAprobacion("Los resultados no incluyen el indicador de alerta.")

    casos = resultados.loc[resultados["es_alerta"].fillna(False)].copy()
    clasificaciones = [
        clasificar_confianza_operativa(fila)
        for _, fila in casos.iterrows()
    ]
    casos["caso_id"] = [
        clave_caso(fila["sucursal"], fila["ingrediente_id"])
        for _, fila in casos.iterrows()
    ]
    casos["confianza_operativa"] = [item.nivel for item in clasificaciones]
    casos["confianza_motivo"] = [item.motivo for item in clasificaciones]
    casos["requiere_revision_humana"] = [
        item.requiere_revision_humana for item in clasificaciones
    ]
    orden_prioridad = casos["prioridad"].map(
        {"CRITICA": 0, "ALTA": 1, "MEDIA": 2}
    ).fillna(99)
    return (
        casos.assign(_orden_prioridad=orden_prioridad)
        .sort_values(["_orden_prioridad", "sucursal", "nombre"], kind="stable")
        .drop(columns="_orden_prioridad")
        .reset_index(drop=True)
    )


def crear_huella_revision(resultados: pd.DataFrame) -> str:
    """Versiona el análisis para invalidar decisiones cuando cambia la orden."""
    columnas_preferidas = [
        "sucursal",
        "ingrediente_id",
        "cantidad_formatos_solicitados",
        "formatos_recomendados",
        "estado",
        "prioridad",
        "stock_actual_unidad_base",
        "consumo_proyectado_unidad_base",
        "metodo_proyeccion",
        "wape_backtest_pct",
        "cantidad_atipicos",
    ]
    columnas = [columna for columna in columnas_preferidas if columna in resultados.columns]
    canonico = resultados[columnas].copy().sort_values(
        [columna for columna in ["sucursal", "ingrediente_id"] if columna in columnas],
        kind="stable",
    )
    registros = canonico.where(pd.notna(canonico), None).to_dict(orient="records")
    contenido = json.dumps(
        registros,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(contenido.encode("utf-8")).hexdigest()


def opciones_decision(caso: Mapping[str, object] | pd.Series) -> tuple[str, ...]:
    if str(caso.get("estado")) == "NO_EVALUABLE":
        return DECISION_CATALOGO, DECISION_DEVOLVER
    return DECISION_APLICAR, DECISION_MANTENER, DECISION_DEVOLVER


def registrar_decision(
    caso: Mapping[str, object] | pd.Series,
    decision: str,
    *,
    motivo_codigo: str = "",
    motivo_detalle: str = "",
    responsable: str = "",
    fecha_hora: str | None = None,
) -> dict[str, object]:
    """Valida y registra una decisión sin modificar el análisis original."""
    permitidas = set(opciones_decision(caso))
    if decision not in permitidas:
        raise ErrorAprobacion("La decisión no es válida para este caso.")

    if decision in {DECISION_MANTENER, DECISION_DEVOLVER, DECISION_CATALOGO}:
        if not str(motivo_codigo).strip() and not str(motivo_detalle).strip():
            raise ErrorAprobacion("Registra el motivo de esta decisión.")

    cantidad_aprobada: int | None
    if decision == DECISION_APLICAR:
        cantidad_aprobada = _entero_no_negativo(
            caso.get("formatos_recomendados"),
            "La cantidad recomendada",
        )
    elif decision == DECISION_MANTENER:
        cantidad_aprobada = _entero_no_negativo(
            caso.get("cantidad_formatos_solicitados"),
            "La cantidad original",
        )
    else:
        cantidad_aprobada = None

    marca_tiempo = fecha_hora or datetime.now(
        ZoneInfo("America/Panama")
    ).isoformat(timespec="seconds")
    return {
        "caso_id": str(caso["caso_id"]),
        "sucursal": str(caso["sucursal"]),
        "ingrediente_id": str(caso["ingrediente_id"]),
        "decision": decision,
        "cantidad_aprobada": cantidad_aprobada,
        "motivo_codigo": str(motivo_codigo).strip(),
        "motivo_detalle": str(motivo_detalle).strip(),
        "responsable": str(responsable).strip(),
        "fecha_hora": marca_tiempo,
    }


def aplicar_recomendaciones_alta_confianza(
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]] | None = None,
    *,
    responsable: str = "",
) -> dict[str, dict[str, object]]:
    """Aplica solo casos verificables y no sobrescribe decisiones humanas."""
    resultado = {
        str(clave): dict(valor)
        for clave, valor in (decisiones or {}).items()
    }
    for _, caso in casos.iterrows():
        caso_id = str(caso["caso_id"])
        if caso_id in resultado:
            continue
        if (
            caso["confianza_operativa"] == CONFIANZA_ALTA
            and caso["estado"] != "NO_EVALUABLE"
        ):
            resultado[caso_id] = registrar_decision(
                caso,
                DECISION_APLICAR,
                motivo_codigo="RECOMENDACION_ALTA_CONFIANZA",
                responsable=responsable,
            )
    return resultado


def resumir_aprobacion(
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]] | None,
) -> dict[str, object]:
    registros = decisiones or {}
    ids = set(casos.get("caso_id", pd.Series(dtype=str)).astype(str))
    decisiones_validas = {
        clave: valor for clave, valor in registros.items() if clave in ids
    }
    total = len(casos)
    revisadas = len(decisiones_validas)
    devueltas = sum(
        registro.get("decision") == DECISION_DEVOLVER
        for registro in decisiones_validas.values()
    )
    excepciones = sum(
        registro.get("decision") == DECISION_CATALOGO
        for registro in decisiones_validas.values()
    )
    aplicadas = sum(
        registro.get("decision") == DECISION_APLICAR
        for registro in decisiones_validas.values()
    )
    mantenidas = sum(
        registro.get("decision") == DECISION_MANTENER
        for registro in decisiones_validas.values()
    )
    pendientes = max(total - revisadas, 0)
    lista = pendientes == 0 and devueltas == 0
    return {
        "total": total,
        "revisadas": revisadas,
        "pendientes": pendientes,
        "aplicadas": aplicadas,
        "mantenidas": mantenidas,
        "devueltas": devueltas,
        "excepciones_catalogo": excepciones,
        "lista_para_aprobar": lista,
        "lista_con_excepciones": lista and excepciones > 0,
        "progreso": 1.0 if total == 0 else revisadas / total,
    }


def generar_bitacora_decisiones(
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]] | None,
    *,
    huella_revision: str,
    fuente: str = "",
    idioma: str = "es",
) -> pd.DataFrame:
    """Genera evidencia descargable de todas las decisiones y pendientes."""
    registros = decisiones or {}
    filas: list[dict[str, object]] = []
    etiquetas = DECISION_ETIQUETAS_EN if idioma.startswith("en") else DECISION_ETIQUETAS_ES
    for _, caso in casos.iterrows():
        decision = dict(registros.get(str(caso["caso_id"]), {}))
        codigo = str(decision.get("decision", "PENDIENTE"))
        filas.append(
            {
                "revision_id": huella_revision[:12],
                "fuente": fuente,
                "sucursal": caso["sucursal"],
                "ingrediente_id": caso["ingrediente_id"],
                "nombre": nombre_ingrediente_visible(
                    caso["ingrediente_id"], caso["nombre"], idioma
                ),
                "prioridad": caso["prioridad"],
                "estado": caso["estado"],
                "cantidad_original": caso["cantidad_formatos_solicitados"],
                "cantidad_recomendada": caso["formatos_recomendados"],
                "cantidad_aprobada": decision.get("cantidad_aprobada"),
                "decision": etiquetas.get(codigo, "Pending" if idioma.startswith("en") else "Pendiente"),
                "motivo": decision.get("motivo_codigo", ""),
                "detalle_motivo": decision.get("motivo_detalle", ""),
                "responsable_declarado": decision.get("responsable", ""),
                "fecha_hora_panama": decision.get("fecha_hora", ""),
                "confianza_operativa": caso["confianza_operativa"],
                "confianza_motivo": caso["confianza_motivo"],
                "metodo_proyeccion": caso.get("metodo_proyeccion"),
                "wape_backtest_pct": caso.get("wape_backtest_pct"),
                "semanas_atipicas": caso.get("semanas_atipicas"),
            }
        )
    return pd.DataFrame(filas)


def generar_orden_aprobada(
    evaluacion: pd.DataFrame,
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]] | None,
) -> pd.DataFrame:
    """Materializa la decisión humana sin modificar la orden recomendada."""
    estado = resumir_aprobacion(casos, decisiones)
    if not estado["lista_para_aprobar"]:
        raise ErrorAprobacion(
            "La orden todavía tiene decisiones pendientes o casos devueltos."
        )

    registros = decisiones or {}
    trabajo = evaluacion.loc[evaluacion["estado"] != "NO_EVALUABLE"].copy()
    trabajo["caso_id"] = [
        clave_caso(sucursal, ingrediente_id)
        for sucursal, ingrediente_id in zip(
            trabajo["sucursal"], trabajo["ingrediente_id"], strict=True
        )
    ]
    cantidades: list[int] = []
    decisiones_fila: list[str] = []
    for _, fila in trabajo.iterrows():
        registro = registros.get(str(fila["caso_id"]))
        if registro:
            codigo = str(registro.get("decision"))
            if codigo not in {DECISION_APLICAR, DECISION_MANTENER}:
                raise ErrorAprobacion(
                    "Una decisión sin cantidad no puede entrar en la orden aprobada."
                )
            cantidad = _entero_no_negativo(
                registro.get("cantidad_aprobada"), "La cantidad aprobada"
            )
            decisiones_fila.append(codigo)
        else:
            cantidad = _entero_no_negativo(
                fila["formatos_recomendados"], "La cantidad recomendada"
            )
            decisiones_fila.append("SIN_ALERTA")
        cantidades.append(cantidad)

    trabajo["cantidad_formatos_aprobada"] = cantidades
    trabajo["decision_aprobacion"] = decisiones_fila
    trabajo["cantidad_unidad_base_aprobada"] = (
        trabajo["cantidad_formatos_aprobada"]
        * trabajo["unidad_base_por_formato"].astype(float)
    )
    trabajo["ajuste_formatos_aprobado"] = (
        trabajo["cantidad_formatos_aprobada"]
        - trabajo["cantidad_formatos_solicitados"].astype(int)
    )
    trabajo = trabajo.loc[trabajo["cantidad_formatos_aprobada"] > 0].copy()
    columnas = [
        "proveedor",
        "sucursal",
        "ingrediente_id",
        "nombre",
        "formato_compra",
        "unidad_base",
        "cantidad_formatos_solicitados",
        "formatos_recomendados",
        "cantidad_formatos_aprobada",
        "cantidad_unidad_base_aprobada",
        "ajuste_formatos_aprobado",
        "decision_aprobacion",
    ]
    return trabajo[columnas].sort_values(
        ["proveedor", "sucursal", "nombre"], kind="stable"
    ).reset_index(drop=True)


def _nombre_formato(formato: object, cantidad: int, idioma: str) -> str:
    singular_es = str(formato or "formato").strip().split()[0].lower()
    if idioma.startswith("en"):
        nombres = {
            "saco": ("sack", "sacks"),
            "bolsa": ("bag", "bags"),
            "caja": ("box", "boxes"),
            "lata": ("can", "cans"),
            "balde": ("bucket", "buckets"),
            "paquete": ("pack", "packs"),
            "kilo": ("kilogram", "kilograms"),
            "unidad": ("unit", "units"),
            "pieza": ("piece", "pieces"),
        }
        singular, plural = nombres.get(singular_es, ("format", "formats"))
    else:
        nombres = {
            "saco": ("saco", "sacos"),
            "bolsa": ("bolsa", "bolsas"),
            "caja": ("caja", "cajas"),
            "lata": ("lata", "latas"),
            "balde": ("balde", "baldes"),
            "paquete": ("paquete", "paquetes"),
            "kilo": ("kilo", "kilos"),
            "unidad": ("unidad", "unidades"),
            "pieza": ("pieza", "piezas"),
        }
        singular, plural = nombres.get(singular_es, ("formato", "formatos"))
    return singular if cantidad == 1 else plural


def _formatear_cantidad(valor: object) -> str:
    numero = float(valor)
    if abs(numero - round(numero)) < 1e-9:
        return str(int(round(numero)))
    return f"{numero:.2f}".rstrip("0").rstrip(".")


def generar_mensaje_proveedor(
    orden: pd.DataFrame,
    proveedor: str,
    *,
    semana: str,
    idioma: str = "es",
    aprobado: bool = False,
) -> str:
    """Prepara texto determinista; no afirma que el mensaje fue enviado."""
    grupo = orden.loc[orden["proveedor"] == proveedor].copy()
    if grupo.empty:
        raise ErrorAprobacion("No hay líneas para el proveedor seleccionado.")

    aprobada = "cantidad_formatos_aprobada" in grupo.columns
    columna_formatos = (
        "cantidad_formatos_aprobada"
        if aprobada
        else "cantidad_formatos_recomendada"
    )
    columna_base = (
        "cantidad_unidad_base_aprobada"
        if aprobada
        else "cantidad_unidad_base_recomendada"
    )
    grupo = aplicar_nombres_visibles(grupo, idioma=idioma)
    titulo_estado = (
        "APPROVED ORDER" if aprobado else "ORDER DRAFT"
    ) if idioma.startswith("en") else (
        "ORDEN APROBADA" if aprobado else "BORRADOR DE ORDEN"
    )
    lineas = [
        f"BARRIO PIZZA · {titulo_estado} · {semana}",
        (f"Supplier: {proveedor}" if idioma.startswith("en") else f"Proveedor: {proveedor}"),
        "",
    ]
    for _, fila in grupo.sort_values(["sucursal", "nombre"], kind="stable").iterrows():
        cantidad = int(fila[columna_formatos])
        formato = _nombre_formato(fila["formato_compra"], cantidad, idioma)
        total = _formatear_cantidad(fila[columna_base])
        lineas.append(
            f"• {fila['sucursal']} · {fila['nombre']}: "
            f"{cantidad} {formato} ({total} {fila['unidad_base']})"
        )
    lineas.extend(
        [
            "",
            (
                "Prepared from the weekly purchasing review. Confirm delivery details through the usual channel."
                if idioma.startswith("en")
                else "Preparada desde la revisión semanal de compras. Confirmar detalles de entrega por el canal habitual."
            ),
        ]
    )
    return "\n".join(lineas)


def generar_mensaje_sucursal(
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]],
    sucursal: str,
    *,
    semana: str,
    idioma: str = "es",
) -> str:
    grupo = casos.loc[casos["sucursal"] == sucursal].copy()
    grupo = aplicar_nombres_visibles(grupo, idioma=idioma)
    lineas = [
        (
            f"BARRIO PIZZA · PURCHASE ADJUSTMENTS · {semana}\nLocation: {sucursal}\n"
            if idioma.startswith("en")
            else f"BARRIO PIZZA · AJUSTES DE COMPRA · {semana}\nSucursal: {sucursal}\n"
        )
    ]
    for _, caso in grupo.iterrows():
        registro = decisiones.get(str(caso["caso_id"]))
        if not registro:
            continue
        codigo = str(registro["decision"])
        if codigo == DECISION_APLICAR:
            cantidad = int(registro["cantidad_aprobada"])
            texto = (
                f"Apply {cantidad} format(s) for {caso['nombre']}."
                if idioma.startswith("en")
                else f"Aplicar {cantidad} formato(s) para {caso['nombre']}."
            )
        elif codigo == DECISION_MANTENER:
            cantidad = int(registro["cantidad_aprobada"])
            texto = (
                f"Keep the original {cantidad} format(s) for {caso['nombre']}."
                if idioma.startswith("en")
                else f"Mantener los {cantidad} formato(s) originales de {caso['nombre']}."
            )
        elif codigo == DECISION_CATALOGO:
            texto = (
                f"Correct the catalog identifier {caso['ingrediente_id']} before including it in a supplier order."
                if idioma.startswith("en")
                else f"Corregir el identificador {caso['ingrediente_id']} en el catálogo antes de incluirlo en una orden a proveedor."
            )
        else:
            texto = (
                f"Return {caso['nombre']} for location review."
                if idioma.startswith("en")
                else f"Devolver {caso['nombre']} para revisión de la sucursal."
            )
        lineas.append(f"• {texto}")
    lineas.extend(
        [
            "",
            (
                "Prepared for coordination; it has not been sent automatically."
                if idioma.startswith("en")
                else "Resumen preparado para coordinación; no fue enviado automáticamente."
            ),
        ]
    )
    return "\n".join(lineas)


def construir_contexto_aprobacion(
    casos: pd.DataFrame,
    decisiones: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Crea un contexto compacto y verificable para BARRIO AI."""
    resumen = resumir_aprobacion(casos, decisiones)
    registros: list[dict[str, object]] = []
    for _, caso in casos.iterrows():
        decision = decisiones.get(str(caso["caso_id"]), {})
        registros.append(
            {
                "sucursal": caso["sucursal"],
                "ingrediente_id": caso["ingrediente_id"],
                "nombre": nombre_ingrediente_visible(
                    caso["ingrediente_id"], caso["nombre"], "es"
                ),
                "prioridad": caso["prioridad"],
                "confianza": caso["confianza_operativa"],
                "confianza_motivo": caso["confianza_motivo"],
                "decision": decision.get("decision", "PENDIENTE"),
                "cantidad_original": caso["cantidad_formatos_solicitados"],
                "cantidad_recomendada": caso["formatos_recomendados"],
                "cantidad_aprobada": decision.get("cantidad_aprobada"),
                "motivo": decision.get("motivo_codigo", ""),
            }
        )
    return {"revision": resumen, "casos": registros}


def simular_escenario_demanda(
    *,
    ingredientes: pd.DataFrame,
    inventario_actual: pd.DataFrame,
    orden_compra_semana: pd.DataFrame,
    proyecciones: pd.DataFrame,
    variacion_pct: float,
    sucursales: Sequence[str] | None = None,
    ingrediente_ids: Sequence[str] | None = None,
) -> ResultadoEscenario:
    """Reutiliza las reglas probadas sobre una copia de las proyecciones."""
    variacion = float(variacion_pct)
    if variacion < -100 or variacion > 200:
        raise ErrorAprobacion("La variación debe estar entre -100% y 200%.")

    escenario = proyecciones.copy()
    mascara = pd.Series(True, index=escenario.index)
    if sucursales:
        mascara &= escenario["sucursal"].isin(sucursales)
    if ingrediente_ids:
        mascara &= escenario["ingrediente_id"].isin(ingrediente_ids)
    escenario.loc[mascara, "consumo_proyectado_unidad_base"] *= 1 + variacion / 100

    evaluacion = evaluar_ordenes_compra(
        ingredientes=ingredientes,
        inventario_actual=inventario_actual,
        orden_compra_semana=orden_compra_semana,
        proyecciones=escenario,
    )
    return ResultadoEscenario(
        resultados=agregar_mensajes_alerta(evaluacion),
        resumen=resumir_evaluacion(evaluacion),
    )
