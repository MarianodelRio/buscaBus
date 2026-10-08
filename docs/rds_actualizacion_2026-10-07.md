# Research Design Solution — Actualización de negocio del 07/10/2026

## Overview
Negocio revisó el PDF de las 15 líneas, dijo que en general estaba bien y mandó
un Excel actualizado (`2026-10-07 ACTUALIZACION HORARIOS.xlsx`, en la raíz del
repo) con horas cambiadas, el aviso "horarios de paso aproximado" en todas las
hojas y las notas internas ya borradas. Además respondió a las preguntas
abiertas P29, P31, P32, P34, P35 y P36. Este ciclo aplica todo eso a
`horarios/`, cierra esas preguntas y mejora una sección del PDF de revisión.
No toca la conversación salvo por lo que se derive de los datos.

## Requisito previo
- Copiar el Excel a `horarios_fuente/2026-10-07 ACTUALIZACION HORARIOS.xlsx`.
  Lo hace el usuario o el coder; no se borran los Excel anteriores, porque
  `horarios_fuente/` no está en git.
- `tools/migracion/cuadre_excel.py`: `EXCEL_PATH` apunta al Excel nuevo.

## Decisiones ya tomadas con el usuario (no rediseñar)
1. **Títulos "INVIERNO DESDE 01/10/2026" (lectura A).** Es la fecha desde la
   que rigen estos horarios actualizados, **no** un cambio de temporada.
   - Las temporadas siguen como confirmó negocio en P02: invierno 15/09-22/06,
     Adamuz desde el 01/09; verano 23/06-14/09, Adamuz hasta el 31/08.
   - Fuente Carreteros, Ochavillos y Belalcázar – Córdoba siguen siendo anuales
     (D-c), aunque su título diga ahora "INVIERNO". Peñarroya y Los Blázquez,
     también (P01).
   - Badajoz dice "a partir del 01/09/2026" y se lee igual.
   - Se deja como nota **P37** para negocio, sin preguntar nada (ver la memoria
     del proyecto: no molestar a negocio).
2. **P29 (opción A):** el Córdoba 12:00 llega a Cabeza del Buey de lunes a
   viernes; los viernes lectivos hay además el de las 15:30. No cambian datos:
   se cierra P29 y se quitan sus marcas.
3. **P31, Badajoz en agosto:**
   - de lunes a viernes la ida **termina en Zafra** (también el viernes) y la
     vuelta sale de Zafra;
   - **sábado, domingo y festivos: sin servicio**, también el 15/08.
4. **Domingos de agosto en Peñarroya – Córdoba:** los viajes Córdoba 14:45 →
   Fuente Obejuna y Fuente Obejuna 18:30 → Córdoba (`bus:cor-1445-dom`,
   `bus:fob-1830-dom`, el mismo autobús que Badajoz) **siguen funcionando** en
   agosto, solo que no continúan a Badajoz. La línea Peñarroya no cambia.
5. **P32, Rivero de Posadas y Los Mochos:** misma hora que Posadas y que
   Almodóvar, respectivamente, solo en los viajes marcados en el Excel
   (naranja = Rivero, verde = Los Mochos; D-l). Pasan a ser paradas normales.
6. **P34, P35:** "ya contestadas": el Excel es correcto tal cual. Cada línea
   conserva sus horas y se cierran.
7. **P36:** resuelta en el Excel: domingo 09:30, Almodóvar 10:15 en vez de 10:40.
8. **P09b deja de aplicarse:** el Excel nuevo recupera el viaje de domingo de
   verano de Pozoblanco que se había borrado. Prevalece el Excel más reciente.

## Verificación hecha (diff semántico por fila y nombre de parada)
Se comparó con `horarios_fuente/HORARIOS NUEVOS MODIFICADO.xlsx` por fila y por
nombre de columna, porque POSADAS INV y BELAL - POZ INV tienen las columnas
desplazadas una posición. Filas ocultas y colores no cambian, salvo lo indicado
abajo.

### Cambios de horas a aplicar
| Hoja (fila) | Cambio |
|---|---|
| VILLAVIC INV 11, 12, 17, 18, 25, 26, 31, 32, 33, 40, 45 | Pantano, El Vacar y Córdoba/Villaviciosa con +5 min (algunos +10). Valores exactos en el Excel, columnas C-E |
| VILLAVIC VER 11, 12, 17, 18, 25, 30 | ídem |
| POSADAS INV 9, 11, 14, 15, 16 | Córdoba: 07:35, 08:15, 12:30, 16:00, 19:15 |
| POSADAS INV 21 | Posadas 10:45, Hornachuelos 11:10 |
| POSADAS INV 34 | Córdoba 17:30 |
| POSADAS INV 38 | Hornachuelos 14:50 |
| POSADAS INV 39, 53 | Almodóvar 20:30 |
| POSADAS INV 45 y POSADAS VER 45 | Almodóvar 10:15 (P36) |
| POSADAS INV 46 | Córdoba 16:20 |
| POSADAS INV 51 | Almodóvar 14:00, Posadas 14:15 |
| POSADAS INV 52 | Almodóvar 17:00, Posadas 17:15 |
| FTE CARRET 9 | 06:30, 06:35, 06:45, 06:50, 07:00, 07:10, Córdoba 07:45 |
| OCHAVILLOS 9 | 09:45, 09:50, 10:00, 10:05, 10:15, Córdoba 10:55 |
| POZOB INV 13 (L-V, VVC 17:30) | Villaharta **18:35D** (amarillo, a demanda) |
| POZOB INV 48 (domingo, VVC 17:15) | Villaharta **18:20D**, Cruce de Villaharta 18:20 → **18:25** |
| POZOB VER 48 (domingo) | Viaje recuperado: VVC 17:15, POZ 17:45, ALC 17:55, CVH 18:20, COR 19:00 |

POSADAS VER solo cambia en la fila 45. Las demás horas de verano de Hornachuelos
**no** cambian (las de invierno sí); no hay que igualarlas.

### Aviso nuevo en todas las hojas
"* LOS HORARIOS SON DE PASO APROXIMADO" → `avisos: [hora_aproximada]` en las 15
líneas (Badajoz ya lo tiene, D-k). `messages.py` muestra una sola vez las notas
comunes a todas las salidas, así que el cliente lo ve una vez por respuesta.

## Proposed Solution

### 1. Líneas (`horarios/lineas/`)
- **Todas:** `avisos: [hora_aproximada]`. Comentario de cabecera con la fuente
  nueva y la lectura del "desde 01/10/2026" (P37).
- **villaviciosa-cordoba, hornachuelos-cordoba, fuente-carreteros-cordoba,
  ochavillos-cordoba, pozoblanco-cordoba:** las horas de la tabla anterior.
- **hornachuelos-cordoba (P32):**
  - Columnas nuevas `RIV` (junto a `POS`) y `MOC` (junto a `ADR`), en las tablas
    de ida y de vuelta.
  - En cada viaje marcado, la misma hora que Posadas o Almodóvar; en el resto,
    `-`.
  - Quitar `pasa_por_rivero` y `para_en_los_mochos` de los viajes, porque ahora
    lo dicen las columnas.
  - Quitar `| P36` y P32/P36 de `pendientes`.
  - Los viajes con las dos marcas (invierno y verano, L-V 09:00 y sábado 08:00
    de ida; sábado 13:30 de vuelta) llevan las dos horas.
  - Las horas iguales en paradas consecutivas ya son válidas (P24, P25).
- **badajoz-cordoba (P31):** dos temporadas.
  ```yaml
  temporadas:
    resto: 01/09 - 31/07
    agosto: 01/08 - 31/08
  dias:
    resto:  { lunes-jueves: horario, viernes: horario, sabado: sin_servicio, domingos-festivos: horario }
    agosto: { lunes-viernes: horario, sabado: sin_servicio, domingos-festivos: sin_servicio }
  ```
  - `resto` = las tablas actuales.
  - `agosto` = ida L-V igual que la actual L-J (termina en Zafra) y vuelta L-V
    igual que la actual. Llevan los mismos `bus:` (`cor-1500`, `fob-1205`).
  - Quitar P31 de `pendientes`.
  - El nombre de temporada `resto` es una propuesta; el planner lo confirma
    contra lo que acepte `formato.py`, que debe cubrir el año entero sin
    solapes.
- **belalcazar-cordoba:** quitar `| P29`, `| P34`, `| P35` y esos pendientes.
  El comentario de P08 se queda.
- **pozoblanco-cordoba:** quitar `| P34` y P34 de `pendientes`.
- **villaviciosa-cordoba:** quitar `| P35` y P35 de `pendientes`.

### 2. `horarios/paradas.yaml` (P32)
- `rivero-de-posadas` y `los-mochos` pasan a ser localidades normales: se quitan
  `pendiente`, `ver`, `minutos` y `aviso`.
- Paradas nuevas: `RIV: { nombre: "Rivero de Posadas", localidad: rivero-de-posadas }`
  y `MOC: { nombre: "Los Mochos", localidad: los-mochos }`.
- `pendientes:` sin P32.
- El código de localidades pendientes (ciclo C2) **se queda**: es genérico y
  tiene tests con fixtures; solo deja de usarse en los datos reales.

### 3. `horarios/observaciones.yaml`
- Borrar `pasa_por_rivero` y `para_en_los_mochos`, que quedan sin uso. Si el
  validador o la revisión dependen de ellos, el planner lo resuelve sin
  mantener datos muertos.

### 4. `docs/preguntas_negocio.txt`
- Cerrar con la respuesta y la fecha 07/10/2026: P29 (opción A), P31
  (Zafra L-V; S/D/F sin servicio; los domingos de Peñarroya sí funcionan), P32
  (misma hora), P34 y P35 (Excel correcto), P36 (Almodóvar 10:15).
- Anotar en P09 que el Excel del 07/10 recupera el viaje.
- Nueva **P37** (informativa, como nota del PDF): "Entendemos que 'desde
  01/10/2026' en los títulos es la fecha desde la que rigen estos horarios, no
  un cambio de temporada: invierno sigue del 15/09 (Adamuz 01/09) al 22/06, y
  Fuente Carreteros, Ochavillos, Belalcázar – Córdoba, Peñarroya y Los Blázquez
  siguen siendo anuales. Si no es así, decídnoslo."
- Quedan abiertas: **P28**, **P30**, **P37**.

### 5. Revisión (`tools/revision.py`)
En "Así aparecen las líneas en el bot":
- Una frase al principio: "Cada pueblo es lo que elige el cliente; si tiene
  más de una parada, se indica cuál."
- Cada pueblo con una sola parada del mismo nombre sale solo con su nombre
  ("Azuaga").
- Si el nombre difiere o hay varias paradas: "Villanueva del Rey — para en:
  Villanueva del Rey (cruce, gasolinera) o Villanueva del Rey (pueblo)".
- La sección "Localidades sin hora de paso" desaparece sola al no haber
  localidades pendientes. Comprobarlo.

### 6. Cuadre (`tools/migracion/cuadre_excel.py`)
- `EXCEL_PATH` → el Excel nuevo.
- Las columnas `RIV`/`MOC` no existen en el Excel: excluirlas del recuento del
  YAML, documentado en el script como derivadas de P32.
- Las tablas de `agosto` de Badajoz repiten horas de `resto`: el cuadre de la
  hoja BADAJOZ cuenta solo `resto`, documentado como derivado de P31.
- Esperado: **100 % en las 18 hojas, sin excepciones**. La fila 48 de POZOB VER
  ya cuadra.

## Key Design Decisions
- **Posadas → Rivero y Almodóvar → Los Mochos (0 minutos) no se excluyen.**
  Excluirlos exigiría una regla nueva o un mensaje que negocio no ha dado
  ("no vendemos" sería falso). Es un dato honesto y nadie lo va a consultar.
  Si molesta, se reabre.
- **Agosto de Badajoz como temporada**, no como `no_circula` (que quitaría la
  línea entera) ni como código nuevo.
- **Los `bus:` se conservan:** fuera de agosto Badajoz y Peñarroya coinciden en
  días, que es lo que exige `_validar_buses`. En agosto solo circula la parte de
  Peñarroya, y eso es correcto.

## Edge Cases
- 15/08 (festivo) en agosto: Badajoz `domingos-festivos: sin_servicio`.
  Peñarroya aplica el horario de domingo (P03c), con los viajes 14:45 y 18:30.
- Un viernes de agosto, Córdoba → Badajoz: `sin_trayecto` o sin salidas ese
  día (el planner comprueba qué da el motor); nunca `sin_datos`.
- Rivero y Los Mochos son aldeas de Posadas y de Almodóvar: sin festivos
  locales (regla del ciclo C2: se declaran en el municipio).
- Viajes que terminan en Posadas sin llegar a Hornachuelos pero con naranja
  (vuelta 16:00): Rivero lleva la hora de Posadas, como dijo negocio.

## Tests (actualizar y añadir)
- Tests con datos reales que citan horas cambiadas (Villaviciosa, Ochavillos,
  Fuente Carreteros, Hornachuelos, Pozoblanco): ponerles los valores nuevos.
- Tests reales de "Los Mochos ofrece Almodóvar": ahora "Los Mochos" se reconoce
  como pueblo con salidas. El comportamiento de localidad pendiente sigue
  cubierto por `fixtures/horarios_pendientes/`.
- Nuevos:
  - Córdoba → Los Mochos un lunes laborable de invierno: salida 14:45, llegada
    15:15 (la misma hora que Almodóvar en ese viaje).
  - Rivero → Córdoba solo en viajes naranja.
  - Córdoba → Badajoz, viernes 07/08/2027: sin salidas a Badajoz; Córdoba →
    Zafra sí (15:00 → 18:15).
  - Badajoz, domingo 08/08/2027: sin servicio.
  - Córdoba → Peñarroya, domingo 08/08/2027: salidas 14:45 y 20:30.
  - Toda respuesta incluye "Horarios de paso aproximados." una sola vez.
  - Revisión: "Azuaga" sin repetir la parada; Villanueva del Rey con "para en:".

## Acceptance Criteria
- `make validar` sin errores. Pendientes: solo P28, P30 y P37.
- `pytest` y `ruff check .` en verde.
- Cuadre al 100 % en las 18 hojas contra el Excel del 07/10, sin excepciones.
- `make revision` (WeasyPrint instalado):
  - portada con pendientes P28, P30 y P37;
  - sin la sección "Localidades sin hora de paso";
  - columnas Rivero y Los Mochos en Hornachuelos;
  - Badajoz con su temporada de agosto;
  - "Cambios desde la versión publicada" con los cambios de horas, si existe
    versión publicada. Si sigue saliendo "Primera versión", decirlo en el
    informe.

## Fuera de alcance
- Borrar `tools/migracion/`, quitar `openpyxl` y archivar el Excel: después de
  que negocio dé el visto bueno a este PDF.
- `diff.py` para festivos y no vendibles.
- Fase 5.

## Scope Estimate
Mediano: casi todo son datos (15 YAML, paradas, observaciones, preguntas), más
un ajuste en `tools/revision.py`, dos excepciones documentadas en el cuadre y la
actualización de tests. Un ciclo planner → coder → reviewer.
