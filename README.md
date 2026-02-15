# electronicCRinvoice

Conector para integrar **Odoo 19** con **Hacienda Costa Rica** de forma directa usando el flujo de **Recepción v4.4**.

## Flujo implementado

1. La factura en Odoo debe estar publicada.
2. El módulo genera automáticamente un XML de comprobante por factura.
3. Firma el XML usando certificado `.p12/.pfx` configurado por compañía.
4. Obtiene token OAuth desde Hacienda.
5. Envía el comprobante directamente a `recepcion/v1/recepcion`.
6. Consulta estado automáticamente y también de forma manual (`aceptado` / `rechazado`).

## Campos de configuración por compañía

En **Ajustes > Contabilidad**:

- URL API Hacienda (puede ser dominio base o la URL completa de recepción de Hacienda, por ejemplo `https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1`)
- URL OAuth Hacienda
- Client ID
- Usuario Hacienda
- Contraseña Hacienda
- Timeout
- Actividad económica por defecto
- Certificado FE (.p12/.pfx)
- Contraseña del certificado
- Opción de consulta automática después de enviar

## Campos funcionales agregados en Odoo

- **Contacto (`res.partner`)**:
  - Tipo de identificación (`fp_identification_type`)
- **Factura (`account.move`)**:
  - Tipo de documento (`fp_document_type`)
  - Actividad económica (`fp_economic_activity_code`)
  - Clave Hacienda (`fp_external_id`)
  - XML (`fp_xml_attachment_id`)
  - Estado FE (`fp_invoice_status`)
- **Impuestos (`account.tax`)**:
  - Código de impuesto (`fp_tax_code`)
  - Tarifa de impuesto (`fp_tax_rate`)

## Botones en factura

- **Enviar a Hacienda**: envía el XML firmado al endpoint de recepción.
- **Consultar Hacienda**: consulta estado por clave.

Además, el módulo ejecuta un `cron` cada 5 minutos para consultar facturas enviadas pendientes de respuesta.

## Catálogo CABYS precargado

El módulo ahora incluye una **lista CABYS base** que se instala automáticamente en `Catálogos FE > Códigos CABYS`, para facilitar la configuración inicial de productos.

Si necesitas el catálogo oficial completo, puedes complementar o reemplazar estos registros desde el mismo menú de catálogos.


## Catálogos de Provincias, Cantones y Distritos

La lista oficial de **provincias, cantones y distritos de Costa Rica** queda disponible en:

- `Contabilidad > Configuración > Catálogos FE > Provincias`
- `Contabilidad > Configuración > Catálogos FE > Cantones`
- `Contabilidad > Configuración > Catálogos FE > Distritos`

Además, en el formulario de **Contacto/Partner** los campos FE se muestran en cascada:

1. Provincia
2. Cantón (filtrado por provincia)
3. Distrito (filtrado por cantón)

La carga inicial se instala automáticamente desde `data/fp_cr_locations_data.xml`.

## Importante para producción

La firma XML se genera dentro de Odoo a partir del certificado configurado por compañía.

Además, valida los catálogos y estructuras vigentes según la documentación oficial:

- https://api.hacienda.go.cr/docs/
- https://www.hacienda.go.cr/docs/Anexosyestructuras.pdf

## Diagnóstico rápido de rechazos de Hacienda

Si Hacienda responde un `MensajeHacienda` con:

- `EstadoMensaje`: `Rechazado`
- `DetalleMensaje`: `...[ SIG_CRYPTO_FAILURE ]`

el rechazo es de **firma criptográfica** (la firma XML no pudo validarse en el lado de Hacienda).

Checklist recomendado:

1. Confirmar que el certificado `.p12/.pfx` y su contraseña son correctos para la compañía emisora.
2. Verificar que el número de identificación del emisor en Odoo coincide exactamente con el del certificado usado para firmar.
3. Validar que el certificado no esté vencido o revocado.
4. Revisar fecha/hora del servidor Odoo (desfase grande puede invalidar validaciones de firma).
5. Comprobar que el XML firmado no fue modificado después del proceso de firma.
6. Reintentar envío generando de nuevo el XML firmado desde Odoo.

Este código de error no suele ser un problema de estructura del XML, sino de **certificado, firma o consistencia de identidad**.


## Logo del Ministerio en la lista de Apps (Odoo)

Para que la app **Hacienda** muestre un logo en el listado de Apps de Odoo, debes colocar un archivo exactamente en:

`factura_profesional_integration/static/description/icon.png`

Recomendaciones:

- Formato: **PNG**
- Tamaño sugerido: **1024x1024** (Odoo lo reescala)
- Nombre obligatorio: `icon.png`

Pasos rápidos:

1. Crea la carpeta si no existe:
   - `mkdir -p factura_profesional_integration/static/description`
2. Copia ahí el logo oficial del Ministerio (renombrado como `icon.png`).
3. Reinicia Odoo.
4. Actualiza el módulo:
   - `odoo -u factura_profesional_integration -d <tu_base>`

Con eso, Odoo toma automáticamente ese ícono para la tarjeta de la app.
