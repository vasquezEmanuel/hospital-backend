# Importación de datos (ETL) — cómo funciona y qué se decidió

Carpeta del código: `etl/`. Comandos (desde la raíz del repo, con el entorno virtual activo y la base encendida):

```powershell
python -m etl.cli catalogo   datos_reales\CATALOGO_CIE10.xls     # 1º el catálogo
python -m etl.cli atenciones datos_reales\PACIENTES_ATENDIDOS.xls # 2º las atenciones
```

Acepta `.xls` (Excel 97-2003, el formato que entrega el hospital), `.xlsx` y `.csv`. Repetir una carga no duplica
nada. Todo lo que no se puede cargar queda en la tabla `importacion_fila` con su motivo: **nada se descarta**.
Los archivos reales NUNCA se suben a Git (carpeta `datos_reales/`, ignorada).

## Catálogo CIE-10
- Encabezado en cualquier fila de las primeras 15; columnas `COD_3`, descripción, `COD_4`, descripción.
- Se limpian las marcas `†` y `*` de los códigos de doble clasificación (`A065†` → `A065`).
- **Códigos odontológicos:** el archivo del hospital los marca con **relleno amarillo** (no con subrayado, como se
  creía). También se reconoce el subrayado. La marca en la fila donde empieza una categoría (la que trae `COD_3`)
  vale para toda la categoría; la marca en una fila suelta (S005) vale solo para ese código.
  Resultado con el archivo recibido: 169 códigos odontológicos (K00–K14, C01–C10 de cavidad bucal, D00/D10/D11 y
  algunos S00–S02). `--solo-filas-marcadas` desactiva la extensión por categoría.
- Un CSV no conserva el formato: debe traer una columna `ES_ODONTOLOGICO` (SI/NO).

## Hoja de atenciones
- Columnas obligatorias: `FECHA DE LA ATENCIÓN`, `DOCUMENTO DE IDENTIDAD`, `NOMBRE`. Sin documento no hay paciente
  (regla 1): la fila va a revisión.
- Fechas de Excel (tipo fecha o número de serie) y texto `DD/MM/AAAA` o `AAAA-MM-DD`.
- **Diagnóstico de hospitalización:** debe resolver a un código CIE-10 (`C187-TUMOR MALIGNO DEL COLON`, `C187`,
  o la descripción exacta). Si no, la fila va a revisión.
- **Diagnóstico bucal:** en la fuente es texto clínico libre (`CARIES`, `GINGIVITIS`). Si resuelve a códigos, se
  vinculan y deben ser odontológicos (regla 2; si no, la fila va a revisión). Si no resuelve, se guarda **solo el
  texto original** en `diagnostico_bucal`, sin código, pendiente de codificar.

Diagnósticos bucales pendientes de codificar:

```sql
SELECT b.id_diagnostico_bucal, a.fecha_atencion, p.documento_identidad, b.descripcion
FROM diagnostico_bucal b
JOIN atencion a USING (id_atencion) JOIN paciente p USING (id_paciente)
LEFT JOIN cie10_x_diagnostico_bucal x USING (id_diagnostico_bucal)
WHERE x.cod_4 IS NULL AND b.activo ORDER BY a.fecha_atencion DESC;
```

## Pendientes con la Dra. Gloria Alvarez
1. El archivo de atenciones recibido trae `DOCUMENTO DE IDENTIDAD` y `NOMBRE` **vacíos** en sus 6 filas (¿se
   anonimizó para enviarlo?). Se necesita la versión con esas dos columnas para poder importar.
2. Confirmar la regla de marca del catálogo: relleno amarillo en la primera fila de cada categoría = toda la categoría.
3. Los diagnósticos bucales vienen como texto libre: ¿se codifican a CIE-10 a mano después de importar, o se acuerda
   una lista de equivalencias (p. ej. `CARIES` → K02.x) para automatizarlo?