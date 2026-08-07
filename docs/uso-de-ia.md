# Cómo utilicé inteligencia artificial

## Respuesta breve para el formulario

Utilicé IA como copiloto de ingeniería y producto, no como sustituto del razonamiento ni como fuente de los cálculos. Me ayudó a interpretar el problema de negocio, comparar métodos de proyección, diseñar una arquitectura modular, detectar casos límite, proponer pruebas, depurar errores, revisar la experiencia de usuario y documentar la solución. Cada recomendación fue contrastada con las reglas del reto, los datos originales, pruebas automatizadas y revisión visual en navegador. Las cantidades finales provienen de un motor determinista y auditable; el asistente de la aplicación solo explica resultados ya calculados y utiliza un respaldo local si el servicio externo no está disponible.

## Uso durante el desarrollo

### Comprensión del problema

La IA ayudó a convertir las instrucciones del reto en reglas verificables:

- distinguir unidad base de formato de compra;
- no confundir redondeo normal con sobrepedido;
- interpretar una fila omitida como cero formatos solicitados;
- tratar identificadores desconocidos como no evaluables;
- mantener trazabilidad sobre cada recomendación.

### Diseño técnico

Se utilizó para discutir y revisar una separación modular entre carga, validación, proyección, cálculo, alertas, presentación, aprobación y asistente. Esto permitió mantener la lógica matemática fuera de Streamlit y probarla de forma aislada.

### Proyección

La IA apoyó la comparación conceptual entre promedio, mediana, ponderación, métodos robustos y tendencia. La selección final quedó expresada en código con criterios explícitos, backtesting y tolerancias verificables. Ningún modelo de lenguaje decide las compras.

### Casos límite y pruebas

Ayudó a enumerar escenarios que podían romper la solución:

- CSV vacío o con columnas faltantes;
- cantidades negativas o fraccionarias;
- semanas duplicadas;
- catálogo incompleto;
- ingrediente omitido;
- producto desconocido;
- semana atípica;
- decisión que mantiene una cantidad sin motivo;
- escenario que modifica accidentalmente la orden real;
- fallo del servicio externo de IA.

Esos casos se convirtieron en pruebas automatizadas. El resultado final es de 62 pruebas aprobadas.

### Producto y UX

La IA también se utilizó para revisar jerarquía, lenguaje empresarial, accesibilidad, navegación y consistencia con la identidad de Barrio Pizza. Las propuestas se validaron observando la aplicación funcionando en navegador, tanto en escritorio como en anchura reducida.

### Documentación

Se utilizó para estructurar el README, explicar supuestos, registrar limitaciones y preparar un guion de demostración. El contenido fue contrastado con el código y los resultados reales antes de publicarlo.

## IA dentro de la aplicación

Barrio AI funciona como una interfaz de consulta sobre el análisis ya calculado:

1. el usuario formula una pregunta;
2. la aplicación recupera únicamente resultados relevantes de la orden activa;
3. construye un contexto compacto y controlado;
4. el modelo redacta una respuesta natural;
5. la interfaz permite consultar los datos utilizados;
6. si el servicio falla, un motor local responde preguntas operativas frecuentes.

El asistente tiene contexto sobre alertas, cantidades, inventario, proveedores, métodos de proyección, decisiones, escenarios y reparación de archivos. No recibe autorización para modificar órdenes ni inventar datos.

## Qué decisiones siguieron siendo humanas

- definir el alcance del producto;
- decidir qué métodos eran adecuados para seis semanas;
- establecer los supuestos operativos;
- comprobar los seis casos base;
- elegir qué propuestas añadían valor real;
- aprobar cambios de código y diseño;
- revisar resultados, capturas y comportamiento;
- conservar secretos fuera del repositorio;
- decidir cuándo una recomendación requería supervisión humana.

## Cómo validé el trabajo asistido por IA

- pruebas automatizadas;
- comparación con resultados base conocidos;
- revisión del cálculo de casos representativos;
- inspección de cada vista en navegador;
- prueba de edición y recálculo;
- prueba del asistente externo y el respaldo local;
- revisión de Git y búsqueda de credenciales;
- verificación de los CSV originales.

La IA aceleró la construcción y amplió la revisión, pero la evidencia —datos, código, pruebas y observación— fue la autoridad final.
