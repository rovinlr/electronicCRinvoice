# Análisis: Factura Electrónica de Compra (FEC) v4.4

## Fuentes revisadas
- PDF oficial de Hacienda: **ANEXOS Y ESTRUCTURAS v4.4** (enlace del usuario).
- Documento compartido de Google: exportado y revisado como referencia del `FacturaElectronicaCompra.xsd`.
- Código del módulo `l10n_cr_einvoice` en este repositorio.

## Hallazgos funcionales clave (FEC v4.4)
1. **Tipo de comprobante y schema**
   - FEC corresponde al código **08** en el consecutivo.
   - Namespace/schema de FEC: `.../v4.4/facturaElectronicaCompra`.

2. **Identificación en FEC (dato crítico)**
   - Para FEC se habilitan tipos de identificación del emisor:
     - `05` = Extranjero No Domiciliado.
     - `06` = No Contribuyente.
   - Para tipos `05` y `06`, el número de identificación puede ser **alfanumérico** (hasta 20 caracteres).

3. **Ubicación y señas del emisor en FEC**
   - `Ubicacion` pasa a condición especial cuando el emisor usa tipo `05`.
   - `OtrasSenasExtranjero` aplica para escenario de emisor con tipo `05` (FEC).

4. **Condición de venta relevante en FEC**
   - Código `13` (Venta bienes usados no contribuyente) se vincula al uso de tipo de identificación `06`.

5. **Información de referencia**
   - En FEC existe `InformacionReferencia` (hasta 10 ocurrencias en el schema).
   - `TipoDocIR` contempla código `16` (**Comprobante de Proveedor No Domiciliado**) y en catálogos se incorporan además códigos `17` y `18` para notas asociadas a FEC.

## Revisión del estado actual del módulo

### Lo que ya está bien encaminado
- El módulo soporta FEC como tipo documental válido (`FEC`) con namespace/xsd v4.4 correcto.
- Las facturas de proveedor (`in_invoice`) se fuerzan/validan como FEC.
- El código de tipo documental para consecutivo usa `08` para FEC.

### Brechas detectadas contra la sección FEC
1. **Catálogo de identificación incompleto**
   - `res.partner.fp_identification_type` no incluye el código `06` (No Contribuyente).

2. **Número de identificación alfanumérico no soportado para FEC 05/06**
   - Al serializar identificación, el módulo elimina todo lo que no sea dígito.
   - Esto rompe el caso permitido por v4.4 para `Extranjero No Domiciliado` y `No Contribuyente` cuando el número contiene letras.

3. **Ubicación del emisor se serializa siempre**
   - Actualmente `Ubicacion` se escribe siempre para emisor/receptor, sin condición específica para FEC con tipo `05`.

4. **Catálogo de TipoDocIR incompleto para FEC**
   - `fp_reference_document_type` no contempla `16`, `17`, `18`.

5. **`InformacionReferencia` no se emite para FEC**
   - La función `_fp_append_reference_information` solo corre para `NC`/`ND`.
   - En FEC, escenarios con proveedor no domiciliado requieren referencia específica (p. ej. TipoDocIR=16), por lo que falta soporte.

## Recomendación priorizada
1. Agregar `06` en `fp_identification_type` de partner.
2. Ajustar serialización de `Identificacion/Numero` para permitir alfanumérico cuando tipo es `05` o `06` en FEC.
3. Condicionar `Ubicacion` y `OtrasSenasExtranjero` según reglas FEC del tipo de identificación.
4. Extender catálogo `TipoDocIR` con `16/17/18`.
5. Permitir y validar `InformacionReferencia` en FEC cuando aplique (especialmente para proveedor no domiciliado).

## Conclusión
El módulo **sí implementa la base de FEC** (tipo, namespace, flujo para `in_invoice`), pero hay **brechas de cumplimiento v4.4** en catálogos y reglas condicionales de FEC, sobre todo en identificación (`05/06`) y referencias (`TipoDocIR` y emisión en FEC).
