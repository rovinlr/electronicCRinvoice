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

- URL API Hacienda
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

## Importante para producción

La firma XML se genera dentro de Odoo a partir del certificado configurado por compañía.

Además, valida los catálogos y estructuras vigentes según la documentación oficial:

- https://api.hacienda.go.cr/docs/
- https://www.hacienda.go.cr/docs/Anexosyestructuras.pdf
