from __future__ import annotations

from html import escape
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
    proyeccion_del_caso,
    resumen_por_estado,
    resumen_por_sucursal,
)
from src.proyecciones import ErrorProyeccion


RAIZ = Path(__file__).resolve().parent
COLORES_PRIORIDAD = {
    "CRITICA": "#871D16",
    "ALTA": "#B84C00",
    "MEDIA": "#8A6500",
    "SIN_ALERTA": "#65655F",
}
COLORES_ESTADO = {
    "Pedido correcto": "#187144",
    "Sin compra necesaria": "#5D765E",
    "Pedido insuficiente": "#C9251A",
    "Sobrepedido": "#B84C00",
    "Ingrediente omitido": "#871D16",
    "Compra innecesaria": "#8A6500",
    "No evaluable": "#65655F",
}
COLOR_TEXTO = "#111111"
COLOR_MUTED = "#65655F"
COLOR_BORDE = "#DEDEDA"
COLOR_FONDO = "#FFFFFF"


st.set_page_config(
    page_title="Inteligencia de Compras · Barrio Pizza",
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


def _seguro(valor: object) -> str:
    """Escapa valores de datos antes de insertarlos en fragmentos HTML."""
    return escape(str(valor), quote=True)


def _tarjeta_metrica(
    etiqueta: str,
    valor: object,
    nota: str,
    tono: str = "neutral",
) -> None:
    st.markdown(
        f"""
        <div class="bp-metric bp-metric--{_seguro(tono)}">
          <div class="bp-metric-label">{_seguro(etiqueta)}</div>
          <div class="bp-metric-value">{_seguro(valor)}</div>
          <div class="bp-metric-note">{_seguro(nota)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _contexto_semana(consumo_historico: pd.DataFrame) -> str:
    semanas = consumo_historico.get("semana", pd.Series(dtype=str)).astype(str)
    numeros = pd.to_numeric(semanas.str.extract(r"(\d+)$")[0], errors="coerce")
    if numeros.dropna().empty:
        return "Ciclo semanal"
    return f"Proyección S{int(numeros.max()) + 1}"


def _encabezado_producto(
    *,
    fuente_datos: str,
    contexto_semana: str,
    ia_conectada: bool,
    modelo_ia: str,
) -> None:
    estado_ia = f"IA conectada · {modelo_ia}" if ia_conectada else "Modo local disponible"
    punto_ia = "ok" if ia_conectada else "warn"
    st.markdown(
        f"""
        <header class="bp-header" role="banner">
          <div>
            <div class="bp-wordmark">Barrio Pizza · Panamá</div>
            <h1>Inteligencia de compras</h1>
            <p>Centro de control semanal para detectar riesgos, corregir cantidades y preparar compras por proveedor.</p>
          </div>
          <div class="bp-status-grid" aria-label="Estado de la operación">
            <div class="bp-status-item">
              <span class="bp-status-label">Semana</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>{_seguro(contexto_semana)}</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">Fuente activa</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>{_seguro(fuente_datos)}</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">Motor de cálculo</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>Análisis listo</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">Asistente</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--{punto_ia}"></span><span>{_seguro(estado_ia)}</span></span>
            </div>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def _titulo_seccion(indice: str, titulo: str, descripcion: str) -> None:
    st.markdown(
        f'<div class="bp-section-kicker">{_seguro(indice)}</div>',
        unsafe_allow_html=True,
    )
    st.header(titulo)
    st.markdown(
        f'<p class="bp-section-intro">{_seguro(descripcion)}</p>',
        unsafe_allow_html=True,
    )


def _separador(texto: str) -> None:
    st.markdown(
        f'<div class="bp-divider-label">{_seguro(texto)}</div>',
        unsafe_allow_html=True,
    )


def _estilo_grafico(figura: go.Figure, *, altura: int = 360) -> go.Figure:
    figura.update_layout(
        height=altura,
        paper_bgcolor=COLOR_FONDO,
        plot_bgcolor=COLOR_FONDO,
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", color=COLOR_TEXTO, size=12),
        title_font=dict(family="Arial Narrow, Segoe UI, Arial, sans-serif", size=17, color=COLOR_TEXTO),
        margin=dict(l=28, r=28, t=42, b=38),
        hoverlabel=dict(bgcolor=COLOR_TEXTO, font_color="#FFFFFF", bordercolor=COLOR_TEXTO),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    figura.update_xaxes(
        showgrid=False,
        linecolor=COLOR_BORDE,
        tickfont=dict(color=COLOR_MUTED),
        title_font=dict(color=COLOR_MUTED),
    )
    figura.update_yaxes(
        gridcolor="#ECECE8",
        zeroline=False,
        linecolor=COLOR_BORDE,
        tickfont=dict(color=COLOR_MUTED),
        title_font=dict(color=COLOR_MUTED),
    )
    return figura


def _ajuste_alerta(fila: pd.Series) -> str:
    solicitado = limpiar_infinito(fila.get("cantidad_formatos_solicitados"))
    recomendado = limpiar_infinito(fila.get("formatos_recomendados"))
    if solicitado is None or recomendado is None:
        return "Revisar datos"
    diferencia = int(round(recomendado - solicitado))
    if diferencia > 0:
        return f"Agregar {diferencia}"
    if diferencia < 0:
        return f"Reducir {abs(diferencia)}"
    return "Sin cambio"


def _bandeja_alertas(filas: pd.DataFrame) -> None:
    for _, fila in filas.iterrows():
        prioridad_codigo = str(fila["prioridad"])
        prioridad = PRIORIDAD_ETIQUETAS.get(prioridad_codigo, prioridad_codigo)
        tono = {"CRITICA": "critical", "ALTA": "high", "MEDIA": "medium"}.get(
            prioridad_codigo,
            "neutral",
        )
        solicitado = _formatear_numero(fila["cantidad_formatos_solicitados"])
        recomendado = _formatear_numero(fila["formatos_recomendados"])
        st.markdown(
            f"""
            <div class="bp-alert-row bp-alert-row--{tono}">
              <div class="bp-alert-cell"><small>Prioridad</small><span class="bp-priority bp-priority--{tono}">{_seguro(prioridad)}</span></div>
              <div class="bp-alert-cell"><small>Sucursal</small><strong>{_seguro(fila['sucursal'])}</strong></div>
              <div class="bp-alert-cell"><small>Ingrediente</small><strong>{_seguro(fila['nombre'])}</strong></div>
              <div class="bp-alert-cell"><small>Solicitado → recomendado</small><strong>{_seguro(solicitado)} → {_seguro(recomendado)} · {_seguro(_ajuste_alerta(fila))}</strong></div>
              <div class="bp-alert-action"><small>Acción</small><strong>{_seguro(fila['accion_recomendada'])}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _orden_para_interfaz(orden: pd.DataFrame) -> pd.DataFrame:
    tabla = orden.copy()
    tabla["ajuste_interfaz"] = (
        tabla["cantidad_formatos_recomendada"] - tabla["cantidad_formatos_original"]
    )
    tabla["estado_interfaz"] = tabla["estado"].map(ESTADO_ETIQUETAS).fillna(tabla["estado"])
    tabla = tabla[
        [
            "proveedor",
            "sucursal",
            "nombre",
            "formato_compra",
            "cantidad_formatos_original",
            "cantidad_formatos_recomendada",
            "ajuste_interfaz",
            "cantidad_unidad_base_recomendada",
            "unidad_base",
            "estado_interfaz",
        ]
    ]
    return tabla.rename(
        columns={
            "proveedor": "Proveedor",
            "sucursal": "Sucursal",
            "nombre": "Ingrediente",
            "formato_compra": "Presentación",
            "cantidad_formatos_original": "Cantidad original",
            "cantidad_formatos_recomendada": "Cantidad recomendada",
            "ajuste_interfaz": "Ajuste",
            "cantidad_unidad_base_recomendada": "Total recomendado",
            "unidad_base": "Unidad",
            "estado_interfaz": "Resultado",
        }
    )


@st.cache_resource(show_spinner=False)
def _crear_generador_ia(api_key: str, modelo: str):
    return crear_generador_gemini(api_key, modelo)


_cargar_estilos()

try:
    datos_base = cargar_datos()
except ErrorCargaDatos as error:
    st.error(f"No pudimos cargar los datos base. {error}", icon="🚫")
    st.stop()


with st.sidebar:
    st.markdown(
        """
        <div class="bp-side-brand">
          <strong>BARRIO PIZZA</strong>
          <span>Control de compras</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### Preparar la revisión")
    st.caption("Elige la orden de trabajo. Cada cambio vuelve a ejecutar la auditoría completa.")

    fuente = st.radio(
        "1. Fuente de la orden",
        options=["Orden del reto", "Cargar otro CSV"],
        index=0,
    )

    orden_activa = datos_base["orden_compra_semana"].copy()
    fuente_texto = "Archivo original del reto"

    if fuente == "Cargar otro CSV":
        archivo = st.file_uploader(
            "2. Orden de compra (.csv)",
            type=["csv"],
            help="Debe contener sucursal, ingrediente_id y cantidad_formatos.",
        )
        if archivo is None:
            st.info("Selecciona un CSV para iniciar la validación.")
        else:
            try:
                orden_activa = leer_orden_csv(archivo.getvalue())
                fuente_texto = archivo.name
                st.success("CSV recibido. La orden fue validada y recalculada.")
            except ErrorDashboard as error:
                st.error(f"No pudimos usar este archivo. {error}")
                st.stop()

    permitir_edicion = st.toggle(
        "3. Activar editor de cantidades",
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

        st.caption("Edita Cantidad. Sucursal e ingrediente quedan protegidos.")
        orden_activa = st.data_editor(
            orden_editor,
            hide_index=True,
            width="stretch",
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
    st.markdown(
        """
        <div class="bp-inline-status">
          <span class="bp-dot bp-dot--ok"></span>
          Recálculo automático activo
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Flujo: cargar → auditar → corregir → descargar")
    st.markdown(
        """
        <div class="bp-side-step"><b>1</b><span>Revisa las prioridades del resumen.</span></div>
        <div class="bp-side-step"><b>2</b><span>Abre el expediente de cada alerta.</span></div>
        <div class="bp-side-step"><b>3</b><span>Descarga la orden lista por proveedor.</span></div>
        """,
        unsafe_allow_html=True,
    )


try:
    analisis = construir_analisis(datos_base, orden_compra=orden_activa)
except (
    ErrorDashboard,
    ErrorCalculoCompras,
    ErrorProyeccion,
    ErrorAlertas,
) as error:
    st.error(
        "La revisión se detuvo porque los datos contienen un error bloqueante. "
        "Corrige el archivo indicado y vuelve a cargarlo."
    )
    with st.expander("Ver detalle técnico del error"):
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


_encabezado_producto(
    fuente_datos=fuente_texto,
    contexto_semana=_contexto_semana(analisis.datos["consumo_historico"]),
    ia_conectada=generador_ia is not None,
    modelo_ia=modelo_gemini,
)

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
    _titulo_seccion(
        "01 · Decidir",
        "Resumen ejecutivo",
        "Lo importante de la revisión semanal, ordenado por riesgo y listo para actuar.",
    )

    alertas = filtrar_resultados(analisis.resultados, solo_alertas=True)
    faltantes = resumen["pedidos_insuficientes"] + resumen["ingredientes_omitidos"]
    excesos = resumen["sobrepedidos"] + resumen["compras_innecesarias"]
    columnas_metricas = st.columns(5)
    with columnas_metricas[0]:
        _tarjeta_metrica("Alertas totales", resumen["alertas_total"], "Casos que requieren decisión", "brand")
    with columnas_metricas[1]:
        _tarjeta_metrica("Críticas", resumen["prioridad_critica"], "Resolver antes de aprobar", "critical")
    with columnas_metricas[2]:
        _tarjeta_metrica("Riesgo de quiebre", faltantes, "Insuficientes u omitidos", "high")
    with columnas_metricas[3]:
        _tarjeta_metrica("Sobrepedidos", excesos, "Capital o inventario de más", "medium")
    with columnas_metricas[4]:
        _tarjeta_metrica("Orden correcta", f"{porcentaje_correcto:.1f}%", "Combinaciones sin ajuste", "good")

    if alertas.empty:
        st.success("Revisión completa: la orden no requiere correcciones.")
    else:
        primera = alertas.iloc[0]
        st.markdown(
            f"""
            <div class="bp-action" role="status">
              <div class="bp-action-index">01</div>
              <div>
                <div class="bp-action-label">Primera acción recomendada · {_seguro(primera['sucursal'])} · {_seguro(primera['nombre'])}</div>
                <div class="bp-action-copy">{_seguro(primera['accion_recomendada'])}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    _separador("Mapa operativo")
    col_grafico_1, col_grafico_2 = st.columns([1.15, 1])

    with col_grafico_1:
        por_sucursal = resumen_por_sucursal(analisis.resultados)
        if por_sucursal.empty:
            st.info("No existen alertas para graficar.")
        else:
            figura_sucursal = px.bar(
                por_sucursal,
                x="sucursal",
                y="cantidad",
                color="prioridad",
                barmode="stack",
                title="Alertas por sucursal",
                labels={"sucursal": "Sucursal", "cantidad": "Alertas", "prioridad": "Prioridad"},
                color_discrete_map=COLORES_PRIORIDAD,
                category_orders={"prioridad": ["CRITICA", "ALTA", "MEDIA"]},
            )
            figura_sucursal.update_layout(legend_title_text="Prioridad")
            figura_sucursal.update_yaxes(dtick=1)
            st.plotly_chart(
                _estilo_grafico(figura_sucursal),
                width="stretch",
                config={"displayModeBar": False},
            )

    with col_grafico_2:
        por_estado = resumen_por_estado(analisis.resultados).sort_values(
            "cantidad",
            ascending=True,
        )
        figura_estado = px.bar(
            por_estado,
            x="cantidad",
            y="estado_etiqueta",
            orientation="h",
            title="Resultado de la revisión",
            text="cantidad",
            color="estado_etiqueta",
            labels={"cantidad": "Combinaciones", "estado_etiqueta": "Resultado"},
            color_discrete_map=COLORES_ESTADO,
        )
        figura_estado.update_traces(textposition="outside", cliponaxis=False)
        figura_estado.update_layout(showlegend=False)
        figura_estado.update_xaxes(dtick=10)
        st.plotly_chart(
            _estilo_grafico(figura_estado),
            width="stretch",
            config={"displayModeBar": False},
        )

    _separador("Tres prioridades inmediatas")
    if alertas.empty:
        st.caption("Sin prioridades abiertas.")
    else:
        _bandeja_alertas(alertas.head(3))


with pestanas[1]:
    _titulo_seccion(
        "02 · Investigar",
        "Centro de alertas",
        "Una bandeja de decisiones: filtra, compara la cantidad pedida y abre el expediente auditable de cada caso.",
    )

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

    with st.container(border=True):
        st.markdown("#### Filtrar bandeja")
        filtros = st.columns(3)
        filtro_sucursales = filtros[0].multiselect(
            "Sucursal",
            sucursales_disponibles,
            placeholder="Todas las sucursales",
        )
        filtro_prioridades = filtros[1].multiselect(
            "Prioridad",
            prioridades_disponibles,
            format_func=lambda valor: PRIORIDAD_ETIQUETAS.get(valor, valor),
            placeholder="Todas las prioridades",
        )
        filtro_estados = filtros[2].multiselect(
            "Tipo de problema",
            estados_disponibles,
            format_func=lambda valor: ESTADO_ETIQUETAS.get(valor, valor),
            placeholder="Todos los tipos",
        )

    filtradas = filtrar_resultados(
        analisis.resultados,
        solo_alertas=True,
        sucursales=filtro_sucursales,
        estados=filtro_estados,
        prioridades=filtro_prioridades,
    )

    st.markdown(
        f'<div class="bp-inline-status"><span class="bp-dot bp-dot--warn"></span>{len(filtradas)} alertas visibles</div>',
        unsafe_allow_html=True,
    )
    if filtradas.empty:
        st.info("No hay alertas con esta combinación de filtros. Ajusta la búsqueda para continuar.")
    else:
        _bandeja_alertas(filtradas)

        opciones = {
            f"{PRIORIDAD_ETIQUETAS.get(str(fila['prioridad']), fila['prioridad'])} · {fila['sucursal']} · {fila['nombre']} — {fila['titulo_alerta']}": (
                str(fila["sucursal"]),
                str(fila["ingrediente_id"]),
            )
            for _, fila in filtradas.iterrows()
        }
        seleccion = st.selectbox(
            "Abrir expediente de alerta",
            options=list(opciones),
            help="Muestra el impacto, la acción, el histórico y el cálculo de la alerta seleccionada.",
        )
        sucursal, ingrediente_id = opciones[seleccion]
        caso = obtener_caso(
            analisis.resultados,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        _separador("Expediente operativo")
        prioridad_caso = PRIORIDAD_ETIQUETAS.get(str(caso["prioridad"]), caso["prioridad"])
        estado_caso = ESTADO_ETIQUETAS.get(str(caso["estado"]), caso["estado"])
        tono_caso = {"CRITICA": "critical", "ALTA": "high", "MEDIA": "medium"}.get(
            str(caso["prioridad"]),
            "neutral",
        )
        st.markdown(
            f"""
            <div class="bp-case-banner">
              <span class="bp-priority bp-priority--{tono_caso}">{_seguro(prioridad_caso)}</span>
              <h3>{_seguro(caso['nombre'])} · {_seguro(caso['sucursal'])}</h3>
              <strong>{_seguro(estado_caso)} — {_seguro(caso['titulo_alerta'])}</strong>
              <p>{_seguro(caso['mensaje_alerta'])}</p>
              <div class="bp-case-action">Acción recomendada: {_seguro(caso['accion_recomendada'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        metricas_caso = st.columns(5)
        unidad = str(caso.get("unidad_base", ""))
        with metricas_caso[0]:
            _tarjeta_metrica("Consumo proyectado", _formatear_numero(caso["consumo_proyectado_unidad_base"]), unidad)
        with metricas_caso[1]:
            _tarjeta_metrica("Inventario actual", _formatear_numero(caso["stock_actual_unidad_base"]), unidad)
        with metricas_caso[2]:
            _tarjeta_metrica("Solicitado", _formatear_numero(caso["cantidad_formatos_solicitados"]), "formatos")
        with metricas_caso[3]:
            _tarjeta_metrica("Recomendado", _formatear_numero(caso["formatos_recomendados"]), str(caso.get("formato_compra", "formatos")), "brand")
        with metricas_caso[4]:
            _tarjeta_metrica("Cobertura", _formatear_porcentaje(caso["cobertura_proyectada_pct"]), "consumo proyectado")

        proyeccion = proyeccion_del_caso(
            analisis.proyecciones,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        if proyeccion is None:
            st.error(
                "No se puede proyectar este producto porque no existe en el catálogo. "
                "Corrige el identificador o registra el ingrediente antes de aprobar la compra."
            )
        else:
            _separador("Consumo y proyección")
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
                    line=dict(color="#111111", width=3),
                    marker=dict(color="#111111", size=7),
                )
            )
            atipicos = historico.loc[historico["es_atipico"]]
            if not atipicos.empty:
                figura_detalle.add_trace(
                    go.Scatter(
                        x=atipicos["semana"],
                        y=atipicos["consumo_unidad_base"],
                        mode="markers",
                        marker=dict(size=14, symbol="x", color="#B84C00", line=dict(width=2)),
                        name="Semana atípica",
                    )
                )
            proyectado = serie.loc[serie["tipo"] == "Proyección"]
            punto_anterior = historico.iloc[-1]
            figura_detalle.add_trace(
                go.Scatter(
                    x=[punto_anterior["semana"], proyectado.iloc[0]["semana"]],
                    y=[punto_anterior["consumo_unidad_base"], proyectado.iloc[0]["consumo_unidad_base"]],
                    mode="lines+markers",
                    line=dict(color="#C9251A", width=3, dash="dot"),
                    marker=dict(size=[0, 15], symbol="diamond", color="#C9251A"),
                    name="Próxima semana",
                )
            )
            figura_detalle.update_layout(
                title="Consumo histórico y próxima semana",
                xaxis_title="Semana",
                yaxis_title=str(caso["unidad_base"]),
                hovermode="x unified",
            )
            st.plotly_chart(
                _estilo_grafico(figura_detalle, altura=390),
                width="stretch",
                config={"displayModeBar": False},
            )

            with st.expander("Cómo se calculó la proyección", expanded=True):
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

            with st.expander("Ver cálculo de compra auditable"):
                tabla_calculo = pd.DataFrame(
                    [
                        ("1. Consumo proyectado", f"{_formatear_numero(caso['consumo_proyectado_unidad_base'])} {caso['unidad_base']}"),
                        ("2. Inventario disponible", f"{_formatear_numero(caso['stock_actual_unidad_base'])} {caso['unidad_base']}"),
                        ("3. Necesidad neta", f"{_formatear_numero(caso['necesidad_neta_unidad_base'])} {caso['unidad_base']}"),
                        ("4. Presentación de compra", str(caso["formato_compra"])),
                        ("5. Cantidad recomendada", f"{_formatear_numero(caso['formatos_recomendados'])} formatos"),
                        ("6. Cantidad solicitada", f"{_formatear_numero(caso['cantidad_formatos_solicitados'])} formatos"),
                    ],
                    columns=["Paso", "Valor usado"],
                )
                st.table(tabla_calculo)


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
