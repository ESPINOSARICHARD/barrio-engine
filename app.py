from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.alertas import ErrorAlertas
from src.aprobaciones import (
    CONFIANZA_ALTA,
    CONFIANZA_MEDIA,
    CONFIANZA_REVISION,
    DECISION_APLICAR,
    DECISION_CATALOGO,
    DECISION_DEVOLVER,
    DECISION_ETIQUETAS_EN,
    DECISION_ETIQUETAS_ES,
    DECISION_MANTENER,
    ErrorAprobacion,
    aplicar_recomendaciones_alta_confianza,
    construir_casos_aprobacion,
    construir_contexto_aprobacion,
    crear_huella_revision,
    generar_bitacora_decisiones,
    generar_mensaje_proveedor,
    generar_mensaje_sucursal,
    generar_orden_aprobada,
    opciones_decision,
    registrar_decision,
    resumir_aprobacion,
    simular_escenario_demanda,
)
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
    preparar_reparacion_orden,
    preparar_serie_detalle,
    proyeccion_del_caso,
    resumen_por_estado,
    resumen_por_sucursal,
)
from src.presentacion import (
    aplicar_nombres_visibles,
    nombre_ingrediente_visible,
    reemplazar_nombre_visible,
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
COLORES_ESTADO_EN = {
    "Correct order": "#187144",
    "No purchase needed": "#5D765E",
    "Underordered": "#C9251A",
    "Overordered": "#B84C00",
    "Missing ingredient": "#871D16",
    "Unnecessary purchase": "#8A6500",
    "Not evaluable": "#65655F",
}
COLOR_TEXTO = "#111111"
COLOR_MUTED = "#65655F"
COLOR_BORDE = "#DEDEDA"
COLOR_FONDO = "#FFFFFF"

PRIORIDAD_ETIQUETAS_EN = {
    "CRITICA": "Critical",
    "ALTA": "High",
    "MEDIA": "Medium",
    "SIN_ALERTA": "No alert",
}
ESTADO_ETIQUETAS_EN = {
    "CORRECTO": "Correct order",
    "SIN_COMPRA_NECESARIA": "No purchase needed",
    "PEDIDO_INSUFICIENTE": "Underordered",
    "SOBREPEDIDO": "Overordered",
    "INGREDIENTE_OMITIDO": "Missing ingredient",
    "COMPRA_INNECESARIA": "Unnecessary purchase",
    "NO_EVALUABLE": "Not evaluable",
}
METODO_ETIQUETAS_EN = {
    "promedio_simple": "Simple average",
    "promedio_ponderado": "Weighted average",
    "mediana": "Historical median",
    "promedio_ponderado_robusto": "Robust weighted average",
    "tendencia_lineal": "Linear trend",
}
FORMATO_INGLES = {
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


st.set_page_config(
    page_title="Barrio Pizza · Inteligencia de Compras",
    page_icon="🍕",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "idioma_ui" not in st.session_state:
    st.session_state.idioma_ui = "ES"


def _en_ingles() -> bool:
    return st.session_state.get("idioma_ui", "ES") == "EN"


def _texto(espanol: str, ingles: str) -> str:
    return ingles if _en_ingles() else espanol


def _idioma_codigo() -> str:
    return "en" if _en_ingles() else "es"


def _nombre_visible(
    ingrediente_id: object,
    nombre: object,
) -> str:
    return nombre_ingrediente_visible(
        ingrediente_id,
        nombre,
        _idioma_codigo(),
    )


def _etiqueta_prioridad(codigo: object) -> str:
    clave = str(codigo)
    etiquetas = PRIORIDAD_ETIQUETAS_EN if _en_ingles() else PRIORIDAD_ETIQUETAS
    return etiquetas.get(clave, clave)


def _etiqueta_estado(codigo: object) -> str:
    clave = str(codigo)
    etiquetas = ESTADO_ETIQUETAS_EN if _en_ingles() else ESTADO_ETIQUETAS
    return etiquetas.get(clave, clave)


def _etiqueta_metodo(codigo: object) -> str:
    clave = str(codigo)
    etiquetas = METODO_ETIQUETAS_EN if _en_ingles() else METODO_ETIQUETAS
    return etiquetas.get(clave, clave)


def _etiqueta_confianza(codigo: object) -> str:
    clave = str(codigo)
    if _en_ingles():
        return {
            CONFIANZA_ALTA: "High",
            CONFIANZA_MEDIA: "Medium",
            CONFIANZA_REVISION: "Human review",
        }.get(clave, clave)
    return {
        CONFIANZA_ALTA: "Alta",
        CONFIANZA_MEDIA: "Media",
        CONFIANZA_REVISION: "Revisión humana",
    }.get(clave, clave)


def _tono_confianza(codigo: object) -> str:
    return {
        CONFIANZA_ALTA: "good",
        CONFIANZA_MEDIA: "medium",
        CONFIANZA_REVISION: "critical",
    }.get(str(codigo), "neutral")


def _imagen_data_uri(ruta: Path) -> str:
    if not ruta.exists():
        return ""
    extension = ruta.suffix.lower().lstrip(".") or "png"
    codificada = base64.b64encode(ruta.read_bytes()).decode("ascii")
    return f"data:image/{extension};base64,{codificada}"


def _cargar_estilos() -> None:
    ruta = RAIZ / "assets" / "styles.css"
    if ruta.exists():
        st.markdown(f"<style>{ruta.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _instalar_experiencia_de_marca() -> None:
    """Instala recursos visuales globales sin intervenir en los cálculos."""

    marca = _imagen_data_uri(RAIZ / "assets" / "barrio-wordmark.png")
    cursor = _imagen_data_uri(RAIZ / "assets" / "pizza-cursor.png")
    if marca:
        st.markdown(
            f"""
            <style>
              .stApp::before {{
                background-image: url('{marca}');
              }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    if not cursor:
        return

    components.html(
        f"""
        <script>
        (() => {{
          const hostWindow = window.parent;
          const doc = hostWindow.document;
          const root = doc.documentElement;

          if (hostWindow.__barrioDashboardCleanup) {{
            hostWindow.__barrioDashboardCleanup();
          }}

          const cursorNode = doc.createElement('div');
          cursorNode.id = 'bp-pizza-cursor';
          cursorNode.setAttribute('aria-hidden', 'true');
          cursorNode.innerHTML = '<img src="{cursor}" alt="">';
          doc.body.appendChild(cursorNode);

          const finePointer = hostWindow.matchMedia('(pointer: fine)');
          let frame = 0;
          let pointerX = 0;
          let pointerY = 0;

          const syncPointerMode = () => {{
            root.classList.toggle('bp-cursor-ready', finePointer.matches);
            if (!finePointer.matches) cursorNode.classList.remove('bp-cursor-visible');
          }};
          const moveCursor = (event) => {{
            if (!finePointer.matches) return;
            pointerX = event.clientX;
            pointerY = event.clientY;
            cursorNode.classList.add('bp-cursor-visible');
            if (frame) return;
            frame = hostWindow.requestAnimationFrame(() => {{
              cursorNode.style.transform = `translate3d(${{pointerX - 4}}px, ${{pointerY - 4}}px, 0)`;
              frame = 0;
            }});
          }};
          const pressCursor = () => cursorNode.classList.add('bp-cursor-pressed');
          const releaseCursor = () => cursorNode.classList.remove('bp-cursor-pressed');
          const hideCursor = () => cursorNode.classList.remove('bp-cursor-visible');

          let observedSidebar = null;
          const sidebarResizeObserver = new hostWindow.ResizeObserver(() => syncSidebar());
          const syncSidebar = () => {{
            const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
            if (sidebar !== observedSidebar) {{
              sidebarResizeObserver.disconnect();
              observedSidebar = sidebar;
              if (sidebar) sidebarResizeObserver.observe(sidebar);
            }}
            const expanded = Boolean(
              sidebar &&
              (sidebar.getAttribute('aria-expanded') === 'true' || sidebar.getBoundingClientRect().width > 80)
            );
            root.classList.toggle('bp-sidebar-open', expanded);
          }};

          const openedPopovers = new hostWindow.WeakSet();
          const keepPopoverHeaderVisible = () => {{
            doc.querySelectorAll('[data-testid="stPopoverBody"]').forEach((popover) => {{
              if (!openedPopovers.has(popover)) {{
                openedPopovers.add(popover);
                hostWindow.requestAnimationFrame(() => {{ popover.scrollTop = 0; }});
              }}
            }});
          }};

          const dashboardObserver = new hostWindow.MutationObserver(() => {{
            syncSidebar();
            keepPopoverHeaderVisible();
          }});
          dashboardObserver.observe(doc.body, {{ childList: true, subtree: true }});

          doc.addEventListener('pointermove', moveCursor, {{ passive: true }});
          doc.addEventListener('pointerdown', pressCursor, {{ passive: true }});
          doc.addEventListener('pointerup', releaseCursor, {{ passive: true }});
          doc.addEventListener('pointercancel', releaseCursor, {{ passive: true }});
          doc.addEventListener('pointerleave', hideCursor, {{ passive: true }});
          finePointer.addEventListener('change', syncPointerMode);

          syncPointerMode();
          syncSidebar();
          keepPopoverHeaderVisible();

          hostWindow.__barrioDashboardCleanup = () => {{
            dashboardObserver.disconnect();
            sidebarResizeObserver.disconnect();
            doc.removeEventListener('pointermove', moveCursor);
            doc.removeEventListener('pointerdown', pressCursor);
            doc.removeEventListener('pointerup', releaseCursor);
            doc.removeEventListener('pointercancel', releaseCursor);
            doc.removeEventListener('pointerleave', hideCursor);
            finePointer.removeEventListener('change', syncPointerMode);
            if (frame) hostWindow.cancelAnimationFrame(frame);
            cursorNode.remove();
            root.classList.remove('bp-cursor-ready', 'bp-sidebar-open');
          }};
        }})();
        </script>
        """,
        height=0,
        scrolling=False,
    )


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
    compacto: bool = False,
) -> None:
    clase_valor = "bp-metric-value bp-metric-value--compact" if compacto else "bp-metric-value"
    st.markdown(
        f"""
        <div class="bp-metric bp-metric--{_seguro(tono)}" role="group" aria-label="{_seguro(etiqueta)}: {_seguro(valor)}">
          <div class="bp-metric-label">{_seguro(etiqueta)}</div>
          <div class="{clase_valor}">{_seguro(valor)}</div>
          <div class="bp-metric-note">{_seguro(nota)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _contexto_semana(consumo_historico: pd.DataFrame) -> str:
    semanas = consumo_historico.get("semana", pd.Series(dtype=str)).astype(str)
    numeros = pd.to_numeric(semanas.str.extract(r"(\d+)$")[0], errors="coerce")
    if numeros.dropna().empty:
        return _texto("Ciclo semanal", "Weekly cycle")
    prefijo = _texto("Proyección", "Forecast")
    return f"{prefijo} S{int(numeros.max()) + 1}"


def _encabezado_producto(
    *,
    fuente_datos: str,
    contexto_semana: str,
    ia_conectada: bool,
) -> None:
    estado_ia = (
        _texto("IA conectada", "AI connected")
        if ia_conectada
        else _texto("Modo local disponible", "Local mode available")
    )
    punto_ia = "ok" if ia_conectada else "warn"
    logo = _imagen_data_uri(RAIZ / "assets" / "barrio-wordmark.png")
    clase_idioma = "bp-header--en" if _en_ingles() else "bp-header--es"
    st.markdown(
        f"""
        <header class="bp-header {clase_idioma}" role="banner">
          <div class="bp-header-main">
            <img class="bp-header-logo" src="{logo}" alt="Barrio Pizza">
            <div>
              <div class="bp-wordmark">{_texto('Panamá · Desde 2015', 'Panama · Since 2015')}</div>
              <h1>{_texto('Inteligencia', 'Purchasing')} <span>{_texto('de compras', 'intelligence')}</span></h1>
              <p>{_texto('Centro de control semanal para detectar riesgos, corregir cantidades y preparar compras por proveedor.', 'Weekly control center to detect risks, correct quantities and prepare supplier-ready orders.')}</p>
            </div>
          </div>
          <div class="bp-status-grid" aria-label="{_texto('Estado de la operación', 'Operation status')}">
            <div class="bp-status-item">
              <span class="bp-status-label">{_texto('Semana', 'Week')}</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>{_seguro(contexto_semana)}</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">{_texto('Fuente activa', 'Active source')}</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>{_seguro(fuente_datos)}</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">{_texto('Motor de cálculo', 'Calculation engine')}</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--ok"></span><span>{_texto('Análisis listo', 'Analysis ready')}</span></span>
            </div>
            <div class="bp-status-item">
              <span class="bp-status-label">BARRIO AI</span>
              <span class="bp-status-value"><span class="bp-dot bp-dot--{punto_ia}"></span><span>{_seguro(estado_ia)}</span></span>
            </div>
          </div>
          <div class="bp-header-tagline">{_texto('Del barrio y para el barrio', 'From the barrio, for the barrio')}</div>
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
        f'<div class="bp-divider-label" role="heading" aria-level="3">{_seguro(texto)}</div>',
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
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
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
        return _texto("Revisar datos", "Review data")
    diferencia = int(round(recomendado - solicitado))
    if diferencia > 0:
        return f"{_texto('Agregar', 'Add')} {diferencia}"
    if diferencia < 0:
        return f"{_texto('Reducir', 'Reduce')} {abs(diferencia)}"
    return _texto("Sin cambio", "No change")


def _detalle_formato_ingles(
    cantidad: int,
    formato_compra: object,
    cantidad_base: object,
    unidad: object,
) -> str:
    singular_es = str(formato_compra or "formatos").strip().split()[0].lower()
    singular, plural = FORMATO_INGLES.get(singular_es, ("format", "formats"))
    nombre = singular if cantidad == 1 else plural
    return f"{cantidad} {nombre} ({_formatear_numero(cantidad_base)} {unidad})"


def _alerta_en_ingles(fila: pd.Series) -> tuple[str, str, str]:
    estado = str(fila["estado"])
    sucursal = str(fila["sucursal"])
    ingrediente = _nombre_visible(
        fila.get("ingrediente_id", ""),
        fila.get("nombre", fila.get("ingrediente_id", "product")),
    )
    solicitado = int(fila["cantidad_formatos_solicitados"])
    recomendado_valor = limpiar_infinito(fila.get("formatos_recomendados"))
    recomendado = int(recomendado_valor) if recomendado_valor is not None else 0
    formato = fila.get("formato_compra")
    unidad = fila.get("unidad_base", "")

    if estado == "NO_EVALUABLE":
        identificador = str(fila.get("ingrediente_id", ingrediente))
        return (
            "Unregistered product",
            f"{sucursal} requested {solicitado} format(s) of {identificador}, but it is not in the catalog and cannot be evaluated.",
            "Correct the identifier or register its unit, purchasing format and supplier before approving the order.",
        )
    if estado == "INGREDIENTE_OMITIDO":
        detalle = _detalle_formato_ingles(
            recomendado,
            formato,
            fila.get("compra_recomendada_unidad_base"),
            unidad,
        )
        return (
            "Missing ingredient",
            f"{sucursal} did not include {ingrediente}, but {detalle} are recommended to cover forecast consumption.",
            f"Add {detalle} of {ingrediente} to the order.",
        )
    if estado == "PEDIDO_INSUFICIENTE":
        faltantes = int(fila.get("faltante_formatos", 0) or 0)
        detalle = _detalle_formato_ingles(
            faltantes,
            formato,
            faltantes * float(fila.get("unidad_base_por_formato", 0) or 0),
            unidad,
        )
        return (
            "Underordered",
            f"{sucursal} requested {solicitado} format(s) of {ingrediente}, but {recomendado} are recommended. The order is short by {detalle} and may run out during the forecast week.",
            f"Increase the order by {detalle} of {ingrediente}.",
        )
    if estado in {"SOBREPEDIDO", "COMPRA_INNECESARIA"}:
        excesos = int(fila.get("exceso_formatos", 0) or 0)
        detalle = _detalle_formato_ingles(
            excesos,
            formato,
            excesos * float(fila.get("unidad_base_por_formato", 0) or 0),
            unidad,
        )
        riesgo = "increases expiry risk" if bool(fila.get("es_perecedero_bool")) else "ties up unnecessary inventory"
        return (
            "Unnecessary purchase" if estado == "COMPRA_INNECESARIA" else "Overordered",
            f"{sucursal} requested {solicitado} format(s) of {ingrediente}, but {recomendado} are recommended. The order has {detalle} too many and {riesgo}.",
            f"Reduce the order by {detalle} of {ingrediente}.",
        )
    if estado == "CORRECTO":
        return (
            "Correct order",
            f"{sucursal} requested the recommended {solicitado} format(s) of {ingrediente}.",
            "No changes are required.",
        )
    return (
        "No purchase needed",
        f"Current inventory of {ingrediente} at {sucursal} covers forecast consumption and no additional formats were requested.",
        "No changes are required.",
    )


def _contenido_alerta(fila: pd.Series) -> tuple[str, str, str]:
    if _en_ingles():
        return _alerta_en_ingles(fila)
    ingrediente_id = fila.get("ingrediente_id", "")
    nombre_original = fila.get("nombre", ingrediente_id)
    return (
        reemplazar_nombre_visible(
            fila["titulo_alerta"],
            ingrediente_id=ingrediente_id,
            nombre_original=nombre_original,
        ),
        reemplazar_nombre_visible(
            fila["mensaje_alerta"],
            ingrediente_id=ingrediente_id,
            nombre_original=nombre_original,
        ),
        reemplazar_nombre_visible(
            fila["accion_recomendada"],
            ingrediente_id=ingrediente_id,
            nombre_original=nombre_original,
        ),
    )


def _explicacion_proyeccion(proyeccion: pd.Series) -> str:
    if not _en_ingles():
        return str(proyeccion["explicacion_proyeccion"])
    metodo = str(proyeccion["metodo_proyeccion"])
    mae = limpiar_infinito(proyeccion.get("mae_backtest"))
    mae_texto = _formatear_numero(mae) if mae is not None else "not available"
    if metodo == "tendencia_lineal":
        pendiente = float(proyeccion.get("pendiente_semanal", 0) or 0)
        direccion = "upward" if pendiente > 0 else "downward"
        return (
            f"Consistent {direccion} trend: slope of {pendiente:.2f} units per week, "
            f"R²={float(proyeccion.get('r2_tendencia', 0) or 0):.3f} and backtest MAE={mae_texto}."
        )
    if metodo == "promedio_ponderado_robusto":
        semanas = str(proyeccion.get("semanas_atipicas") or "none")
        cantidad = int(proyeccion.get("cantidad_atipicos", 0) or 0)
        return (
            f"Robust weighted average: reduced the influence of {cantidad} outlier week(s) "
            f"({semanas}) and weighted recent weeks more heavily. Backtest MAE={mae_texto}."
        )
    if metodo == "promedio_ponderado":
        return f"Weighted average: recent weeks receive more weight. Backtest MAE={mae_texto}."
    if metodo == "mediana":
        return f"Historical median: represents the central level without being dominated by isolated variations. Backtest MAE={mae_texto}."
    return f"Simple average: the most parsimonious method within the accepted error margin. Backtest MAE={mae_texto}."


def _bandeja_alertas(filas: pd.DataFrame) -> None:
    for _, fila in filas.iterrows():
        prioridad_codigo = str(fila["prioridad"])
        prioridad = _etiqueta_prioridad(prioridad_codigo)
        _, _, accion = _contenido_alerta(fila)
        tono = {"CRITICA": "critical", "ALTA": "high", "MEDIA": "medium"}.get(
            prioridad_codigo,
            "neutral",
        )
        solicitado = _formatear_numero(fila["cantidad_formatos_solicitados"])
        recomendado = _formatear_numero(fila["formatos_recomendados"])
        nombre_visible = _nombre_visible(fila["ingrediente_id"], fila["nombre"])
        st.markdown(
            f"""
            <div class="bp-alert-row bp-alert-row--{tono}" role="group" aria-label="{_texto('Alerta', 'Alert')} {_seguro(prioridad)} {_texto('de', 'for')} {_seguro(nombre_visible)} {_texto('en', 'at')} {_seguro(fila['sucursal'])}">
              <div class="bp-alert-cell"><small>{_texto('Prioridad', 'Priority')}</small><span class="bp-priority bp-priority--{tono}">{_seguro(prioridad)}</span></div>
              <div class="bp-alert-cell"><small>{_texto('Sucursal', 'Location')}</small><strong>{_seguro(fila['sucursal'])}</strong></div>
              <div class="bp-alert-cell"><small>{_texto('Ingrediente', 'Ingredient')}</small><strong>{_seguro(nombre_visible)}</strong></div>
              <div class="bp-alert-cell"><small>{_texto('Solicitado → recomendado', 'Requested → recommended')}</small><strong>{_seguro(solicitado)} → {_seguro(recomendado)} · {_seguro(_ajuste_alerta(fila))}</strong></div>
              <div class="bp-alert-action"><small>{_texto('Acción', 'Action')}</small><strong>{_seguro(accion)}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _orden_para_interfaz(orden: pd.DataFrame) -> pd.DataFrame:
    tabla = aplicar_nombres_visibles(orden, idioma=_idioma_codigo())
    tabla["ajuste_interfaz"] = (
        tabla["cantidad_formatos_recomendada"] - tabla["cantidad_formatos_original"]
    )
    tabla["estado_interfaz"] = tabla["estado"].map(
        ESTADO_ETIQUETAS_EN if _en_ingles() else ESTADO_ETIQUETAS
    ).fillna(tabla["estado"])
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
    nombres = (
        {
            "proveedor": "Supplier",
            "sucursal": "Location",
            "nombre": "Ingredient",
            "formato_compra": "Purchase format",
            "cantidad_formatos_original": "Original quantity",
            "cantidad_formatos_recomendada": "Recommended quantity",
            "ajuste_interfaz": "Adjustment",
            "cantidad_unidad_base_recomendada": "Recommended total",
            "unidad_base": "Unit",
            "estado_interfaz": "Result",
        }
        if _en_ingles()
        else {
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
    return tabla.rename(columns=nombres)


def _orden_aprobada_para_interfaz(orden: pd.DataFrame) -> pd.DataFrame:
    tabla = aplicar_nombres_visibles(orden, idioma=_idioma_codigo())
    etiquetas = DECISION_ETIQUETAS_EN if _en_ingles() else DECISION_ETIQUETAS_ES
    tabla["decision_interfaz"] = tabla["decision_aprobacion"].map(etiquetas).fillna(
        _texto("Sin alerta", "No alert")
    )
    tabla = tabla[
        [
            "proveedor",
            "sucursal",
            "nombre",
            "formato_compra",
            "cantidad_formatos_solicitados",
            "formatos_recomendados",
            "cantidad_formatos_aprobada",
            "ajuste_formatos_aprobado",
            "cantidad_unidad_base_aprobada",
            "unidad_base",
            "decision_interfaz",
        ]
    ]
    nombres = (
        {
            "proveedor": "Supplier",
            "sucursal": "Location",
            "nombre": "Ingredient",
            "formato_compra": "Purchase format",
            "cantidad_formatos_solicitados": "Original quantity",
            "formatos_recomendados": "System recommendation",
            "cantidad_formatos_aprobada": "Approved quantity",
            "ajuste_formatos_aprobado": "Approved adjustment",
            "cantidad_unidad_base_aprobada": "Approved total",
            "unidad_base": "Unit",
            "decision_interfaz": "Human decision",
        }
        if _en_ingles()
        else {
            "proveedor": "Proveedor",
            "sucursal": "Sucursal",
            "nombre": "Ingrediente",
            "formato_compra": "Presentación",
            "cantidad_formatos_solicitados": "Cantidad original",
            "formatos_recomendados": "Recomendación del sistema",
            "cantidad_formatos_aprobada": "Cantidad aprobada",
            "ajuste_formatos_aprobado": "Ajuste aprobado",
            "cantidad_unidad_base_aprobada": "Total aprobado",
            "unidad_base": "Unidad",
            "decision_interfaz": "Decisión humana",
        }
    )
    return tabla.rename(columns=nombres)


@st.cache_resource(show_spinner=False)
def _crear_generador_ia(api_key: str, modelo: str):
    return crear_generador_gemini(api_key, modelo)


_cargar_estilos()
_instalar_experiencia_de_marca()

with st.container(key="bp_language_switch"):
    st.segmented_control(
        "Idioma / Language",
        options=["ES", "EN"],
        key="idioma_ui",
        label_visibility="collapsed",
        help="Cambiar idioma / Switch language",
    )

try:
    datos_base = cargar_datos()
except ErrorCargaDatos as error:
    st.error(
        _texto(
            f"No pudimos cargar los datos base. {error}",
            f"We could not load the base data. {error}",
        ),
        icon="🚫",
    )
    st.stop()


with st.sidebar:
    logo_sidebar = _imagen_data_uri(RAIZ / "assets" / "barrio-wordmark.png")
    st.markdown(
        f"""
        <div class="bp-side-brand">
          <img src="{logo_sidebar}" alt="Barrio Pizza">
          <div><strong>{_texto('CONTROL', 'CONTROL')}</strong><span>{_texto('Inteligencia de compras', 'Purchasing intelligence')}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"### {_texto('Preparar la revisión', 'Prepare the review')}")
    st.caption(
        _texto(
            "Elige la orden de trabajo. Cada cambio vuelve a ejecutar la auditoría completa.",
            "Choose the working order. Every change reruns the full audit.",
        )
    )

    fuente = st.radio(
        _texto("1. Fuente de la orden", "1. Order source"),
        options=["Orden del reto", "Cargar otro CSV"],
        index=0,
        format_func=lambda valor: {
            "Orden del reto": _texto("Orden del reto", "Challenge order"),
            "Cargar otro CSV": _texto("Cargar otro CSV", "Upload another CSV"),
        }[valor],
    )

    orden_activa = datos_base["orden_compra_semana"].copy()
    fuente_texto = _texto("Archivo original del reto", "Original challenge file")

    if fuente == "Cargar otro CSV":
        archivo = st.file_uploader(
            _texto("2. Orden de compra (.csv)", "2. Purchase order (.csv)"),
            type=["csv"],
            help=_texto(
                "Debe contener sucursal, ingrediente_id y cantidad_formatos.",
                "It must contain sucursal, ingrediente_id and cantidad_formatos.",
            ),
        )
        if archivo is None:
            st.info(_texto("Selecciona un CSV para iniciar la validación.", "Select a CSV to start validation."))
        else:
            try:
                orden_activa = leer_orden_csv(archivo.getvalue())
                fuente_texto = archivo.name
                st.success(
                    _texto(
                        "CSV recibido. La orden fue validada y recalculada.",
                        "CSV received. The order was validated and recalculated.",
                    )
                )
            except ErrorDashboard as error:
                st.error(
                    _texto(
                        f"No pudimos usar este archivo. {error}",
                        f"We could not use this file. {error}",
                    )
                )
                st.stop()

    permitir_edicion = st.toggle(
        _texto("3. Activar editor de cantidades", "3. Enable quantity editor"),
        value=False,
        help=_texto(
            "Completa ingredientes omitidos con cero y recalcula al editar.",
            "Adds missing ingredients with zero and recalculates after edits.",
        ),
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

        st.caption(
            _texto(
                "Edita Cantidad. Sucursal e ingrediente quedan protegidos; el CSV conserva sus identificadores técnicos.",
                "Edit Quantity. Location and ingredient remain protected; the CSV keeps its technical identifiers.",
            )
        )
        catalogo_editor = aplicar_nombres_visibles(
            datos_base["ingredientes"],
            idioma=_idioma_codigo(),
        )[["ingrediente_id", "nombre"]]
        orden_editor = orden_editor.merge(
            catalogo_editor,
            on="ingrediente_id",
            how="left",
        )
        orden_editor["nombre"] = orden_editor["nombre"].fillna(
            orden_editor["ingrediente_id"]
        )
        orden_editada = st.data_editor(
            orden_editor,
            hide_index=True,
            width="stretch",
            height=390,
            disabled=["sucursal", "ingrediente_id", "nombre"],
            num_rows="fixed",
            column_order=["sucursal", "nombre", "cantidad_formatos"],
            column_config={
                "sucursal": st.column_config.TextColumn(
                    _texto("Sucursal", "Location"),
                    width="small",
                ),
                "ingrediente_id": None,
                "nombre": st.column_config.TextColumn(
                    _texto("Ingrediente", "Ingredient"),
                    width="small",
                ),
                "cantidad_formatos": st.column_config.NumberColumn(
                    _texto("Cant.", "Qty."),
                    min_value=0,
                    step=1,
                    format="%d",
                    width="small",
                ),
            },
            key="editor_orden",
        )
        orden_activa = orden_editada[
            ["sucursal", "ingrediente_id", "cantidad_formatos"]
        ].copy()
        fuente_texto += _texto(" · edición activa", " · editing active")

    st.divider()
    st.markdown(
        f"""
        <div class="bp-inline-status">
          <span class="bp-dot bp-dot--ok"></span>
          {_texto('Recálculo automático activo', 'Automatic recalculation active')}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(_texto("Flujo: cargar → auditar → corregir → descargar", "Flow: upload → audit → correct → download"))
    st.markdown(
        f"""
        <div class="bp-side-step"><b>1</b><span>{_texto('Revisa las prioridades del resumen.', 'Review the priorities in the summary.')}</span></div>
        <div class="bp-side-step"><b>2</b><span>{_texto('Abre el expediente de cada alerta.', 'Open the case file for each alert.')}</span></div>
        <div class="bp-side-step"><b>3</b><span>{_texto('Descarga la orden lista por proveedor.', 'Download the supplier-ready order.')}</span></div>
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
        _texto(
            "La revisión se detuvo porque los datos contienen un error bloqueante. "
            "Corrige el archivo indicado y vuelve a cargarlo.",
            "The review stopped because the data contains a blocking error. "
            "Correct the indicated file and upload it again.",
        )
    )
    with st.expander(_texto("Ver detalle técnico del error", "View technical error details")):
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


casos_aprobacion = construir_casos_aprobacion(analisis.resultados)
huella_revision = crear_huella_revision(analisis.resultados)
revision_previa = st.session_state.get("revision_aprobacion")
revision_reiniciada = bool(
    revision_previa and revision_previa.get("huella") != huella_revision
)
if not revision_previa or revision_previa.get("huella") != huella_revision:
    st.session_state.revision_aprobacion = {
        "huella": huella_revision,
        "decisiones": {},
    }
    if revision_reiniciada:
        st.session_state.mensajes_asistente = []

decisiones_aprobacion = st.session_state.revision_aprobacion["decisiones"]
estado_aprobacion = resumir_aprobacion(
    casos_aprobacion,
    decisiones_aprobacion,
)
contexto_aprobacion = construir_contexto_aprobacion(
    casos_aprobacion,
    decisiones_aprobacion,
)
orden_aprobada: pd.DataFrame | None = None
if estado_aprobacion["lista_para_aprobar"]:
    try:
        orden_aprobada = generar_orden_aprobada(
            analisis.evaluacion,
            casos_aprobacion,
            decisiones_aprobacion,
        )
    except ErrorAprobacion:
        orden_aprobada = None


_encabezado_producto(
    fuente_datos=fuente_texto,
    contexto_semana=_contexto_semana(analisis.datos["consumo_historico"]),
    ia_conectada=generador_ia is not None,
)

if revision_reiniciada:
    st.toast(
        _texto(
            "La orden cambió: se inició una nueva revisión y se limpió el contexto anterior de Barrio AI.",
            "The order changed: a new review was started and Barrio AI's previous context was cleared.",
        )
    )

resumen = analisis.resumen
porcentaje_correcto = porcentaje_orden_correcta(resumen)
contexto_escenario: dict[str, object] = {"configurado": False}

pestanas = st.tabs(
    [
        _texto("Resumen ejecutivo", "Executive summary"),
        _texto("Centro de alertas", "Alert center"),
        _texto("Centro de aprobación", "Approval center"),
        _texto("Orden corregida", "Corrected order"),
        _texto("Calidad y modelo", "Quality and model"),
    ]
)


with pestanas[0]:
    _titulo_seccion(
        _texto("01 · Decidir", "01 · Decide"),
        _texto("Resumen ejecutivo", "Executive summary"),
        _texto(
            "Lo importante de la revisión semanal, ordenado por riesgo y listo para actuar.",
            "The weekly review essentials, ranked by risk and ready for action.",
        ),
    )

    alertas = filtrar_resultados(analisis.resultados, solo_alertas=True)
    faltantes = resumen["pedidos_insuficientes"] + resumen["ingredientes_omitidos"]
    excesos = resumen["sobrepedidos"] + resumen["compras_innecesarias"]
    columnas_metricas = st.columns(3)
    with columnas_metricas[0]:
        _tarjeta_metrica(_texto("Alertas totales", "Total alerts"), resumen["alertas_total"], _texto("Casos que requieren decisión", "Cases requiring a decision"), "brand")
    with columnas_metricas[1]:
        _tarjeta_metrica(_texto("Críticas", "Critical"), resumen["prioridad_critica"], _texto("Resolver antes de aprobar", "Resolve before approval"), "critical")
    with columnas_metricas[2]:
        _tarjeta_metrica(_texto("Riesgo de quiebre", "Stockout risk"), faltantes, _texto("Insuficientes u omitidos", "Underordered or missing"), "high")
    st.markdown(
        '<div class="bp-metric-row-gap" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    columnas_metricas_secundarias = st.columns(2)
    with columnas_metricas_secundarias[0]:
        _tarjeta_metrica(_texto("Sobrepedidos", "Overorders"), excesos, _texto("Capital o inventario de más", "Excess capital or inventory"), "medium")
    with columnas_metricas_secundarias[1]:
        _tarjeta_metrica(_texto("Orden correcta", "Correct order"), f"{porcentaje_correcto:.1f}%", _texto("Combinaciones sin ajuste", "Combinations needing no adjustment"), "good")

    if alertas.empty:
        st.success(_texto("Revisión completa: la orden no requiere correcciones.", "Review complete: the order needs no corrections."))
    else:
        primera = alertas.iloc[0]
        _, _, primera_accion = _contenido_alerta(primera)
        st.markdown(
            f"""
            <div class="bp-action" role="status">
              <div class="bp-action-index">01</div>
              <div>
                <div class="bp-action-label">{_texto('Primera acción recomendada', 'First recommended action')} · {_seguro(primera['sucursal'])} · {_seguro(_nombre_visible(primera['ingrediente_id'], primera['nombre']))}</div>
                <div class="bp-action-copy">{_seguro(primera_accion)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    _separador(_texto("Mapa operativo", "Operating map"))
    col_grafico_1, col_grafico_2 = st.columns([1.15, 1])

    with col_grafico_1:
        por_sucursal = resumen_por_sucursal(analisis.resultados)
        if por_sucursal.empty:
            st.info(_texto("No existen alertas para graficar.", "There are no alerts to chart."))
        else:
            por_sucursal["prioridad_ui"] = por_sucursal["prioridad"].map(
                PRIORIDAD_ETIQUETAS_EN if _en_ingles() else PRIORIDAD_ETIQUETAS
            )
            colores_prioridad_ui = {
                _etiqueta_prioridad(codigo): color
                for codigo, color in COLORES_PRIORIDAD.items()
            }
            figura_sucursal = px.bar(
                por_sucursal,
                x="sucursal",
                y="cantidad",
                color="prioridad_ui",
                barmode="stack",
                title=_texto("Alertas por sucursal", "Alerts by location"),
                labels={"sucursal": _texto("Sucursal", "Location"), "cantidad": _texto("Alertas", "Alerts"), "prioridad_ui": _texto("Prioridad", "Priority")},
                color_discrete_map=colores_prioridad_ui,
                category_orders={"prioridad_ui": [_etiqueta_prioridad(codigo) for codigo in ["CRITICA", "ALTA", "MEDIA"]]},
            )
            figura_sucursal.update_layout(legend_title_text=_texto("Prioridad", "Priority"))
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
        por_estado["estado_etiqueta"] = por_estado["estado"].map(
            ESTADO_ETIQUETAS_EN if _en_ingles() else ESTADO_ETIQUETAS
        )
        figura_estado = px.bar(
            por_estado,
            x="cantidad",
            y="estado_etiqueta",
            orientation="h",
            title=_texto("Resultado de la revisión", "Review result"),
            text="cantidad",
            color="estado_etiqueta",
            labels={"cantidad": _texto("Combinaciones", "Combinations"), "estado_etiqueta": _texto("Resultado", "Result")},
            color_discrete_map=COLORES_ESTADO_EN if _en_ingles() else COLORES_ESTADO,
        )
        figura_estado.update_traces(textposition="outside", cliponaxis=False)
        figura_estado.update_layout(showlegend=False)
        figura_estado.update_xaxes(dtick=10)
        st.plotly_chart(
            _estilo_grafico(figura_estado),
            width="stretch",
            config={"displayModeBar": False},
        )

    with st.expander(
        _texto(
            "Simulador de demanda · probar un evento o promoción",
            "Demand simulator · test an event or promotion",
        )
    ):
        st.caption(
            _texto(
                "Cambia temporalmente la proyección para responder “¿qué pasaría si…?”. El escenario no modifica la orden activa ni las decisiones guardadas.",
                "Temporarily change the forecast to answer “what if…?”. The scenario does not modify the active order or saved decisions.",
            )
        )
        controles_escenario = st.columns([1, 1, 1.1])
        todas_sucursales = _texto("Toda la operación", "All locations")
        todos_ingredientes = _texto("Todos los ingredientes", "All ingredients")
        sucursal_escenario = controles_escenario[0].selectbox(
            _texto("Sucursal del escenario", "Scenario location"),
            [todas_sucursales]
            + sorted(analisis.resultados["sucursal"].dropna().unique()),
            key="simulador_sucursal",
        )
        catalogo_simulador = aplicar_nombres_visibles(
            analisis.datos["ingredientes"],
            idioma=_idioma_codigo(),
        )
        opciones_ingrediente = {
            str(fila["nombre"]): str(fila["ingrediente_id"])
            for _, fila in catalogo_simulador.sort_values("nombre").iterrows()
        }
        ingrediente_escenario_etiqueta = controles_escenario[1].selectbox(
            _texto("Ingrediente del escenario", "Scenario ingredient"),
            [todos_ingredientes] + list(opciones_ingrediente),
            key="simulador_ingrediente",
        )
        variacion_escenario = controles_escenario[2].slider(
            _texto("Variación esperada", "Expected variation"),
            min_value=-20,
            max_value=50,
            value=10,
            step=5,
            format="%+d%%",
            key="simulador_variacion",
        )
        sucursales_objetivo = (
            None
            if sucursal_escenario == todas_sucursales
            else [sucursal_escenario]
        )
        ingredientes_objetivo = (
            None
            if ingrediente_escenario_etiqueta == todos_ingredientes
            else [opciones_ingrediente[ingrediente_escenario_etiqueta]]
        )
        escenario = simular_escenario_demanda(
            ingredientes=analisis.datos["ingredientes"],
            inventario_actual=analisis.datos["inventario_actual"],
            orden_compra_semana=analisis.datos["orden_compra_semana"],
            proyecciones=analisis.proyecciones,
            variacion_pct=variacion_escenario,
            sucursales=sucursales_objetivo,
            ingrediente_ids=ingredientes_objetivo,
        )
        faltantes_escenario = (
            escenario.resumen["pedidos_insuficientes"]
            + escenario.resumen["ingredientes_omitidos"]
        )
        metricas_escenario = st.columns(3)
        with metricas_escenario[0]:
            _tarjeta_metrica(
                _texto("Alertas base", "Base alerts"),
                resumen["alertas_total"],
                _texto("orden activa", "active order"),
            )
        with metricas_escenario[1]:
            _tarjeta_metrica(
                _texto("Alertas del escenario", "Scenario alerts"),
                escenario.resumen["alertas_total"],
                f"{variacion_escenario:+d}% {_texto('de demanda', 'demand')}",
                "brand",
            )
        with metricas_escenario[2]:
            _tarjeta_metrica(
                _texto("Riesgos de quiebre", "Stockout risks"),
                faltantes_escenario,
                _texto("en el escenario", "in the scenario"),
                "high" if faltantes_escenario else "good",
            )

        comparacion = analisis.resultados[
            ["sucursal", "ingrediente_id", "nombre", "formatos_recomendados"]
        ].merge(
            escenario.resultados[
                ["sucursal", "ingrediente_id", "formatos_recomendados"]
            ],
            on=["sucursal", "ingrediente_id"],
            how="inner",
            suffixes=("_base", "_escenario"),
        )
        comparacion["ajuste_escenario"] = (
            comparacion["formatos_recomendados_escenario"]
            - comparacion["formatos_recomendados_base"]
        )
        comparacion = comparacion.loc[
            comparacion["ajuste_escenario"].fillna(0) != 0
        ]
        comparacion = aplicar_nombres_visibles(
            comparacion,
            idioma=_idioma_codigo(),
        )
        contexto_escenario = {
            "configurado": True,
            "variacion_pct": variacion_escenario,
            "sucursal": (
                "TODAS"
                if sucursales_objetivo is None
                else sucursales_objetivo[0]
            ),
            "ingrediente_id": (
                "TODOS"
                if ingredientes_objetivo is None
                else ingredientes_objetivo[0]
            ),
            "alertas_base": resumen["alertas_total"],
            "alertas_escenario": escenario.resumen["alertas_total"],
            "riesgos_quiebre_escenario": faltantes_escenario,
            "cambios_formatos": comparacion[
                [
                    "sucursal",
                    "ingrediente_id",
                    "nombre",
                    "formatos_recomendados_base",
                    "formatos_recomendados_escenario",
                    "ajuste_escenario",
                ]
            ]
            .head(20)
            .where(pd.notna(comparacion.head(20)), None)
            .to_dict(orient="records"),
        }
        if comparacion.empty:
            st.info(
                _texto(
                    "Con este escenario no cambian los formatos recomendados.",
                    "This scenario does not change the recommended purchase formats.",
                )
            )
        else:
            tabla_escenario = comparacion[
                [
                    "sucursal",
                    "nombre",
                    "formatos_recomendados_base",
                    "formatos_recomendados_escenario",
                    "ajuste_escenario",
                ]
            ].rename(
                columns={
                    "sucursal": _texto("Sucursal", "Location"),
                    "nombre": _texto("Ingrediente", "Ingredient"),
                    "formatos_recomendados_base": _texto("Base", "Base"),
                    "formatos_recomendados_escenario": _texto("Escenario", "Scenario"),
                    "ajuste_escenario": _texto("Cambio", "Change"),
                }
            )
            st.dataframe(tabla_escenario, hide_index=True, width="stretch")

    _separador(_texto("Tres prioridades inmediatas", "Three immediate priorities"))
    if alertas.empty:
        st.caption(_texto("Sin prioridades abiertas.", "No open priorities."))
    else:
        _bandeja_alertas(alertas.head(3))


with pestanas[1]:
    _titulo_seccion(
        _texto("02 · Investigar", "02 · Investigate"),
        _texto("Centro de alertas", "Alert center"),
        _texto(
            "Una bandeja de decisiones: filtra, compara la cantidad pedida y abre el expediente auditable de cada caso.",
            "A decision inbox: filter, compare requested quantities and open the auditable case file for each alert.",
        ),
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
        st.markdown(f"#### {_texto('Filtrar bandeja', 'Filter inbox')}")
        filtros = st.columns(3)
        filtro_sucursales = filtros[0].multiselect(
            _texto("Sucursal", "Location"),
            sucursales_disponibles,
            placeholder=_texto("Todas las sucursales", "All locations"),
        )
        filtro_prioridades = filtros[1].multiselect(
            _texto("Prioridad", "Priority"),
            prioridades_disponibles,
            format_func=_etiqueta_prioridad,
            placeholder=_texto("Todas las prioridades", "All priorities"),
        )
        filtro_estados = filtros[2].multiselect(
            _texto("Tipo de problema", "Issue type"),
            estados_disponibles,
            format_func=_etiqueta_estado,
            placeholder=_texto("Todos los tipos", "All issue types"),
        )

    filtradas = filtrar_resultados(
        analisis.resultados,
        solo_alertas=True,
        sucursales=filtro_sucursales,
        estados=filtro_estados,
        prioridades=filtro_prioridades,
    )

    st.markdown(
        f'<div class="bp-inline-status"><span class="bp-dot bp-dot--warn"></span>{len(filtradas)} {_texto("alertas visibles", "visible alerts")}</div>',
        unsafe_allow_html=True,
    )
    if filtradas.empty:
        st.info(
            _texto(
                "No hay alertas con esta combinación de filtros. Ajusta la búsqueda para continuar.",
                "There are no alerts for this filter combination. Adjust the search to continue.",
            )
        )
    else:
        _bandeja_alertas(filtradas)

        opciones = {
            f"{_etiqueta_prioridad(fila['prioridad'])} · {fila['sucursal']} · {_nombre_visible(fila['ingrediente_id'], fila['nombre'])} — {_contenido_alerta(fila)[0]}": (
                str(fila["sucursal"]),
                str(fila["ingrediente_id"]),
            )
            for _, fila in filtradas.iterrows()
        }
        seleccion = st.selectbox(
            _texto("Abrir expediente de alerta", "Open alert case file"),
            options=list(opciones),
            help=_texto(
                "Muestra el impacto, la acción, el histórico y el cálculo de la alerta seleccionada.",
                "Shows the impact, action, history and calculation for the selected alert.",
            ),
        )
        sucursal, ingrediente_id = opciones[seleccion]
        caso = obtener_caso(
            analisis.resultados,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        _separador(_texto("Expediente operativo", "Operational case file"))
        prioridad_caso = _etiqueta_prioridad(caso["prioridad"])
        estado_caso = _etiqueta_estado(caso["estado"])
        titulo_caso, mensaje_caso, accion_caso = _contenido_alerta(caso)
        tono_caso = {"CRITICA": "critical", "ALTA": "high", "MEDIA": "medium"}.get(
            str(caso["prioridad"]),
            "neutral",
        )
        st.markdown(
            f"""
            <div class="bp-case-banner">
              <span class="bp-priority bp-priority--{tono_caso}">{_seguro(prioridad_caso)}</span>
              <div class="bp-case-title" role="heading" aria-level="3">{_seguro(_nombre_visible(caso['ingrediente_id'], caso['nombre']))} · {_seguro(caso['sucursal'])}</div>
              <strong>{_seguro(estado_caso)} — {_seguro(titulo_caso)}</strong>
              <p>{_seguro(mensaje_caso)}</p>
              <div class="bp-case-action">{_texto('Acción recomendada', 'Recommended action')}: {_seguro(accion_caso)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        metricas_caso = st.columns(3)
        unidad = str(caso.get("unidad_base", ""))
        with metricas_caso[0]:
            _tarjeta_metrica(_texto("Consumo proyectado", "Forecast consumption"), _formatear_numero(caso["consumo_proyectado_unidad_base"]), unidad)
        with metricas_caso[1]:
            _tarjeta_metrica(_texto("Inventario actual", "Current inventory"), _formatear_numero(caso["stock_actual_unidad_base"]), unidad)
        with metricas_caso[2]:
            _tarjeta_metrica(_texto("Solicitado", "Requested"), _formatear_numero(caso["cantidad_formatos_solicitados"]), _texto("formatos", "formats"))
        metricas_caso_secundarias = st.columns(2)
        with metricas_caso_secundarias[0]:
            _tarjeta_metrica(_texto("Recomendado", "Recommended"), _formatear_numero(caso["formatos_recomendados"]), str(caso.get("formato_compra", _texto("formatos", "formats"))), "brand")
        with metricas_caso_secundarias[1]:
            _tarjeta_metrica(_texto("Cobertura", "Coverage"), _formatear_porcentaje(caso["cobertura_proyectada_pct"]), _texto("consumo proyectado", "forecast consumption"))

        proyeccion = proyeccion_del_caso(
            analisis.proyecciones,
            sucursal=sucursal,
            ingrediente_id=ingrediente_id,
        )

        if proyeccion is None:
            st.error(
                _texto(
                    "No se puede proyectar este producto porque no existe en el catálogo. "
                    "Corrige el identificador o registra el ingrediente antes de aprobar la compra.",
                    "This product cannot be forecast because it is not in the catalog. "
                    "Correct the identifier or register the ingredient before approving the purchase.",
                )
            )
        else:
            _separador(_texto("Consumo y proyección", "Consumption and forecast"))
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
                    name=_texto("Consumo histórico", "Historical consumption"),
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
                        name=_texto("Semana atípica", "Outlier week"),
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
                    name=_texto("Próxima semana", "Next week"),
                )
            )
            figura_detalle.update_layout(
                title=_texto("Consumo histórico y próxima semana", "Historical consumption and next week"),
                xaxis_title=_texto("Semana", "Week"),
                yaxis_title=str(caso["unidad_base"]),
                hovermode="x unified",
            )
            st.plotly_chart(
                _estilo_grafico(figura_detalle, altura=390),
                width="stretch",
                config={"displayModeBar": False},
            )

            with st.expander(_texto("Cómo se calculó la proyección", "How the forecast was calculated"), expanded=True):
                st.write(_explicacion_proyeccion(proyeccion))
                columnas_modelo = st.columns(4)
                with columnas_modelo[0]:
                    _tarjeta_metrica(
                        _texto("Método", "Method"),
                        _etiqueta_metodo(proyeccion["metodo_proyeccion"]),
                        _texto("modelo seleccionado", "selected model"),
                        "brand",
                        compacto=True,
                    )
                with columnas_modelo[1]:
                    _tarjeta_metrica(_texto("MAE retrospectivo", "Backtest MAE"), _formatear_numero(proyeccion["mae_backtest"]), _texto("error absoluto", "absolute error"))
                with columnas_modelo[2]:
                    _tarjeta_metrica(_texto("WAPE retrospectivo", "Backtest WAPE"), _formatear_porcentaje(proyeccion["wape_backtest_pct"]), _texto("error porcentual", "percentage error"))
                with columnas_modelo[3]:
                    _tarjeta_metrica(_texto("Semanas atípicas", "Outlier weeks"), str(proyeccion["semanas_atipicas"] or _texto("Ninguna", "None")), _texto("detectadas en la serie", "detected in the series"))

            with st.expander(_texto("Ver cálculo de compra auditable", "View auditable purchase calculation")):
                tabla_calculo = pd.DataFrame(
                    [
                        (_texto("1. Consumo proyectado", "1. Forecast consumption"), f"{_formatear_numero(caso['consumo_proyectado_unidad_base'])} {caso['unidad_base']}"),
                        (_texto("2. Inventario disponible", "2. Available inventory"), f"{_formatear_numero(caso['stock_actual_unidad_base'])} {caso['unidad_base']}"),
                        (_texto("3. Necesidad neta", "3. Net requirement"), f"{_formatear_numero(caso['necesidad_neta_unidad_base'])} {caso['unidad_base']}"),
                        (_texto("4. Presentación de compra", "4. Purchase format"), str(caso["formato_compra"])),
                        (_texto("5. Cantidad recomendada", "5. Recommended quantity"), f"{_formatear_numero(caso['formatos_recomendados'])} {_texto('formatos', 'formats')}"),
                        (_texto("6. Cantidad solicitada", "6. Requested quantity"), f"{_formatear_numero(caso['cantidad_formatos_solicitados'])} {_texto('formatos', 'formats')}"),
                    ],
                    columns=[_texto("Paso", "Step"), _texto("Valor usado", "Value used")],
                )
                st.table(tabla_calculo)


with pestanas[2]:
    _titulo_seccion(
        _texto("03 · Aprobar", "03 · Approve"),
        _texto("Centro de aprobación", "Approval center"),
        _texto(
            "Convierte cada alerta en una decisión explícita, conserva el motivo y prepara una orden final con evidencia humana.",
            "Turn every alert into an explicit decision, preserve the reason and prepare a final order with human evidence.",
        ),
    )
    st.caption(
        _texto(
            "La confianza es una categoría operativa basada en seis semanas, atípicos y WAPE retrospectivo; no representa una probabilidad de acierto.",
            "Confidence is an operational category based on six weeks, outliers and backtest WAPE; it is not a probability of success.",
        )
    )

    metricas_aprobacion = st.columns(3)
    with metricas_aprobacion[0]:
        _tarjeta_metrica(
            _texto("Decisiones revisadas", "Reviewed decisions"),
            f"{estado_aprobacion['revisadas']} / {estado_aprobacion['total']}",
            _texto("casos documentados", "documented cases"),
            "brand",
        )
    with metricas_aprobacion[1]:
        _tarjeta_metrica(
            _texto("Pendientes", "Pending"),
            estado_aprobacion["pendientes"],
            _texto("requieren decisión", "need a decision"),
            "high" if estado_aprobacion["pendientes"] else "good",
        )
    with metricas_aprobacion[2]:
        estado_cierre = (
            _texto("Lista", "Ready")
            if estado_aprobacion["lista_para_aprobar"]
            else _texto("En revisión", "In review")
        )
        _tarjeta_metrica(
            _texto("Orden final", "Final order"),
            estado_cierre,
            _texto("control humano", "human control"),
            "good" if estado_aprobacion["lista_para_aprobar"] else "medium",
            compacto=True,
        )

    st.progress(
        float(estado_aprobacion["progreso"]),
        text=_texto(
            f"Revisión semanal: {estado_aprobacion['revisadas']} de {estado_aprobacion['total']} decisiones completadas",
            f"Weekly review: {estado_aprobacion['revisadas']} of {estado_aprobacion['total']} decisions completed",
        ),
    )

    herramientas_aprobacion = st.columns([1.1, 1])
    responsable_revision = herramientas_aprobacion[0].text_input(
        _texto("Responsable de la revisión", "Review owner"),
        placeholder=_texto("Nombre o iniciales", "Name or initials"),
        help=_texto(
            "Identificación declarada para la bitácora; no sustituye una firma autenticada.",
            "Declared identity for the log; it does not replace an authenticated signature.",
        ),
        key="responsable_revision",
    )
    casos_alta_pendientes = casos_aprobacion.loc[
        (casos_aprobacion["confianza_operativa"] == CONFIANZA_ALTA)
        & (~casos_aprobacion["caso_id"].isin(decisiones_aprobacion))
    ]
    with herramientas_aprobacion[1]:
        st.write("")
        if st.button(
            _texto(
                f"Aplicar recomendaciones de alta confianza ({len(casos_alta_pendientes)})",
                f"Apply high-confidence recommendations ({len(casos_alta_pendientes)})",
            ),
            type="primary",
            width="stretch",
            disabled=casos_alta_pendientes.empty,
            key="aplicar_alta_confianza",
            help=_texto(
                "No incluye productos desconocidos ni sobrescribe decisiones existentes.",
                "It excludes unknown products and never overwrites existing decisions.",
            ),
        ):
            st.session_state.revision_aprobacion["decisiones"] = (
                aplicar_recomendaciones_alta_confianza(
                    casos_aprobacion,
                    decisiones_aprobacion,
                    responsable=responsable_revision,
                )
            )
            st.rerun()

    if estado_aprobacion["devueltas"]:
        st.warning(
            _texto(
                "Hay casos devueltos a una sucursal. La orden final seguirá bloqueada hasta reabrirlos y registrar una decisión con cantidad.",
                "Some cases were returned to a location. The final order remains blocked until they are reopened and a quantity decision is recorded.",
            )
        )
    elif estado_aprobacion["lista_con_excepciones"]:
        st.success(
            _texto(
                f"Revisión completada con {estado_aprobacion['excepciones_catalogo']} excepción de catálogo documentada. La excepción queda fuera de la orden a proveedores.",
                f"Review completed with {estado_aprobacion['excepciones_catalogo']} documented catalog exception. The exception stays out of supplier orders.",
            )
        )
    elif estado_aprobacion["lista_para_aprobar"]:
        st.success(
            _texto(
                "Revisión completada. La orden aprobada y la bitácora están listas para descargar.",
                "Review complete. The approved order and decision log are ready to download.",
            )
        )
    else:
        st.info(
            _texto(
                "Revisa los pendientes o aplica en bloque únicamente las recomendaciones de alta confianza.",
                "Review pending cases or batch-apply only high-confidence recommendations.",
            )
        )

    _separador(_texto("Expedientes de decisión", "Decision case files"))
    etiquetas_decision = (
        DECISION_ETIQUETAS_EN if _en_ingles() else DECISION_ETIQUETAS_ES
    )
    motivos = {
        "RECOMENDACION_SISTEMA": _texto("Recomendación verificada", "Verified recommendation"),
        "INVENTARIO_EN_TRANSITO": _texto("Inventario en tránsito", "Inventory in transit"),
        "PROMOCION_CANCELADA": _texto("Promoción o evento cancelado", "Promotion or event cancelled"),
        "DECISION_GERENCIAL": _texto("Decisión gerencial", "Management decision"),
        "CORRECCION_CATALOGO": _texto("Corrección de catálogo", "Catalog correction"),
        "OTRO": _texto("Otro", "Other"),
    }
    for indice_caso, (_, caso_aprobacion) in enumerate(
        casos_aprobacion.iterrows()
    ):
        caso_id = str(caso_aprobacion["caso_id"])
        nombre_caso = _nombre_visible(
            caso_aprobacion["ingrediente_id"],
            caso_aprobacion["nombre"],
        )
        decision_actual = decisiones_aprobacion.get(caso_id)
        estado_decision = (
            etiquetas_decision.get(str(decision_actual["decision"]), str(decision_actual["decision"]))
            if decision_actual
            else _texto("Pendiente", "Pending")
        )
        with st.expander(
            f"{_etiqueta_prioridad(caso_aprobacion['prioridad'])} · "
            f"{caso_aprobacion['sucursal']} · {nombre_caso} · {estado_decision}",
            expanded=decision_actual is None and indice_caso == 0,
        ):
            formato_caso = caso_aprobacion.get("formato_compra")
            nota_recomendacion = (
                _texto("Sin recomendación", "No recommendation")
                if formato_caso is None or pd.isna(formato_caso)
                else str(formato_caso)
            )
            resumen_caso = st.columns(4)
            with resumen_caso[0]:
                _tarjeta_metrica(
                    _texto("Solicitado", "Requested"),
                    _formatear_numero(caso_aprobacion["cantidad_formatos_solicitados"]),
                    _texto("formatos", "formats"),
                )
            with resumen_caso[1]:
                _tarjeta_metrica(
                    _texto("Recomendado", "Recommended"),
                    _formatear_numero(caso_aprobacion["formatos_recomendados"]),
                    nota_recomendacion,
                    "brand",
                )
            with resumen_caso[2]:
                _tarjeta_metrica(
                    _texto("Confianza", "Confidence"),
                    _etiqueta_confianza(caso_aprobacion["confianza_operativa"]),
                    _texto("categoría operativa", "operational category"),
                    _tono_confianza(caso_aprobacion["confianza_operativa"]),
                    compacto=True,
                )
            with resumen_caso[3]:
                _tarjeta_metrica(
                    _texto("Decisión", "Decision"),
                    estado_decision,
                    _texto("registro de sesión", "session record"),
                    "good" if decision_actual else "medium",
                    compacto=True,
                )
            st.caption(str(caso_aprobacion["confianza_motivo"]))

            if decision_actual:
                detalle_decision = decision_actual.get("motivo_detalle") or decision_actual.get("motivo_codigo")
                st.markdown(
                    f"**{_texto('Decisión registrada', 'Recorded decision')}:** "
                    f"{_seguro(estado_decision)}  \n"
                    f"**{_texto('Motivo', 'Reason')}:** {_seguro(detalle_decision or '—')}"
                )
                if st.button(
                    _texto("Reabrir decisión", "Reopen decision"),
                    key=f"reabrir_{caso_id}",
                ):
                    del st.session_state.revision_aprobacion["decisiones"][caso_id]
                    st.rerun()
            else:
                permitidas = list(opciones_decision(caso_aprobacion))
                with st.form(f"form_decision_{caso_id}"):
                    decision_elegida = st.selectbox(
                        _texto("Decisión", "Decision"),
                        permitidas,
                        format_func=lambda codigo: etiquetas_decision[codigo],
                    )
                    motivo_elegido = st.selectbox(
                        _texto("Motivo", "Reason"),
                        list(motivos),
                        index=(
                            list(motivos).index("CORRECCION_CATALOGO")
                            if caso_aprobacion["estado"] == "NO_EVALUABLE"
                            else 0
                        ),
                        format_func=lambda codigo: motivos[codigo],
                    )
                    motivo_detalle = st.text_area(
                        _texto("Nota opcional", "Optional note"),
                        placeholder=_texto(
                            "Contexto breve para la bitácora",
                            "Brief context for the decision log",
                        ),
                    )
                    guardar_decision = st.form_submit_button(
                        _texto("Guardar decisión", "Save decision"),
                        type="primary",
                        width="stretch",
                    )
                if guardar_decision:
                    try:
                        registro_decision = registrar_decision(
                            caso_aprobacion,
                            decision_elegida,
                            motivo_codigo=motivo_elegido,
                            motivo_detalle=motivo_detalle,
                            responsable=responsable_revision,
                        )
                    except ErrorAprobacion as error:
                        st.error(str(error))
                    else:
                        st.session_state.revision_aprobacion["decisiones"][caso_id] = registro_decision
                        st.rerun()

    if orden_aprobada is not None:
        _separador(_texto("Cierre y evidencia", "Closure and evidence"))
        bitacora = generar_bitacora_decisiones(
            casos_aprobacion,
            decisiones_aprobacion,
            huella_revision=huella_revision,
            fuente=fuente_texto,
            idioma=_idioma_codigo(),
        )
        descargas_aprobacion = st.columns(2)
        descargas_aprobacion[0].download_button(
            _texto("Descargar orden aprobada · CSV", "Download approved order · CSV"),
            data=dataframe_a_csv_bytes(
                aplicar_nombres_visibles(
                    orden_aprobada,
                    idioma=_idioma_codigo(),
                )
            ),
            file_name="orden_aprobada_barrio_pizza.csv",
            mime="text/csv",
            type="primary",
            width="stretch",
            key="aprobacion_descargar_orden",
        )
        descargas_aprobacion[1].download_button(
            _texto("Descargar bitácora · CSV", "Download decision log · CSV"),
            data=dataframe_a_csv_bytes(bitacora),
            file_name="bitacora_revision_compras.csv",
            mime="text/csv",
            width="stretch",
            key="aprobacion_descargar_bitacora",
        )

        with st.expander(
            _texto(
                "Mensajes preparados para las sucursales",
                "Messages prepared for locations",
            )
        ):
            sucursales_con_decision = sorted(casos_aprobacion["sucursal"].unique())
            for sucursal_mensaje in sucursales_con_decision:
                mensaje_sucursal = generar_mensaje_sucursal(
                    casos_aprobacion,
                    decisiones_aprobacion,
                    sucursal_mensaje,
                    semana=_contexto_semana(analisis.datos["consumo_historico"]),
                    idioma=_idioma_codigo(),
                )
                st.markdown(f"#### {sucursal_mensaje}")
                st.code(mensaje_sucursal, language=None)
                st.download_button(
                    _texto("Descargar mensaje · TXT", "Download message · TXT"),
                    data=mensaje_sucursal.encode("utf-8"),
                    file_name=f"ajustes_{sucursal_mensaje.lower().replace(' ', '_')}.txt",
                    mime="text/plain",
                    key=f"mensaje_sucursal_{sucursal_mensaje}",
                )


with pestanas[3]:
    _titulo_seccion(
        _texto("04 · Resolver", "04 · Resolve"),
        _texto("Orden corregida por proveedor", "Corrected order by supplier"),
        _texto(
            "Revisa el ajuste final, filtra por proveedor y descarga archivos listos para enviar. La recomendación excluye productos desconocidos y conserva formatos completos.",
            "Review the final adjustment, filter by supplier and download files ready to send. The recommendation excludes unknown products and preserves full purchase formats.",
        ),
    )

    es_orden_aprobada = orden_aprobada is not None
    orden_operativa = (
        orden_aprobada.copy()
        if es_orden_aprobada
        else analisis.orden_corregida.copy()
    )
    if es_orden_aprobada:
        st.success(
            _texto(
                "Esta vista refleja las decisiones registradas en el Centro de aprobación.",
                "This view reflects the decisions recorded in the Approval center.",
            )
        )
    else:
        st.info(
            _texto(
                "Borrador recomendado: completa las decisiones del Centro de aprobación para generar la orden final aprobada.",
                "Recommended draft: complete the Approval center decisions to generate the final approved order.",
            )
        )

    proveedores = sorted(orden_operativa["proveedor"].dropna().unique())
    with st.container(border=True):
        filtro_proveedores = st.multiselect(
            _texto("Filtrar proveedores", "Filter suppliers"),
            proveedores,
            placeholder=_texto("Todos los proveedores", "All suppliers"),
            help=_texto("La descarga filtrada respeta esta selección.", "The filtered download follows this selection."),
        )
    orden_filtrada = preparar_orden_por_proveedor(
        orden_operativa,
        proveedores=filtro_proveedores,
    )

    indicadores_orden = st.columns(3)
    with indicadores_orden[0]:
        _tarjeta_metrica(_texto("Proveedores", "Suppliers"), orden_filtrada["proveedor"].nunique(), _texto("incluidos en la vista", "included in the view"))
    with indicadores_orden[1]:
        _tarjeta_metrica(_texto("Líneas de compra", "Purchase lines"), len(orden_filtrada), _texto("ingredientes por sucursal", "ingredients by location"), "brand")
    with indicadores_orden[2]:
        _tarjeta_metrica(_texto("Sucursales", "Locations"), orden_filtrada["sucursal"].nunique(), _texto("cubiertas por la orden", "covered by the order"))

    _separador(_texto("Vista consolidada", "Consolidated view"))
    columna_original = _texto("Cantidad original", "Original quantity")
    columna_recomendada = _texto(
        "Cantidad aprobada" if es_orden_aprobada else "Cantidad recomendada",
        "Approved quantity" if es_orden_aprobada else "Recommended quantity",
    )
    columna_ajuste = _texto(
        "Ajuste aprobado" if es_orden_aprobada else "Ajuste",
        "Approved adjustment" if es_orden_aprobada else "Adjustment",
    )
    columna_total = _texto(
        "Total aprobado" if es_orden_aprobada else "Total recomendado",
        "Approved total" if es_orden_aprobada else "Recommended total",
    )
    tabla_orden_interfaz = (
        _orden_aprobada_para_interfaz(orden_filtrada)
        if es_orden_aprobada
        else _orden_para_interfaz(orden_filtrada)
    )
    st.dataframe(
        tabla_orden_interfaz,
        hide_index=True,
        width="stretch",
        height=480,
        column_config={
            columna_original: st.column_config.NumberColumn(format="%d"),
            columna_recomendada: st.column_config.NumberColumn(format="%d"),
            columna_ajuste: st.column_config.NumberColumn(
                help=_texto("Positivo: agregar. Negativo: reducir.", "Positive: add. Negative: reduce."),
                format="%+d",
            ),
            columna_total: st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(_texto("Ajuste positivo = agregar formatos · Ajuste negativo = reducir formatos.", "Positive adjustment = add formats · Negative adjustment = reduce formats."))

    descargas = st.columns(2)
    descarga_completa = descargas[0].download_button(
        _texto(
            "Descargar orden aprobada · CSV" if es_orden_aprobada else "Descargar borrador completo · CSV",
            "Download approved order · CSV" if es_orden_aprobada else "Download full draft · CSV",
        ),
        data=dataframe_a_csv_bytes(
            aplicar_nombres_visibles(
                orden_operativa,
                idioma=_idioma_codigo(),
            )
        ),
        file_name=(
            "orden_aprobada_barrio_pizza.csv"
            if es_orden_aprobada
            else "orden_recomendada_barrio_pizza.csv"
        ),
        mime="text/csv",
        width="stretch",
        type="primary",
        key="orden_descarga_completa",
    )
    descarga_filtrada = descargas[1].download_button(
        _texto("Descargar vista filtrada · CSV", "Download filtered view · CSV"),
        data=dataframe_a_csv_bytes(
            aplicar_nombres_visibles(
                orden_filtrada,
                idioma=_idioma_codigo(),
            )
        ),
        file_name=(
            "orden_aprobada_filtrada.csv"
            if es_orden_aprobada
            else "orden_recomendada_filtrada.csv"
        ),
        mime="text/csv",
        width="stretch",
        key="orden_descarga_filtrada",
    )
    if descarga_completa or descarga_filtrada:
        st.toast(_texto("Descarga preparada correctamente.", "Download prepared successfully."))

    _separador(
        _texto(
            "Órdenes y mensajes por proveedor",
            "Orders and messages by supplier",
        )
    )
    for proveedor, grupo in orden_filtrada.groupby("proveedor", sort=True):
        with st.expander(f"{proveedor} · {len(grupo)} {_texto('líneas de compra', 'purchase lines')}"):
            tabla_grupo = (
                _orden_aprobada_para_interfaz(grupo)
                if es_orden_aprobada
                else _orden_para_interfaz(grupo)
            )
            st.dataframe(
                tabla_grupo.drop(columns=_texto("Proveedor", "Supplier")),
                hide_index=True,
                width="stretch",
            )
            mensaje_proveedor = generar_mensaje_proveedor(
                grupo,
                proveedor,
                semana=_contexto_semana(analisis.datos["consumo_historico"]),
                idioma=_idioma_codigo(),
                aprobado=es_orden_aprobada,
            )
            st.caption(
                _texto(
                    "Texto listo para copiar; el sistema no lo envía automáticamente.",
                    "Copy-ready text; the system does not send it automatically.",
                )
            )
            st.code(mensaje_proveedor, language=None)
            descargas_proveedor = st.columns(2)
            descarga_proveedor = descargas_proveedor[0].download_button(
                f"{_texto('Descargar CSV', 'Download CSV')} · {proveedor}",
                data=dataframe_a_csv_bytes(
                    aplicar_nombres_visibles(grupo, idioma=_idioma_codigo())
                ),
                file_name=f"orden_{str(proveedor).lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"descarga_{proveedor}",
                width="stretch",
            )
            descarga_texto = descargas_proveedor[1].download_button(
                f"{_texto('Descargar mensaje', 'Download message')} · TXT",
                data=mensaje_proveedor.encode("utf-8"),
                file_name=f"mensaje_{str(proveedor).lower().replace(' ', '_')}.txt",
                mime="text/plain",
                key=f"mensaje_proveedor_{proveedor}",
                width="stretch",
            )
            if descarga_proveedor or descarga_texto:
                st.toast(_texto(f"Orden de {proveedor} preparada.", f"{proveedor} order prepared."))


with pestanas[4]:
    _titulo_seccion(
        _texto("05 · Verificar", "05 · Verify"),
        _texto("Calidad y trazabilidad", "Quality and traceability"),
        _texto(
            "Distingue problemas de archivo, desempeño del modelo y evidencia de cada proyección.",
            "Separate file issues, model performance and the evidence behind every forecast.",
        ),
    )

    hallazgos = analisis.hallazgos.copy()
    _separador(_texto("Calidad de datos", "Data quality"))
    st.caption(_texto("Los errores bloqueantes detienen el cálculo; las advertencias permiten continuar, pero requieren revisión.", "Blocking errors stop the calculation; warnings allow it to continue but still require review."))
    columnas_calidad = st.columns(3)
    cantidad_errores = int((hallazgos["nivel"] == "ERROR").sum()) if not hallazgos.empty else 0
    cantidad_bloqueantes = int(hallazgos["bloqueante"].fillna(False).sum()) if not hallazgos.empty else 0
    with columnas_calidad[0]:
        _tarjeta_metrica(_texto("Hallazgos", "Findings"), len(hallazgos), _texto("advertencias y errores", "warnings and errors"))
    with columnas_calidad[1]:
        _tarjeta_metrica(_texto("Errores", "Errors"), cantidad_errores, _texto("requieren corrección", "require correction"), "high" if cantidad_errores else "good")
    with columnas_calidad[2]:
        _tarjeta_metrica(_texto("Bloqueantes", "Blocking"), cantidad_bloqueantes, _texto("detienen el análisis", "stop the analysis"), "critical" if cantidad_bloqueantes else "good")

    if hallazgos.empty:
        st.success(_texto("No se encontraron problemas de calidad de datos.", "No data-quality issues were found."))
    else:
        tabla_calidad = hallazgos.copy()
        tabla_calidad["bloqueante"] = tabla_calidad["bloqueante"].fillna(False).map(
            {True: _texto("Sí", "Yes"), False: _texto("No", "No")}
        )
        nombres_calidad = {
            "codigo": _texto("Código", "Code"),
            "nivel": _texto("Severidad", "Severity"),
            "archivo": _texto("Fuente", "Source"),
            "mensaje": _texto("Hallazgo", "Finding"),
            "sucursal": _texto("Sucursal", "Location"),
            "ingrediente_id": _texto("Ingrediente", "Ingredient"),
            "campo": _texto("Campo", "Field"),
            "valor": _texto("Valor recibido", "Received value"),
            "bloqueante": _texto("¿Bloquea el análisis?", "Blocks analysis?"),
        }
        tabla_calidad = tabla_calidad.rename(columns=nombres_calidad)
        tabla_calidad = tabla_calidad[
            [
                _texto("Severidad", "Severity"),
                _texto("Hallazgo", "Finding"),
                _texto("Fuente", "Source"),
                _texto("Sucursal", "Location"),
                _texto("Ingrediente", "Ingredient"),
                _texto("¿Bloquea el análisis?", "Blocks analysis?"),
            ]
        ]
        st.dataframe(
            tabla_calidad,
            hide_index=True,
            width="stretch",
        )
        st.download_button(
            _texto("Descargar reporte de calidad · CSV", "Download quality report · CSV"),
            data=dataframe_a_csv_bytes(hallazgos),
            file_name="reporte_calidad_datos.csv",
            mime="text/csv",
        )

    with st.expander(
        _texto(
            "Reparador guiado · preparar un archivo limpio",
            "Guided repair · prepare a clean file",
        )
    ):
        st.caption(
            _texto(
                "Completa combinaciones omitidas con cero y separa identificadores desconocidos. Nunca corrige nombres ni elimina filas silenciosamente.",
                "Adds missing combinations with zero and separates unknown identifiers. It never silently renames or deletes rows.",
            )
        )
        plantilla_reparada, filas_revision, reporte_reparacion = preparar_reparacion_orden(
            analisis.datos["orden_compra_semana"],
            analisis.datos["consumo_historico"],
            analisis.datos["ingredientes"],
        )
        metricas_reparacion = st.columns(3)
        with metricas_reparacion[0]:
            _tarjeta_metrica(
                _texto("Filas válidas", "Valid rows"),
                len(plantilla_reparada),
                _texto("plantilla completa", "complete template"),
                "good",
            )
        with metricas_reparacion[1]:
            _tarjeta_metrica(
                _texto("Combinaciones añadidas", "Added combinations"),
                int(
                    (
                        reporte_reparacion["accion"]
                        == "COMBINACION_AGREGADA_CON_CERO"
                    ).sum()
                ),
                _texto("inician en cero", "start at zero"),
                "brand",
            )
        with metricas_reparacion[2]:
            _tarjeta_metrica(
                _texto("Filas separadas", "Separated rows"),
                len(filas_revision),
                _texto("requieren revisión", "require review"),
                "high" if len(filas_revision) else "good",
            )
        if not reporte_reparacion.empty:
            reporte_ui = reporte_reparacion.rename(
                columns={
                    "accion": _texto("Acción", "Action"),
                    "sucursal": _texto("Sucursal", "Location"),
                    "ingrediente_id": _texto("Identificador", "Identifier"),
                    "detalle": _texto("Qué hizo el reparador", "What the repair tool did"),
                }
            )
            st.dataframe(reporte_ui, hide_index=True, width="stretch")
        descargas_reparacion = st.columns(3)
        descargas_reparacion[0].download_button(
            _texto("Descargar plantilla limpia", "Download clean template"),
            data=dataframe_a_csv_bytes(plantilla_reparada),
            file_name="orden_plantilla_validada.csv",
            mime="text/csv",
            width="stretch",
            key="reparador_descargar_plantilla",
        )
        descargas_reparacion[1].download_button(
            _texto("Descargar filas a revisar", "Download rows to review"),
            data=dataframe_a_csv_bytes(filas_revision),
            file_name="orden_filas_por_revisar.csv",
            mime="text/csv",
            width="stretch",
            disabled=filas_revision.empty,
            key="reparador_descargar_excepciones",
        )
        descargas_reparacion[2].download_button(
            _texto("Descargar registro de cambios", "Download change log"),
            data=dataframe_a_csv_bytes(reporte_reparacion),
            file_name="orden_registro_reparacion.csv",
            mime="text/csv",
            width="stretch",
            key="reparador_descargar_registro",
        )

    _separador(_texto("Rendimiento del modelo", "Model performance"))
    wape_mediano = analisis.proyecciones["wape_backtest_pct"].replace([float("inf"), float("-inf")], pd.NA).dropna().median()
    modelo_metricas = st.columns(4)
    with modelo_metricas[0]:
        _tarjeta_metrica(_texto("Proyecciones", "Forecasts"), len(analisis.proyecciones), _texto("sucursal + ingrediente", "location + ingredient"))
    with modelo_metricas[1]:
        _tarjeta_metrica(_texto("Métodos usados", "Methods used"), analisis.proyecciones["metodo_proyeccion"].nunique(), _texto("selección adaptativa", "adaptive selection"))
    with modelo_metricas[2]:
        _tarjeta_metrica(_texto("WAPE mediano", "Median WAPE"), _formatear_porcentaje(wape_mediano), _texto("error retrospectivo", "backtest error"), "good")
    with modelo_metricas[3]:
        _tarjeta_metrica(_texto("Series atípicas", "Outlier series"), int((analisis.proyecciones["cantidad_atipicos"] > 0).sum()), _texto("requieren contexto", "require context"))

    metodos = (
        analisis.proyecciones.groupby("metodo_proyeccion")
        .size()
        .rename("cantidad")
        .reset_index()
    )
    metodo_columna = _texto("Método", "Method")
    metodos[metodo_columna] = metodos["metodo_proyeccion"].map(
        METODO_ETIQUETAS_EN if _en_ingles() else METODO_ETIQUETAS
    )
    figura_metodos = px.bar(
        metodos,
        x=metodo_columna,
        y="cantidad",
        labels={"cantidad": _texto("Combinaciones", "Combinations")},
        text_auto=True,
        color_discrete_sequence=["#C9251A"],
        title=_texto("Método elegido por serie", "Method selected by series"),
    )
    figura_metodos.update_layout(showlegend=False)
    st.plotly_chart(
        _estilo_grafico(figura_metodos, altura=350),
        width="stretch",
        config={"displayModeBar": False},
    )

    _separador(_texto("Trazabilidad de cada proyección", "Forecast traceability"))
    columnas_modelo_tabla = [
        "sucursal",
        "consumo_proyectado_unidad_base",
        "metodo_proyeccion",
        "cantidad_atipicos",
        "semanas_atipicas",
        "mae_backtest",
        "wape_backtest_pct",
        "explicacion_proyeccion",
    ]
    catalogo_modelos = aplicar_nombres_visibles(
        analisis.datos["ingredientes"],
        idioma=_idioma_codigo(),
    )[["ingrediente_id", "nombre"]]
    tabla_modelos = analisis.proyecciones.merge(
        catalogo_modelos,
        on="ingrediente_id",
        how="left",
    )[["nombre"] + columnas_modelo_tabla].copy()
    tabla_modelos["metodo_proyeccion"] = tabla_modelos[
        "metodo_proyeccion"
    ].map(METODO_ETIQUETAS_EN if _en_ingles() else METODO_ETIQUETAS)
    tabla_modelos = tabla_modelos.rename(
        columns={
            "sucursal": _texto("Sucursal", "Location"),
            "nombre": _texto("Ingrediente", "Ingredient"),
            "consumo_proyectado_unidad_base": _texto("Consumo proyectado", "Forecast consumption"),
            "metodo_proyeccion": _texto("Método", "Method"),
            "cantidad_atipicos": _texto("Datos atípicos", "Outliers"),
            "semanas_atipicas": _texto("Semanas atípicas", "Outlier weeks"),
            "mae_backtest": _texto("MAE retrospectivo", "Backtest MAE"),
            "wape_backtest_pct": _texto("WAPE retrospectivo (%)", "Backtest WAPE (%)"),
            "explicacion_proyeccion": _texto("Explicación", "Explanation (source language)"),
        }
    )
    st.dataframe(
        tabla_modelos,
        hide_index=True,
        width="stretch",
        height=420,
    )

    with st.expander(_texto("Supuestos operativos del cálculo", "Calculation assumptions")):
        st.markdown(
            _texto(
                """
- S1 es la semana más antigua y S6 la más reciente.
- El inventario actual está disponible antes de la semana proyectada.
- La orden cubre una semana y no utiliza stock de seguridad adicional.
- Solo se compran formatos completos.
- Una fila omitida equivale a cero formatos solicitados.
- No se inventan precios, clientes, vencimientos ni tiempos de entrega que no están en los datos.
                """,
                """
- S1 is the oldest week and S6 is the most recent.
- Current inventory is available before the forecast week.
- The order covers one week and uses no additional safety stock.
- Only complete purchase formats are ordered.
- A missing row is treated as zero requested formats.
- Prices, customers, expiry dates and lead times not present in the data are never invented.
                """,
            )
        )


contexto_operativo_ai = {
    **contexto_aprobacion,
    "escenario_activo": contexto_escenario,
    "reparacion_archivo": {
        "filas_validas": len(plantilla_reparada),
        "combinaciones_agregadas_con_cero": int(
            (
                reporte_reparacion["accion"]
                == "COMBINACION_AGREGADA_CON_CERO"
            ).sum()
        ),
        "filas_separadas_para_revision": len(filas_revision),
    },
    "comunicaciones": {
        "estado": "APROBADA" if orden_aprobada is not None else "BORRADOR",
        "proveedores_con_mensaje": int(orden_operativa["proveedor"].nunique()),
        "sucursales_con_ajustes": int(casos_aprobacion["sucursal"].nunique()),
        "mensajes_enviados_automaticamente": False,
    },
    "capacidades_dashboard": [
        "resumen ejecutivo y alertas auditables",
        "simulador temporal de demanda",
        "centro de aprobación y bitácora de decisiones",
        "confianza operativa con supervisión humana",
        "orden aprobada y mensajes por proveedor y sucursal",
        "reparador guiado de archivos",
        "carga, edición, recálculo y descargas",
    ],
}


def _renderizar_barrio_ai_flotante() -> None:
    if "mensajes_asistente" not in st.session_state:
        st.session_state.mensajes_asistente = []

    conectado = generador_ia is not None
    modo_asistente = (
        _texto("IA conectada", "AI connected")
        if conectado
        else _texto("Modo local verificado", "Verified local mode")
    )
    descripcion_asistente = _texto(
        "Pregunta desde cualquier vista. Barrio AI conoce la orden activa, los escenarios y las decisiones de esta revisión.",
        "Ask from any view. Barrio AI knows the active order, scenarios and decisions in this review.",
    )

    with st.container(key="barrio_ai_floating"):
        with st.popover(
            "BARRIO AI",
            help=_texto("Abrir asistente de compras", "Open purchasing assistant"),
            use_container_width=False,
        ):
            st.markdown(
                f"""
                <div class="bp-ai-panel-head">
                  <div class="bp-ai-panel-mark" aria-hidden="true">AI</div>
                  <div>
                    <div class="bp-ai-panel-kicker">BARRIO AI</div>
                    <h3>{_texto('Tu copiloto de compras', 'Your purchasing copilot')}</h3>
                    <p>{_seguro(descripcion_asistente)}</p>
                  </div>
                </div>
                <div class="bp-ai-panel-status">
                  <span class="bp-dot bp-dot--{'ok' if conectado else 'warn'}"></span>
                  <span>{_seguro(modo_asistente)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if error_configuracion_ia:
                with st.expander(_texto("Por qué se activó el modo local", "Why local mode is active")):
                    st.write(
                        _texto(
                            "El servicio de IA no está disponible en este momento. Barrio AI mantiene las respuestas verificadas con el motor local.",
                            "The AI service is unavailable right now. Barrio AI keeps answers verified through the local engine.",
                        )
                    )
            elif not conectado:
                st.caption(
                    _texto(
                        "Respaldo local activo: las respuestas siguen usando únicamente resultados verificados.",
                        "Local fallback active: answers still use verified results only.",
                    )
                )

            sugerencias = (
                [
                    "What should I review first?",
                    "How many decisions are left?",
                    "What requires human review?",
                    "Is the order ready to approve?",
                ]
                if _en_ingles()
                else [
                    "¿Qué debo revisar primero?",
                    "¿Cuántas decisiones faltan?",
                    "¿Qué requiere revisión humana?",
                    "¿La orden está lista para aprobar?",
                ]
            )
            st.caption(_texto("Prueba una pregunta", "Try a question"))
            columnas_sugerencias = st.columns(2)
            pregunta_sugerida = None
            for indice, sugerencia in enumerate(sugerencias):
                if columnas_sugerencias[indice % 2].button(
                    sugerencia,
                    width="stretch",
                    key=f"sugerencia_flotante_{indice}_{st.session_state.idioma_ui}",
                ):
                    pregunta_sugerida = sugerencia

            with st.container(height=235, key="barrio_ai_history"):
                if not st.session_state.mensajes_asistente:
                    st.markdown(
                        _texto(
                            "**Hola, soy Barrio AI.** Puedo explicar prioridades, confianza, decisiones, escenarios, cantidades y proveedores.",
                            "**Hi, I'm Barrio AI.** I can explain priorities, confidence, decisions, scenarios, quantities and suppliers.",
                        )
                    )
                    st.caption(
                        _texto(
                            "Los números siempre provienen del análisis de la orden activa.",
                            "Numbers always come from the active order analysis.",
                        )
                    )
                for mensaje in st.session_state.mensajes_asistente:
                    with st.chat_message(mensaje["role"]):
                        st.markdown(mensaje["content"])
                        if mensaje["role"] == "assistant" and mensaje.get("modo"):
                            st.caption(
                                _texto("IA + cálculo verificado", "AI + verified calculation")
                                if mensaje.get("modo") == "gemini"
                                else _texto("Cálculo local verificado", "Verified local calculation")
                            )
                        if mensaje.get("advertencia"):
                            st.warning(
                                _texto(
                                    "La IA no respondió; se usó el respaldo local verificado.",
                                    "AI did not respond; the verified local fallback was used.",
                                )
                            )
                        evidencia = mensaje.get("evidencia") or []
                        if mensaje["role"] == "assistant" and evidencia:
                            with st.expander(_texto("Datos usados para responder", "Data used to answer")):
                                for elemento in evidencia:
                                    st.write(f"- {elemento}")

            pregunta_escrita = st.chat_input(
                _texto(
                    "Pregunta sobre esta orden...",
                    "Ask about this order...",
                ),
                key="barrio_ai_chat_input",
            )
            pregunta = pregunta_sugerida or pregunta_escrita

            if pregunta:
                st.session_state.mensajes_asistente.append({"role": "user", "content": pregunta})
                historial = [
                    {"role": mensaje["role"], "content": mensaje["content"]}
                    for mensaje in st.session_state.mensajes_asistente[-8:]
                ]
                with st.spinner(_texto("Barrio AI está revisando los resultados...", "Barrio AI is reviewing the results...")):
                    respuesta = responder_asistente(
                        pregunta,
                        analisis,
                        generador_llm=generador_ia,
                        historial=historial,
                        idioma=st.session_state.idioma_ui.lower(),
                        contexto_operativo=contexto_operativo_ai,
                    )
                st.session_state.mensajes_asistente.append(
                    {
                        "role": "assistant",
                        "content": respuesta.respuesta,
                        "modo": respuesta.modo,
                        "evidencia": list(respuesta.evidencia),
                        "advertencia": respuesta.advertencia,
                    }
                )
                st.rerun()

            acciones_chat = st.columns([1, 1.6])
            if acciones_chat[0].button(
                _texto("Limpiar", "Clear"),
                key="limpiar_asistente_flotante",
                width="stretch",
            ):
                st.session_state.mensajes_asistente = []
                st.rerun()
            acciones_chat[1].caption(
                _texto("Siempre disponible en el tablero", "Always available in the dashboard")
            )


_renderizar_barrio_ai_flotante()
