from __future__ import annotations

from src.asistente import responder_asistente, responder_local
from src.carga_datos import cargar_datos
from src.dashboard import construir_analisis


def _analisis_real():
    return construir_analisis(cargar_datos())


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
