# Auditoría técnica — `l10n_cr_einvoice` (Odoo 19, FE Costa Rica 4.4)

## Resumen ejecutivo
El módulo presenta una base funcional sólida para emisión FE 4.4 en Odoo 19 (XML, firma XAdES, envío/consulta a Hacienda, cron de seguimiento y plantillas de correo). En comparación con riesgos típicos de integraciones tributarias, el código ya incorpora elementos positivos como manejo explícito de errores HTTP, validaciones de endpoint OAuth, y logging en tareas automáticas.

**Veredicto actual:** **Apto para UAT/QA ampliada**, con ajustes recomendados antes de una salida productiva de alto volumen.

---

## Alcance revisado
- Arquitectura general del addon y manifest.
- Seguridad y robustez de integración con Hacienda (OAuth/API).
- Riesgos operativos en cron/procesamiento síncrono.
- Calidad de modelos y configuración sensible.
- Mantenibilidad del código.

---

## Hallazgos clave

### ✅ Fortalezas relevantes
1. **Dependencias externas declaradas correctamente en el manifest.**
   - `requests`, `lxml` y `cryptography` ya están explicitados para despliegues reproducibles.
2. **Manejo de red razonable en OAuth y API.**
   - Se contemplan `Timeout` y `RequestException` con mensajes de negocio controlados.
3. **Trazabilidad mínima en cron.**
   - El cron de consulta registra excepción, marca estado de error y publica mensaje.
4. **Validación defensiva de URL OAuth.**
   - Se valida que el path apunte al endpoint esperado de token.
5. **Protección funcional de campos después de envío.**
   - Se restringe edición de datos FE críticos tras cambio de estado.

### 🟠 Riesgos medios (prioridad recomendada)
1. **Credenciales sensibles sin `password=True` en definición Python.**
   - `fp_hacienda_password` y `fp_signing_certificate_password` son `fields.Char` estándar.
   - Aunque la vista pueda ocultar valores, definir `password=True` en modelo mejora consistencia y evita exposición accidental en UIs o herramientas genéricas.

2. **Archivo `account_move.py` concentra demasiadas responsabilidades.**
   - Mezcla reglas de negocio, serialización XML, firma criptográfica, HTTP client y lógica de cron.
   - Impacto: mayor costo de mantenimiento, pruebas más difíciles y mayor riesgo de regresión.

3. **Procesamiento pesado en `action_post`.**
   - Generación y firma se ejecutan en línea al publicar factura.
   - En lotes grandes puede elevar latencia percibida por usuarios y aumentar contención.

4. **Capturas amplias de `except Exception` en rutas no críticas.**
   - Existen capturas genéricas en varios bloques para resiliencia.
   - Recomendable acotar donde sea posible para mejorar diagnóstico y evitar ocultar fallos de programación.

5. **Ausencia de estrategia explícita de reintentos/backoff.**
   - Hay timeout configurable, pero no política de retry para errores transitorios de red/servicio.

### 🟢 Mejoras de calidad recomendadas
1. **Extraer servicios internos (`services/`)** para API Hacienda, firma XAdES y construcción XML.
2. **Agregar pruebas automatizadas** (unitarias/integración) sobre:
   - normalización de token Authorization,
   - parseo de respuestas JSON inválidas,
   - construcción de clave/consecutivo,
   - comportamiento de cron ante error.
3. **Métricas y observabilidad**: contadores de envío/aceptación/rechazo, tiempos de respuesta y errores por endpoint.
4. **Documentar runbook operativo** (timeouts sugeridos, acciones ante rechazo, reenvío seguro, rotación de certificados).

---

## Plan de remediación sugerido

### Fase 1 (rápida, bajo riesgo)
- Marcar campos de secreto con `password=True`.
- Ajustar mensajes de error para mantener detalle técnico solo en logs.
- Normalizar/centralizar helpers de manejo HTTP y logging contextual.

### Fase 2 (estabilidad operativa)
- Implementar reintentos con backoff exponencial para errores transitorios (idempotencia controlada).
- Añadir pruebas automatizadas mínimas para rutas críticas FE.

### Fase 3 (escalabilidad/mantenibilidad)
- Separar `account_move.py` en servicios especializados.
- Evaluar procesamiento asíncrono para firma/envío en cargas altas.

---

## Conclusión
El módulo está en una posición más madura que una integración FE promedio y **sí puede avanzar a pruebas funcionales/UAT**. Para endurecimiento productivo, las prioridades inmediatas son seguridad de secretos en modelo, reducción de acoplamiento en `account_move.py` y mejora de resiliencia de red mediante reintentos controlados.

---

## ¿Qué hacer para completar la auditoría? (checklist accionable)

### 1) Endurecimiento de seguridad (prioridad alta)
- [ ] Marcar secretos con `password=True` en `res.company`:
  - `fp_hacienda_password`
  - `fp_signing_certificate_password`
- [ ] Revisar que no se muestren en vistas técnicas/listados exportables.
- [ ] Confirmar permisos de acceso a campos sensibles por grupos contables/administración.

**Criterio de cierre:** usuarios no administradores no pueden visualizar secretos en UI ni exportaciones estándar.

### 2) Resiliencia HTTP con reintentos y backoff (prioridad alta)
- [ ] Añadir helper central para requests con:
  - reintentos para `Timeout`, `ConnectionError`, `502/503/504`;
  - backoff exponencial con jitter;
  - límite máximo de intentos (ej. 3).
- [ ] Aplicarlo a OAuth (`_fp_get_hacienda_access_token`) y API (`_fp_call_api`).
- [ ] Mantener mensajes de usuario simples y trazas detalladas en log.

**Criterio de cierre:** ante fallos transitorios, la operación se recupera en <= 3 intentos sin traceback al usuario.

### 3) Observabilidad y soporte operativo (prioridad media)
- [ ] Estandarizar logs con contexto mínimo: `move.name`, `fp_external_id`, endpoint, status.
- [ ] Crear tablero operativo básico con KPIs:
  - enviados,
  - aceptados,
  - rechazados,
  - en error,
  - tiempo promedio de consulta.
- [ ] Definir runbook de incidentes (token inválido, certificado vencido, rechazo Hacienda).

**Criterio de cierre:** soporte puede diagnosticar incidentes FE sin inspección manual de base de datos.

### 4) Refactor gradual de `account_move.py` (prioridad media)
- [ ] Extraer cliente de Hacienda a `services/hacienda_client.py`.
- [ ] Extraer firma XAdES a `services/xml_signer.py`.
- [ ] Dejar `account.move` como orquestador de negocio.

**Criterio de cierre:** reducción de tamaño/ complejidad ciclomática del modelo y pruebas unitarias más simples.

### 5) Pruebas mínimas obligatorias antes de producción (prioridad alta)
- [ ] Test de token OAuth inválido/expirado.
- [ ] Test de respuesta no JSON de Hacienda.
- [ ] Test de reintentos en timeout y éxito posterior.
- [ ] Test de cron ante excepción: marca error + `message_post`.
- [ ] Test de bloqueo de campos FE tras envío.

**Criterio de cierre:** suite verde en CI y evidencia de cobertura sobre rutas críticas FE.

### 6) Plan de ejecución sugerido (3 semanas)
- **Semana 1:** seguridad de secretos + helper HTTP + reintentos.
- **Semana 2:** pruebas automatizadas críticas + mejoras de logging.
- **Semana 3:** extracción de servicios y runbook operativo.

**Resultado esperado:** salida productiva con menor riesgo operativo, mayor mantenibilidad y mejor capacidad de soporte.
