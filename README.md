# electronicCRinvoice

Conector base para integrar **Odoo 19** con un API externo de facturación electrónica donde:

1. Odoo envía los datos de la factura.
2. El API construye el XML.
3. Odoo guarda el XML como adjunto en la factura.

## Estructura

- `odoo_addons/factura_profesional_integration`: módulo inicial de integración.

## Flujo implementado

- Campos de configuración por compañía:
  - URL base del API
  - Token
  - Timeout
- Método `action_fp_send_to_api` en `account.move` para:
  - Validar estado de factura
  - Armar payload
  - Invocar `POST /documents`
  - Guardar XML devuelto en `ir.attachment`

## Instalación rápida

1. Copiar `odoo_addons/factura_profesional_integration` al `addons_path` de Odoo 19.
2. Actualizar lista de apps e instalar **Factura Profesional API Connector**.
3. Ir a **Ajustes > Contabilidad** y completar URL, token y timeout.

## Uso desde código (ejemplo)

```python
invoice.action_fp_send_to_api()
```

## Importante para producción

Debes alinear el payload y endpoint con la documentación final del proveedor (campos obligatorios, autenticación, firma, manejo de errores y estados tributarios).
