# Guion de video — 3 a 5 minutos

Duración objetivo: **4 minutos 30 segundos**.

## Antes de grabar

- Abrir la app publicada en español.
- Usar la orden original del reto.
- Mantener cerrado el panel lateral al iniciar.
- Tener preparada una segunda pestaña para mostrar el editor.
- Confirmar que el enlace de grabación pueda abrirse sin iniciar sesión.
- No mostrar claves, configuración de secretos ni ventanas del editor de código.

## 0:00–0:25 — Problema y objetivo

### En pantalla

Encabezado y resumen ejecutivo.

### Narración sugerida

> Cada semana las sucursales de Barrio Pizza preparan órdenes de compra y la gerente debe revisar si están pidiendo de más, de menos o si olvidaron algo. Construí este centro de inteligencia de compras para convertir esa revisión manual en un flujo automático, explicable y listo para tomar decisiones.

## 0:25–0:55 — Datos y cálculo

### En pantalla

Mostrar brevemente la fuente activa, la semana S7 y las tarjetas del resumen.

### Narración sugerida

> La herramienta utiliza seis semanas de consumo, inventario actual, catálogo de ingredientes y la orden semanal. Proyecta el consumo por sucursal e ingrediente, resta el inventario y redondea hacia arriba al formato completo de compra. Por eso nunca recomienda medio saco o media caja.

## 0:55–1:25 — Resultado ejecutivo

### En pantalla

Mostrar las seis alertas, críticas y primera acción recomendada.

### Narración sugerida

> Con los datos originales se detectan seis alertas: dos críticas, tres altas y una media. El 94.3 % de las combinaciones está correcto. La gerente puede ver inmediatamente qué problema requiere atención y en qué sucursal.

## 1:25–2:05 — Dos casos que explican el modelo

### En pantalla

Abrir el centro de alertas y el detalle de Harina 00 de Costa del Este. Después mencionar Pepperoni de Marbella en la trazabilidad.

### Narración sugerida

> En la harina de Costa del Este existe una tendencia creciente consistente. El modelo proyecta aproximadamente 330 kilos y recomienda 13 sacos, pero la sucursal pidió 6. En cambio, el pepperoni de Marbella tiene una semana atípica de 150 kilos. El motor reduce su influencia y evita una alerta falsa. No utilizo el mismo promedio para todos: comparo métodos mediante backtesting y favorezco el más sencillo que explica bien cada serie.

## 2:05–2:35 — Carga, edición y recálculo

### En pantalla

Abrir la barra lateral, activar el editor y cambiar Mozzarella de Brisas del Golf de 0 a 18.

### Narración sugerida

> La gerente también puede cargar otra orden o corregir cantidades desde la interfaz. Al cambiar la mozzarella omitida de cero a 18 cajas, la aplicación vuelve a ejecutar la auditoría y la alerta desaparece. Esto demuestra que no es un reporte estático.

Después de mostrar el cambio, volver a la orden original para continuar.

## 2:35–3:15 — Aprobación y supervisión humana

### En pantalla

Abrir Centro de aprobación. Mostrar confianza, decisiones y aplicación masiva de alta confianza.

### Narración sugerida

> Añadí un centro de aprobación para cerrar el trabajo real de la gerente. Cada alerta puede aceptar la recomendación, mantener la cantidad indicando un motivo, devolverse a la sucursal o separarse para corregir catálogo. La confianza no es una probabilidad: es una señal operativa basada en error retrospectivo, estabilidad y atípicos. Solo los casos de alta confianza pueden aplicarse en bloque.

## 3:15–3:45 — Orden por proveedor

### En pantalla

Abrir Orden corregida y expandir un proveedor.

### Narración sugerida

> La orden se agrupa por proveedor y conserva formatos completos. Además del CSV para Excel o una futura integración, se genera un mensaje en texto legible que la gerente puede copiar a correo o WhatsApp. El prototipo prepara la comunicación, pero no afirma que la envió.

## 3:45–4:05 — Calidad y reparación

### En pantalla

Abrir Calidad y modelo; mostrar el producto desconocido y el reparador guiado.

### Narración sugerida

> La auditoría detecta que falta mozzarella y que `aji_chombo` no existe en el catálogo. El sistema nunca inventa su unidad o proveedor. Puede generar una plantilla limpia, separar las filas que requieren revisión y descargar un registro de cambios.

## 4:05–4:25 — Barrio AI

### En pantalla

Abrir el botón flotante de Barrio AI y preguntar: “¿Qué debo revisar primero?”.

### Narración sugerida

> Barrio AI permite consultar la orden en lenguaje natural desde cualquier vista. La IA no calcula compras: recibe los resultados del motor y los explica. Si el servicio externo no está disponible, existe un respaldo local para que el dashboard siga funcionando.

## 4:25–4:40 — Cierre y evolución

### En pantalla

Volver al resumen o mostrar la orden final.

### Narración sugerida

> En producción conectaría catálogo, ventas, inventario y órdenes con Odoo, manteniendo aprobación humana, auditoría y monitoreo. Mi objetivo fue construir una base que no solo detectara problemas, sino que ayudara a resolverlos de forma responsable y trazable.

## Enlaces antes de enviar

Comprobar en una ventana sin sesión:

- repositorio de GitHub;
- aplicación publicada;
- video no listado o enlace de Loom;
- cualquier archivo compartido.

Si alguno pide iniciar sesión o solicitar permiso, todavía no está listo para el formulario.
