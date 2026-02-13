# electronicCRinvoice

Conector para integrar **Odoo 19** con **Hacienda Costa Rica** de forma directa usando el flujo de **Recepción v4.4**.

## Flujo implementado

1. La factura en Odoo debe estar publicada.
2. Debe existir un XML firmado adjunto en la factura (`Factura XML`).
3. El módulo obtiene token OAuth desde Hacienda.
4. Envía el comprobante directamente a `recepcion/v1/recepcion`.
5. Consulta estado en Hacienda con la clave (`aceptado` / `rechazado`).

## Campos de configuración por compañía

En **Ajustes > Contabilidad**:

- URL API Hacienda
- URL OAuth Hacienda
- Client ID
- Usuario Hacienda
- Contraseña Hacienda
- Timeout
- Actividad económica por defecto

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

## Importante para producción

Este módulo **no firma XML**. Debes tener integrado el firmado previo (HSM/certificado) y adjuntar el XML firmado antes de enviar.

Además, valida los catálogos y estructuras vigentes según la documentación oficial:

- https://api.hacienda.go.cr/docs/
- https://www.hacienda.go.cr/docs/Anexosyestructuras.pdf
