from __future__ import annotations

from src.aprobaciones import (
    DECISION_CATALOGO,
    aplicar_recomendaciones_alta_confianza,
    construir_casos_aprobacion,
    construir_contexto_aprobacion,
    registrar_decision,
)
from src.asistente import responder_asistente, responder_local
from src.carga_datos import cargar_datos
from src.dashboard import construir_analisis


def _analisis_real():
    return construir_analisis(cargar_datos())


def _contexto_aprobacion(completo: bool = False):
    analisis = _analisis_real()
    casos = construir_casos_aprobacion(analisis.resultados)
    decisiones = {}
    if completo:
        decisiones = aplicar_recomendaciones_alta_confianza(casos)
        desconocido = casos.loc[casos["estado"] == "NO_EVALUABLE"].iloc[0]
        decisiones[str(desconocido["caso_id"])] = registrar_decision(
            desconocido,
            DECISION_CATALOGO,
            motivo_codigo="CORRECCION_CATALOGO",
        )
    return construir_contexto_aprobacion(casos, decisiones)


def test_recomienda_harina_para_costa_del_este() -> None:
    respuesta = responder_local(
        "¿Cuánta harina debe comprar Costa del Este?",
        _analisis_real(),
    )

    assert respuesta.intencion == "recomendacion_compra"
    assert "13 sacos" in respuesta.respuesta
    assert "325 kg" in respuesta.respuesta
    assert "orden actual tiene 6" in respuesta.respuesta


def test_responde_prioridades_con_las_seis_alertas() -> None:
    respuesta = responder_local("¿Qué debo revisar primero?", _analisis_real())

    assert respuesta.intencion == "alertas"
    assert "Alertas detectadas (6)" in respuesta.respuesta
    assert "Mozzarella" in respuesta.respuesta
    assert "Harina 00" in respuesta.respuesta


def test_responde_conteo_de_alertas() -> None:
    respuesta = responder_local("¿Cuántas alertas hay?", _analisis_real())

    assert respuesta.intencion == "conteo_alertas"
    assert "6 alertas" in respuesta.respuesta
    assert "2 críticas" in respuesta.respuesta


def test_responde_proveedor_de_mozzarella() -> None:
    respuesta = responder_local("¿Quién provee la mozzarella?", _analisis_real())

    assert respuesta.intencion == "proveedor_ingrediente"
    assert "Distrib. Bella Italia" in respuesta.respuesta
    assert "Caja 10 kg" in respuesta.respuesta


def test_responde_inventario_de_albahaca() -> None:
    respuesta = responder_local(
        "¿Cuánto inventario de albahaca hay en Vía Argentina?",
        _analisis_real(),
    )

    assert respuesta.intencion == "inventario"
    assert "1 kg" in respuesta.respuesta


def test_capa_llm_recibe_contexto_y_conserva_modo() -> None:
    capturado: dict[str, str] = {}

    def generador(instruccion: str, contenido: str) -> str:
        capturado["instruccion"] = instruccion
        capturado["contenido"] = contenido
        return "Costa del Este debe comprar 13 sacos de harina."

    respuesta = responder_asistente(
        "¿Cuánta harina debe comprar Costa del Este?",
        _analisis_real(),
        generador_llm=generador,
    )

    assert respuesta.modo == "gemini"
    assert "13 sacos" in respuesta.respuesta
    assert "respuesta_determinista" in capturado["contenido"]
    assert "no inventes" in capturado["instruccion"].lower()


def test_falla_del_llm_activa_respuesta_local() -> None:
    def generador(_: str, __: str) -> str:
        raise RuntimeError("servicio no disponible")

    respuesta = responder_asistente(
        "¿Cuántas alertas hay?",
        _analisis_real(),
        generador_llm=generador,
    )

    assert respuesta.modo == "local"
    assert "6 alertas" in respuesta.respuesta
    assert respuesta.advertencia is not None


def test_pregunta_fuera_de_alcance_explica_capacidades() -> None:
    respuesta = responder_local("Buenos días", _analisis_real())

    assert respuesta.intencion == "ayuda"
    assert "cantidades recomendadas" in respuesta.respuesta


def test_motor_local_responde_recomendacion_en_ingles() -> None:
    respuesta = responder_local(
        "How much flour should Costa del Este buy?",
        _analisis_real(),
        idioma="en",
    )

    assert respuesta.intencion == "recomendacion_compra"
    assert "13 sacks" in respuesta.respuesta
    assert "325 kg" in respuesta.respuesta
    assert "current order has 6" in respuesta.respuesta


def test_capa_llm_recibe_instruccion_en_ingles() -> None:
    capturado: dict[str, str] = {}

    def generador(instruccion: str, contenido: str) -> str:
        capturado["instruccion"] = instruccion
        capturado["contenido"] = contenido
        return "There are 6 alerts to review."

    respuesta = responder_asistente(
        "How many alerts are there?",
        _analisis_real(),
        generador_llm=generador,
        idioma="en",
    )

    assert respuesta.modo == "gemini"
    assert "Answer in clear" in capturado["instruccion"]
    assert "6 alerts" in capturado["contenido"]


def test_respuesta_visible_usa_pina_con_enie_sin_cambiar_id() -> None:
    analisis = _analisis_real()
    respuesta = responder_local(
        "¿Cuánta piña debe comprar Costa del Este?",
        analisis,
    )

    assert respuesta.intencion == "recomendacion_compra"
    assert "Piña" in respuesta.respuesta
    assert "pina" in analisis.resultados["ingrediente_id"].tolist()


def test_barrio_ai_conoce_el_progreso_y_estado_de_aprobacion() -> None:
    pendiente = responder_local(
        "¿Cuántas decisiones faltan?",
        _analisis_real(),
        contexto_operativo=_contexto_aprobacion(),
    )
    lista = responder_local(
        "¿La orden está lista para aprobar?",
        _analisis_real(),
        contexto_operativo=_contexto_aprobacion(completo=True),
    )

    assert pendiente.intencion == "progreso_aprobacion"
    assert "6 pendientes" in pendiente.respuesta
    assert lista.intencion == "estado_aprobacion"
    assert "revisión está completa" in lista.respuesta


def test_contexto_operativo_llega_a_la_capa_llm() -> None:
    capturado: dict[str, str] = {}

    def generador(instruccion: str, contenido: str) -> str:
        capturado["instruccion"] = instruccion
        capturado["contenido"] = contenido
        return "Quedan 6 decisiones."

    respuesta = responder_asistente(
        "¿Cuántas decisiones faltan?",
        _analisis_real(),
        generador_llm=generador,
        contexto_operativo=_contexto_aprobacion(),
    )

    assert respuesta.modo == "gemini"
    assert "aprobacion_y_operacion" in capturado["contenido"]
    assert '"pendientes": 6' in capturado["contenido"]
    assert "no autoapruebes" in capturado["instruccion"].lower()


def test_fallo_externo_conserva_respuesta_local_de_aprobacion() -> None:
    def generador(_: str, __: str) -> str:
        raise RuntimeError("sin servicio")

    respuesta = responder_asistente(
        "¿Cuántas decisiones faltan?",
        _analisis_real(),
        generador_llm=generador,
        contexto_operativo=_contexto_aprobacion(),
    )

    assert respuesta.modo == "local"
    assert "6 pendientes" in respuesta.respuesta


def test_barrio_ai_conoce_escenario_y_reparacion_activos() -> None:
    contexto = _contexto_aprobacion()
    contexto["escenario_activo"] = {
        "configurado": True,
        "variacion_pct": 10,
        "sucursal": "TODAS",
        "ingrediente_id": "TODOS",
        "alertas_base": 6,
        "alertas_escenario": 50,
        "riesgos_quiebre_escenario": 47,
        "cambios_formatos": [],
    }
    contexto["reparacion_archivo"] = {
        "filas_validas": 88,
        "combinaciones_agregadas_con_cero": 1,
        "filas_separadas_para_revision": 1,
    }

    escenario = responder_local(
        "¿Qué cambia con el escenario?",
        _analisis_real(),
        contexto_operativo=contexto,
    )
    reparador = responder_local(
        "¿Qué hizo el reparador?",
        _analisis_real(),
        contexto_operativo=contexto,
    )

    assert escenario.intencion == "escenario_activo"
    assert "6 a 50" in escenario.respuesta
    assert "47 riesgos" in escenario.respuesta
    assert reparador.intencion == "estado_reparador"
    assert "88 filas válidas" in reparador.respuesta
