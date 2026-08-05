from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.alertas import ErrorAlertas
from src.asistente import (
    ErrorAsistente,
    crear_generador_gemini,
    obtener_configuracion_gemini,
    responder_asistente,
)
from src.calculos import ErrorCalculoCompras
from src.carga_datos import ErrorCargaDatos, cargar_datos
from src.dashboard import (
    ESTADO_ETIQUETAS,
    METODO_ETIQUETAS,
    PRIORIDAD_ETIQUETAS,
    ErrorDashboard,
    completar_orden_para_editor,
    construir_analisis,
    dataframe_a_csv_bytes,
    filtrar_resultados,
    limpiar_infinito,
    leer_orden_csv,
    obtener_caso,
    porcentaje_orden_correcta,
    preparar_orden_por_proveedor,
    preparar_serie_detalle,
    preparar_tabla_alertas,
    proyeccion_del_caso,
    resumen_por_estado,
    resumen_por_sucursal,
)
from src.proyecciones import ErrorProyeccion


RAIZ = Path(__file__).resolve().parent
COLORES_PRIORIDAD = {
    "CRITICA": "#B42318",
    "ALTA": "#E77728",
    "MEDIA": "#E0A82E",
    "SIN_ALERTA": "#667085",
}
COLORES_ESTADO = {
    "Pedido correcto": "#2E7D5B",
    "Sin compra necesaria": "#7A8B5A",
    "Pedido insuficiente": "#C84031",
    "Sobrepedido": "#E77728",
    "Ingrediente omitido": "#8F2D22",
    "Compra innecesaria": "#B86B24",
    "No evaluable": "#4B5563",
}


st.set_page_config(
    page_title="Centro Inteligente de Compras",
    page_icon="🍕",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _cargar_estilos() -> None:
    ruta = RAIZ / "assets" / "styles.css"
    if ruta.exists():
        st.markdown(f"<style>{ruta.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _formatear_numero(valor: object, decimales: int = 2) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    numero = float(valor)
    if numero == float("inf") or numero == float("-inf"):
        return "—"
    if abs(numero - round(numero)) < 1e-9:
        return f"{int(round(numero)):,}"
    return f"{numero:,.{decimales}f}".rstrip("0").rstrip(".")


def _formatear_porcentaje(valor: object) -> str:
    numero = limpiar_infinito(valor)
    return "—" if numero is None else f"{numero:.1f}%"


def _mostrar_tarjeta_alerta(fila: pd.Series) -> None:
    prioridad = PRIORIDAD_ETIQUETAS.get(str(fila["prioridad"]), str(fila["prioridad"]))
    with st.container(border=True):
        st.caption(f"PRIORIDAD {prioridad.upper()} · {fila['sucursal']}")
        st.subheader(str(fila["titulo_alerta"]))
        st.write(str(fila["mensaje_alerta"]))
        st.markdown(f"**Acción:** {fila['accion_recomendada']}")


@st.cache_resource(show_spinner=False)
def _crear_generador_ia(api_key: str, modelo: str):
    return crear_generador_gemini(api_key, modelo)


_cargar_estilos()

try:
    datos_base = cargar_datos()
except ErrorCargaDatos as error:
    st.error(str(error))
    st.stop()


with st.sidebar:
    st.markdown("## Datos de la semana")
    st.caption("Carga una orden nueva o trabaja con el archivo incluido en el reto.")

    fuente = st.radio(
        "Fuente de la orden",
        options=["Orden del reto", "Cargar otro CSV"],
        index=0,
    )

    orden_activa = datos_base["orden_compra_semana"].copy()
    fuente_texto = "Archivo original del reto"

    if fuente == "Cargar otro CSV":
        archivo = st.file_uploader(
            "Orden de compra (.csv)",
            type=["csv"],
            help="Debe contener sucursal, ingrediente_id y cantidad_formatos.",
        )
        if archivo is None:
            st.info("Carga un archivo para reemplazar la orden del reto.")
        else:
            try:
                orden_activa = leer_orden_csv(archivo.getvalue())
                fuente_texto = archivo.name
                st.success("Orden cargada correctamente.")
            except ErrorDashboard as error:
                st.error(str(error))
                st.stop()

    permitir_edicion = st.toggle(
        "Editar cantidades en la interfaz",
        value=False,
        help="Completa ingredientes omitidos con cero y recalcula al editar.",
    )

    if permitir_edicion:
        try:
            orden_editor = completar_orden_para_editor(
                orden=orden_activa,
                consumo_historico=datos_base["consumo_historico"],
                ingredientes=datos_base["ingredientes"],
            )
        except ErrorDashboard as error:
            st.error(str(error))
            st.stop()

        st.caption("Edita solo la columna Cantidad. Los formatos deben ser enteros.")
        orden_activa = st.data_editor(
            orden_editor,
            hide_index=True,
            use_container_width=True,
            height=390,
            disabled=["sucursal", "ingrediente_id"],
            num_rows="fixed",
            column_config={
                "sucursal": st.column_config.TextColumn("Sucursal"),
                "ingrediente_id": st.column_config.TextColumn("Ingrediente"),
                "cantidad_formatos": st.column_config.NumberColumn(
                    "Cantidad",
                    min_value=0,
                    step=1,
                    format="%d",
                ),
            },
            key="editor_orden",
        )
        fuente_texto += " · edición activa"

    st.divider()
    st.caption("El análisis se actualiza automáticamente con cada cambio.")


try:
    analisis = construir_analisis(datos_base, orden_compra=orden_activa)
except (
    ErrorDashboard,
    ErrorCalculoCompras,
    ErrorProyeccion,
    ErrorAlertas,
) as error:
    st.error("No se pudo completar el análisis de compras.")
    st.code(str(error))
    st.stop()


try:
    secretos_streamlit = st.secrets
except Exception:
    secretos_streamlit = None

clave_gemini, modelo_gemini = obtener_configuracion_gemini(secretos_streamlit)
generador_ia = None
error_configuracion_ia = None
if clave_gemini:
    try:
        generador_ia = _crear_generador_ia(clave_gemini, modelo_gemini)
    except ErrorAsistente as error:
        error_configuracion_ia = str(error)


st.markdown('<div class="eyebrow">OPERACIÓN SEMANAL · BARRIO PIZZA</div>', unsafe_allow_html=True)
st.title("Centro Inteligente de Compras")
st.write(
    "Revisión preventiva de órdenes, consumo proyectado e inventario para decidir qué corregir antes de comprar."
)
st.caption(f"Fuente activa: {fuente_texto}")

resumen = analisis.resumen
porcentaje_correcto = porcentaje_orden_correcta(resumen)

pestanas = st.tabs(
    [
        "Resumen ejecutivo",
        "Centro de alertas",
        "Orden corregida",
        "Calidad y modelo",
        "Asistente IA",
    ]
)


with pestanas[0]:
    st.subheader("Estado general de las órdenes")

    columnas_metricas = st.columns(5)
    columnas_metricas[0].metric("Alertas por revisar", resumen["alertas_total"])
    columnas_metricas[1].metric("Prioridad crítica", resumen["prioridad_critica"])
    columnas_metricas[2].metric(
        "Pedidos insuficientes",
        resumen["pedidos_insuficientes"] + resumen["ingredientes_omitidos"],
    )
    columnas_metricas[3].metric(
        "Excesos detectados",
        resumen["sobrepedidos"] + resumen["compras_innecesarias"],
    )
    columnas_metricas[4].metric("Orden sin corrección", f"{porcentaje_correcto:.1f}%")

    alertas = filtrar_resultados(analisis.resultados, solo_alertas=True)
    if alertas.empty:
        st.success("La orden no requiere correcciones.")
    else:
        primera = alertas.iloc[0]
        st.warning(
            f"Empiece por {primera['sucursal']} · {primera['nombre']}: "
            f"{primera['accion_recomendada']}"
        )

    col_grafico_1, col_grafico_2 = st.columns([1.25, 1])

    with col_grafico_1:
        st.markdown("#### Alertas por sucursal")
        por_sucursal = resumen_por_sucursal(analisis.resultados)
        if por_sucursal.empty:
            st.info("No existen alertas para graficar.")
        else:
            por_sucursal["Prioridad"] = por_sucursal["prioridad"].map(
                PRIORIDAD_ETIQUETAS
            )
            figura_sucursal = px.bar(
                por_sucursal,
                x="sucursal",
                y="cantidad",
                color="prioridad",
                barmode="stack",
                labels={"sucursal": "Sucursal", "cantidad": "Alertas"},
                color_discrete_map=COLORES_PRIORIDAD,
                category_orders={"prioridad": ["CRITICA", "ALTA", "MEDIA"]},
            )
            figura_sucursal.update_layout(
                legend_title_text="Prioridad",
                margin=dict(l=10, r=10, t=20, b=10),
                yaxis=dict(dtick=1),
            )
            st.plotly_chart(
                figura_sucursal,
                use_container_width=True,
                config={"displayModeBar": False},
            )

    with col_grafico_2:
        st.markdown("#### Resultado de la revisión")
        por_estado = resumen_por_estado(analisis.resultados)
        figura_estado = px.pie(
            por_estado,
            names="estado_etiqueta",
            values="cantidad",
            hole=0.58,
            color="estado_etiqueta",
            color_discrete_map=COLORES_ESTADO,
        )
        figura_estado.update_traces(textposition="inside", textinfo="percent+label")
        figura_estado.update_layout(
            showlegend=False,
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(
            figura_estado,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    st.markdown("#### Prioridades inmediatas")
    tarjetas = st.columns(min(3, max(1, len(alertas))))
    for indice, (_, fila) in enumerate(alertas.head(3).iterrows()):
        with tarjetas[indice]:
            _mostrar_tarjeta_alerta(fila)


with pestanas[1]:
    st.subheader("Bandeja de decisiones")
    st.caption("Filtra las alertas y abre cada caso para ver el cálculo completo.")

    sucursales_disponibles = sorted(analisis.resultados["sucursal"].dropna().unique())
    estados_disponibles = [
        estado
        for estado in ESTADO_ETIQUETAS
        if estado in analisis.resultados["estado"].unique()
    ]
    prioridades_disponibles = [
        prioridad
        for prioridad in ["CRITICA", "ALTA", "MEDIA"]
        if prioridad in analisis.resultados["prioridad"].unique()
    ]

    filtros = st.columns(3)
    filtro_sucursales = filtros[0].multiselect(
        "Sucursal",
        sucursales_disponibles,
        placeholder="Todas",
    )
    filtro_prioridades = filtros[1].multiselect(
        "Prioridad",
        prioridades_disponibles,
        format_func=lambda valor: PRIORIDAD_ETIQUETAS.get(valor, valor),
        placeholder="Todas",
    )
    filtro_estados = filtros[2].multiselect(
        "Tipo de resultado",
        estados_disponibles,
        format_func=lambda valor: ESTADO_ETIQUETAS.get(valor, valor),
        placeholder="Todos",
    )

    filtradas = filtrar_resultados(
        analisis.resultados,
        solo_alertas=True,
        sucursales=filtro_sucursales,
        estados=filtro_estados,
        prioridades=filtro_prioridades,
    )

    st.metric("Alertas visibles", len(filtradas))
    if filtradas.empty:
        st.info("No hay alertas que coincidan con los filtros.")
    else:
        st.dataframe(
            preparar_tabla_alertas(filtradas),
            hide_index=True,
            use_container_width=True,
            height=min(420, 90 + len(filtradas) * 46),
        )

        opciones = {
            f"{fila['prioridad']} · {fila['sucursal']} · {fila['nombre']} — {fila['titulo_alerta']}": (
                str(fila["sucursal"]),
                str(fila["ingrediente_id"]),
            )
            for _, fila in filtradas.iterrows()
        }
        seleccion = st.selectbox(
            "Abrir detalle",
            options=list(opciones),
        )
        sucursal, ingrediente_id = opciones[seleccion]
        caso = obtener_caso(
            analisis.resultados,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        st.divider()
        st.markdown(
            f"### {caso['nombre']} · {caso['sucursal']}"
        )
        st.caption(
            f"{PRIORIDAD_ETIQUETAS.get(str(caso['prioridad']), caso['prioridad'])} · "
            f"{ESTADO_ETIQUETAS.get(str(caso['estado']), caso['estado'])}"
        )
        st.write(str(caso["mensaje_alerta"]))
        st.markdown(f"**Acción recomendada:** {caso['accion_recomendada']}")

        metricas_caso = st.columns(5)
        metricas_caso[0].metric(
            "Consumo proyectado",
            f"{_formatear_numero(caso['consumo_proyectado_unidad_base'])} {caso.get('unidad_base', '')}",
        )
        metricas_caso[1].metric(
            "Inventario actual",
            f"{_formatear_numero(caso['stock_actual_unidad_base'])} {caso.get('unidad_base', '')}",
        )
        metricas_caso[2].metric(
            "Formatos solicitados",
            _formatear_numero(caso["cantidad_formatos_solicitados"]),
        )
        metricas_caso[3].metric(
            "Formatos recomendados",
            _formatear_numero(caso["formatos_recomendados"]),
        )
        metricas_caso[4].metric(
            "Cobertura con orden",
            _formatear_porcentaje(caso["cobertura_proyectada_pct"]),
        )

        proyeccion = proyeccion_del_caso(
            analisis.proyecciones,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        if proyeccion is None:
            st.error(
                "Este producto no puede proyectarse porque no existe en el catálogo."
            )
        else:
            serie = preparar_serie_detalle(
                analisis.datos["consumo_historico"],
                analisis.proyecciones,
                sucursal=sucursal,
                ingrediente_id=ingrediente_id,
            )
            figura_detalle = go.Figure()
            historico = serie.loc[serie["tipo"] == "Histórico"]
            figura_detalle.add_trace(
                go.Scatter(
                    x=historico["semana"],
                    y=historico["consumo_unidad_base"],
                    mode="lines+markers",
                    name="Consumo histórico",
                )
            )
            atipicos = historico.loc[historico["es_atipico"]]
            if not atipicos.empty:
                figura_detalle.add_trace(
                    go.Scatter(
                        x=atipicos["semana"],
                        y=atipicos["consumo_unidad_base"],
                        mode="markers",
                        marker=dict(size=14, symbol="x"),
                        name="Semana atípica",
                    )
                )
            proyectado = serie.loc[serie["tipo"] == "Proyección"]
            figura_detalle.add_trace(
                go.Scatter(
                    x=proyectado["semana"],
                    y=proyectado["consumo_unidad_base"],
                    mode="markers",
                    marker=dict(size=15, symbol="diamond"),
                    name="Proyección",
                )
            )
            figura_detalle.update_layout(
                title="Consumo histórico y próxima semana",
                xaxis_title="Semana",
                yaxis_title=str(caso["unidad_base"]),
                margin=dict(l=10, r=10, t=50, b=10),
                hovermode="x unified",
            )
            st.plotly_chart(
                figura_detalle,
                use_container_width=True,
                config={"displayModeBar": False},
            )

            with st.expander("Por qué se proyectó así", expanded=True):
                st.write(str(proyeccion["explicacion_proyeccion"]))
                columnas_modelo = st.columns(4)
                columnas_modelo[0].metric(
                    "Método",
                    METODO_ETIQUETAS.get(
                        str(proyeccion["metodo_proyeccion"]),
                        str(proyeccion["metodo_proyeccion"]),
                    ),
                )
                columnas_modelo[1].metric(
                    "MAE retrospectivo",
                    _formatear_numero(proyeccion["mae_backtest"]),
                )
                columnas_modelo[2].metric(
                    "WAPE retrospectivo",
                    _formatear_porcentaje(proyeccion["wape_backtest_pct"]),
                )
                columnas_modelo[3].metric(
                    "Semanas atípicas",
                    str(proyeccion["semanas_atipicas"] or "Ninguna"),
                )

            with st.expander("Ver cálculo de compra"):
                st.code(
                    "\n".join(
                        [
                            f"Consumo proyectado = {_formatear_numero(caso['consumo_proyectado_unidad_base'])} {caso['unidad_base']}",
                            f"Inventario actual = {_formatear_numero(caso['stock_actual_unidad_base'])} {caso['unidad_base']}",
                            f"Necesidad neta = {_formatear_numero(caso['necesidad_neta_unidad_base'])} {caso['unidad_base']}",
                            f"Formato = {caso['formato_compra']}",
                            f"Formatos recomendados = {_formatear_numero(caso['formatos_recomendados'])}",
                            f"Formatos solicitados = {_formatear_numero(caso['cantidad_formatos_solicitados'])}",
                        ]
                    )
                )


with pestanas[2]:
    st.subheader("Orden corregida por proveedor")
    st.caption(
        "La recomendación excluye productos desconocidos y respeta formatos completos de compra."
    )

    proveedores = sorted(analisis.orden_corregida["proveedor"].dropna().unique())
    filtro_proveedores = st.multiselect(
        "Proveedor",
        proveedores,
        placeholder="Todos los proveedores",
    )
    orden_filtrada = preparar_orden_por_proveedor(
        analisis.orden_corregida,
        proveedores=filtro_proveedores,
    )

    indicadores_orden = st.columns(3)
    indicadores_orden[0].metric("Proveedores", orden_filtrada["proveedor"].nunique())
    indicadores_orden[1].metric("Líneas de compra", len(orden_filtrada))
    indicadores_orden[2].metric("Sucursales", orden_filtrada["sucursal"].nunique())

    st.dataframe(
        orden_filtrada,
        hide_index=True,
        use_container_width=True,
        height=480,
    )

    descargas = st.columns(2)
    descargas[0].download_button(
        "Descargar orden corregida completa",
        data=dataframe_a_csv_bytes(analisis.orden_corregida),
        file_name="orden_corregida_barrio_pizza.csv",
        mime="text/csv",
        use_container_width=True,
    )
    descargas[1].download_button(
        "Descargar vista filtrada",
        data=dataframe_a_csv_bytes(orden_filtrada),
        file_name="orden_corregida_filtrada.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown("#### Separación lista para enviar")
    for proveedor, grupo in orden_filtrada.groupby("proveedor", sort=True):
        with st.expander(f"{proveedor} · {len(grupo)} líneas"):
            st.dataframe(
                grupo.drop(columns="proveedor"),
                hide_index=True,
                use_container_width=True,
            )
            st.download_button(
                f"Descargar orden de {proveedor}",
                data=dataframe_a_csv_bytes(grupo),
                file_name=f"orden_{str(proveedor).lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"descarga_{proveedor}",
            )


with pestanas[3]:
    st.subheader("Calidad de datos y trazabilidad del modelo")

    hallazgos = analisis.hallazgos.copy()
    columnas_calidad = st.columns(3)
    columnas_calidad[0].metric("Hallazgos", len(hallazgos))
    columnas_calidad[1].metric(
        "Errores",
        int((hallazgos["nivel"] == "ERROR").sum()) if not hallazgos.empty else 0,
    )
    columnas_calidad[2].metric(
        "Bloqueantes",
        int(hallazgos["bloqueante"].fillna(False).sum()) if not hallazgos.empty else 0,
    )

    if hallazgos.empty:
        st.success("No se encontraron problemas de calidad de datos.")
    else:
        st.dataframe(
            hallazgos,
            hide_index=True,
            use_container_width=True,
        )
        st.download_button(
            "Descargar reporte de calidad",
            data=dataframe_a_csv_bytes(hallazgos),
            file_name="reporte_calidad_datos.csv",
            mime="text/csv",
        )

    st.markdown("#### Métodos seleccionados")
    metodos = (
        analisis.proyecciones.groupby("metodo_proyeccion")
        .size()
        .rename("cantidad")
        .reset_index()
    )
    metodos["Método"] = metodos["metodo_proyeccion"].map(METODO_ETIQUETAS)
    figura_metodos = px.bar(
        metodos,
        x="Método",
        y="cantidad",
        labels={"cantidad": "Combinaciones"},
        text_auto=True,
    )
    figura_metodos.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=False,
    )
    st.plotly_chart(
        figura_metodos,
        use_container_width=True,
        config={"displayModeBar": False},
    )

    columnas_modelo_tabla = [
        "sucursal",
        "ingrediente_id",
        "consumo_proyectado_unidad_base",
        "metodo_proyeccion",
        "cantidad_atipicos",
        "semanas_atipicas",
        "mae_backtest",
        "wape_backtest_pct",
        "explicacion_proyeccion",
    ]
    tabla_modelos = analisis.proyecciones[columnas_modelo_tabla].copy()
    tabla_modelos["metodo_proyeccion"] = tabla_modelos[
        "metodo_proyeccion"
    ].map(METODO_ETIQUETAS)
    st.dataframe(
        tabla_modelos,
        hide_index=True,
        use_container_width=True,
        height=420,
    )

    with st.expander("Supuestos actuales del prototipo"):
        st.markdown(
            """
- S1 es la semana más antigua y S6 la más reciente.
- El inventario actual está disponible antes de la semana proyectada.
- La orden cubre una semana y no utiliza stock de seguridad adicional.
- Solo se compran formatos completos.
- Una fila omitida equivale a cero formatos solicitados.
- No se inventan precios, clientes, vencimientos ni tiempos de entrega que no están en los datos.
            """
        )

with pestanas[4]:
    st.subheader("Asistente de compras")
    st.caption(
        "Pregunta en lenguaje natural. Las cantidades siempre provienen del motor de cálculo verificado."
    )

    if generador_ia is not None:
        st.success(f"IA conectada · {modelo_gemini}")
        st.caption(
            "El modelo interpreta la pregunta y redacta la respuesta, pero no decide ni modifica cantidades."
        )
    else:
        st.info("Modo local verificado")
        st.caption(
            "El asistente funciona sin internet para preguntas directas. Al configurar Gemini, también entenderá preguntas más flexibles y seguimientos."
        )
        if error_configuracion_ia:
            with st.expander("Detalle de configuración"):
                st.code(error_configuracion_ia)

    st.markdown("#### Preguntas sugeridas")
    sugerencias = [
        "¿Qué debo revisar primero?",
        "¿Cuánta harina debe comprar Costa del Este?",
        "¿Qué están pidiendo de más?",
        "¿Quién provee la mozzarella?",
    ]
    columnas_sugerencias = st.columns(4)
    pregunta_sugerida = None
    for indice, sugerencia in enumerate(sugerencias):
        if columnas_sugerencias[indice].button(
            sugerencia,
            use_container_width=True,
            key=f"sugerencia_asistente_{indice}",
        ):
            pregunta_sugerida = sugerencia

    if "mensajes_asistente" not in st.session_state:
        st.session_state.mensajes_asistente = [
            {
                "role": "assistant",
                "content": (
                    "Hola. Puedo ayudarte a consultar recomendaciones, inventario, consumo proyectado, "
                    "alertas y proveedores."
                ),
                "modo": "local",
                "evidencia": [],
                "advertencia": None,
            }
        ]

    for mensaje in st.session_state.mensajes_asistente:
        with st.chat_message(mensaje["role"]):
            st.markdown(mensaje["content"])
            if mensaje.get("advertencia"):
                st.warning(mensaje["advertencia"])
            evidencia = mensaje.get("evidencia") or []
            if mensaje["role"] == "assistant" and evidencia:
                with st.expander("Datos usados para responder"):
                    for elemento in evidencia:
                        st.write(f"- {elemento}")

    pregunta_escrita = st.chat_input(
        "Ejemplo: ¿Cuántas cajas de mozzarella necesita Brisas del Golf?"
    )
    pregunta = pregunta_sugerida or pregunta_escrita

    if pregunta:
        mensaje_usuario = {"role": "user", "content": pregunta}
        st.session_state.mensajes_asistente.append(mensaje_usuario)
        with st.chat_message("user"):
            st.markdown(pregunta)

        historial = [
            {"role": mensaje["role"], "content": mensaje["content"]}
            for mensaje in st.session_state.mensajes_asistente[-8:]
        ]
        with st.chat_message("assistant"):
            with st.spinner("Consultando los datos..."):
                respuesta = responder_asistente(
                    pregunta,
                    analisis,
                    generador_llm=generador_ia,
                    historial=historial,
                )
            st.markdown(respuesta.respuesta)
            if respuesta.advertencia:
                st.warning(respuesta.advertencia)
            if respuesta.evidencia:
                with st.expander("Datos usados para responder"):
                    for elemento in respuesta.evidencia:
                        st.write(f"- {elemento}")

        st.session_state.mensajes_asistente.append(
            {
                "role": "assistant",
                "content": respuesta.respuesta,
                "modo": respuesta.modo,
                "evidencia": list(respuesta.evidencia),
                "advertencia": respuesta.advertencia,
            }
        )

    if st.button("Limpiar conversación", key="limpiar_asistente"):
        st.session_state.mensajes_asistente = []
        st.rerun()

