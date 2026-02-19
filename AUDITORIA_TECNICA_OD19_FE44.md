# Auditoría técnica — `l10n_cr_einvoice` (Odoo 19, FE Costa Rica 4.4)

## Alcance
Revisión estructural y técnica del addon con foco en:
- compatibilidad con Odoo 19,
- uso de ORM / constraints,
- integración con Hacienda (OAuth, XML firmado, robustez HTTP),
- cron jobs,
- seguridad de datos sensibles.

## Observaciones clasificadas

### 🔴 Críticas
1. **Llamadas HTTP sin manejo de excepciones de red (token y API de Hacienda)**
   - En `_fp_get_hacienda_access_token` y `_fp_call_api` se usa `requests.post/get` sin `try/except requests.exceptions.RequestException`.
   - Un timeout, DNS error o corte de red puede romper la transacción con traceback no controlado hacia usuario/cron.
   - Impacto: caídas en producción, estados parciales (`fp_api_state`) y mala experiencia operativa.

2. **Cron marca error sin trazabilidad (except genérico sin log)**
   - En `_fp_cron_consult_pending_documents` se captura `Exception` y solo asigna `fp_api_state = "error"`.
   - No se registra detalle del error ni se publica mensaje en chatter.
   - Impacto: incidentes silenciosos, difícil auditoría/soporte.

3. **Posible exposición de información sensible en errores de autenticación**
   - Al fallar OAuth se construye `UserError` con `response.text` completo.
   - Dependiendo del proveedor/infra, el body puede incluir información sensible de autenticación o diagnóstico interno.
   - Impacto: fuga de información a usuarios funcionales o logs de cliente.

### 🟠 Riesgo medio
1. **`action_post` ejecuta lógica pesada síncrona (XML + firma criptográfica)**
   - `action_post` genera y firma XML de cada factura al confirmar.
   - En cargas altas puede afectar tiempo de posteo y lock de usuario.
   - Recomendación: separar generación/firma a cola asíncrona o job diferido.

2. **Uso de SQL directo en defaults/bootstrapping**
   - `_default_fp_economic_activity_id` consulta `information_schema` por SQL en cada evaluación de default.
   - Es válido para bootstrap defensivo, pero con costo extra y dependencia en metadatos DB.
   - Recomendación: minimizar con cache/contexto de instalación o migración explícita.

3. **`_auto_init` de `res.partner` agrega columnas manualmente con SQL**
   - Soluciona esquemas rotos, pero puede ocultar problemas de migración y salirse de rutas estándar ORM.
   - Recomendación: mantener solo como parche temporal y reforzar scripts de migración.

4. **Sin política explícita de reintentos/backoff para HTTP**
   - Hay timeout configurable, pero no retry controlado en errores transitorios.
   - Riesgo de falsos negativos con infraestructura inestable.

5. **Campos secretos sin `password=True` a nivel campo Python**
   - En vistas se usa `password="True"`, correcto para UI.
   - No obstante, en modelo `fields.Char` de passwords no define `password=True`.
   - Recomendación: marcar también en definición de campo para mayor consistencia de seguridad.

### 🟢 Mejora recomendada
1. **Declarar `external_dependencies` en `__manifest__.py`**
   - Se importan `requests`, `lxml`, `cryptography`; deberían declararse para instalaciones reproducibles.

2. **Agregar logger estructurado (`logging.getLogger(__name__)`)**
   - Especialmente en cron, OAuth y envío/consulta de Hacienda.

3. **Refinar separación de responsabilidades en `account_move.py`**
   - El archivo concentra mucha lógica (generación XML, firma XAdES, HTTP, cron).
   - Recomendación: extraer servicios (`services/hacienda_client.py`, `services/xml_signer.py`).

4. **Evaluar constraints adicionales en Python (`@api.constrains`) para reglas de negocio contextuales**
   - Ejemplo: validar obligatoriedad de ciertos campos FE por tipo de documento/partner.

5. **Documentar estrategia de colisiones de constraints en bases con datos legacy**
   - Existen varias `models.Constraint(UNIQUE(...))`; conviene checklist de pre-migración para deduplicar datos antes de upgrade.

## Sugerencias concretas (ejemplos)

### 1) Manejo robusto de requests en OAuth/API
```python
import logging
import requests
from requests import exceptions as req_exc

_logger = logging.getLogger(__name__)

try:
    response = requests.post(token_url, data=data, timeout=company.fp_api_timeout)
    response.raise_for_status()
except req_exc.Timeout:
    raise UserError(_("Tiempo de espera agotado al autenticar con Hacienda."))
except req_exc.RequestException as err:
    _logger.exception("Error de red OAuth Hacienda")
    raise UserError(_("No fue posible conectar con Hacienda. Intente nuevamente.")) from err
```

### 2) Mejor trazabilidad en cron
```python
import logging
_logger = logging.getLogger(__name__)

try:
    move.action_fp_consult_api_document()
except Exception as err:
    _logger.exception("Error consultando FE pendiente %s", move.name)
    move.fp_api_state = "error"
    move.message_post(body=_("Error en consulta automática a Hacienda: %s") % err)
```

### 3) Manifest con dependencias externas
```python
"external_dependencies": {
    "python": ["requests", "lxml", "cryptography"],
},
```

## Veredicto de preparación para producción
**Estado actual: No listo para producción sin ajustes mínimos.**

### Ajustes mínimos obligatorios
1. Encapsular llamadas HTTP con manejo explícito de excepciones de red y mensajes controlados.
2. Añadir logging útil en cron/procesos Hacienda (evitar errores silenciosos).
3. Reducir exposición de detalles sensibles en errores de autenticación/API.
4. Declarar `external_dependencies` en manifest para despliegues confiables.

Con esos cambios, el módulo quedaría en un estado razonable para pasar a pruebas UAT/QA con carga y escenarios de contingencia de Hacienda.
