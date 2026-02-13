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

## ¿Por qué no aparece en Aplicaciones?

En Odoo los módulos **no se detectan** si el `addons_path` apunta a una carpeta equivocada.

Checklist rápido:

1. Verifica que la ruta configurada en `addons_path` sea exactamente la carpeta que contiene el módulo:
   - ✅ Correcto: `/ruta/proyecto/odoo_addons`
   - ❌ Incorrecto: `/ruta/proyecto` (si el módulo está dentro de `odoo_addons/`)
2. Confirma que exista el archivo:
   - `odoo_addons/factura_profesional_integration/__manifest__.py`
3. Reinicia Odoo después de ajustar `addons_path`.
4. En **Aplicaciones**, quita el filtro "Aplicaciones" o busca por nombre técnico `factura_profesional_integration`.
5. Haz clic en **Actualizar lista de aplicaciones**.

> Este módulo ahora está marcado como `application=True`, por lo que también debería aparecer con el filtro de Aplicaciones activado.

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
