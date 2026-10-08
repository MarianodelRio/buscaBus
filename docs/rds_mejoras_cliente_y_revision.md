# Research Design Solution — Mejoras de cara al cliente y lista de cambios del PDF

## Overview
Tras la actualización de negocio del 07/10/2026, la revisión con el motor real
sacó tres problemas que no cambian ningún horario, pero que se ven:
1. la cabecera del resultado de WhatsApp muestra el **nombre interno** de la
   temporada;
2. cuando no hay salidas en los 7 días siguientes, el bot responde "No hay
   salidas en los próximos días" aunque el servicio vuelva poco después
   (Córdoba → Badajoz en agosto);
3. la lista de "Cambios desde la versión publicada" del PDF usa ids internos y
   no informa de cambios en avisos de línea, calendario ni paradas.

Es un ciclo pequeño, previo a la fase 5. Datos de `horarios/`: no se tocan.

## Problem / Motivation

### 1. Cabecera de temporada (`app/utils/messages.py`, `_cabecera_fecha`)
Hoy: `📅 {día} · horario de {" / ".join(nombres de temporada)}`. Con los datos
reales el cliente verá, por ejemplo:
- "horario de anual": todas las líneas anuales (8 de 15);
- "horario de septiembre-julio": Badajoz, de septiembre a julio;
- "horario de agosto / anual": Córdoba → Peñarroya en agosto (Badajoz +
  Peñarroya);
- "horario de anual / septiembre-julio": Córdoba → Espiel casi todo el año.

`design.md` 4.6 solo contempla "horario de invierno".

### 2. Siguiente día con salidas (`app/services/horarios/query.py`)
- `SIGUIENTE_CON_SERVICIO_DIAS = 7`.
- Córdoba → Badajoz un viernes de agosto: no hay salida (P31), la siguiente es
  el viernes 03/09 y queda fuera de la ventana.
- `messages.py` dice entonces "No hay salidas en los próximos días" + teléfono.
  Es cierto, pero no ayuda.
- Pasa lo mismo con cualquier trayecto que solo exista en otra temporada.

### 3. Lista de cambios del PDF (`app/services/horarios/diff.py`)
Comprobado con `python -m tools.revision --desde HEAD` antes del commit del
07/10:
- 34 de las ~167 líneas dicen "se quita la observación de viaje
  'pasa_por_rivero'": id interno, no texto de negocio.
- **No aparece** que las 14 líneas pasan a llevar el aviso "Horarios de paso
  aproximados" (`Linea.avisos`): `comparar()` no compara los avisos de línea.
- Tampoco compara (hueco anotado desde el ciclo B):
  - calendario: festivos, festivos locales, `sin_servicio_todas_las_lineas`,
    curso y vigencia;
  - `paradas.yaml`: localidades y paradas nuevas, quitadas o renombradas,
    alias y `no_vendibles`;
  - textos de `observaciones.yaml`.

## Proposed Solution

### 1. Cabecera de temporada
**Recomendación:** mostrar la temporada solo cuando dice algo útil y todas las
líneas del resultado coinciden en ella.
- Vocabulario público cerrado en un solo sitio (propuesta: `formato.py`, junto
  a las demás constantes del formato): `invierno` → "invierno", `verano` →
  "verano", `agosto` → "agosto". Cualquier otro nombre (`anual`,
  `septiembre-julio`…) no tiene nombre público.
- Regla en `_cabecera_fecha`:
  - si todas las temporadas usadas en la consulta tienen nombre público y es el
    mismo → `· horario de {nombre}`;
  - en cualquier otro caso → sin texto de temporada (`📅 Viernes 06/08`).
- Festivo y festivo local mantienen su prioridad actual en la cabecera.
- Actualizar `design.md` 4.6 con la regla.
- Alternativa descartada: un campo `nombre_publico` por temporada en cada YAML.
  Es más flexible, pero obliga a editar 15 ficheros y a validar un campo nuevo
  para tres palabras.

### 2. Siguiente día con salidas
**Recomendación:** ampliar la búsqueda hasta **45 días** (cubre un agosto entero
y su primera semana de septiembre) sin cambiar el algoritmo.
- `SIGUIENTE_CON_SERVICIO_DIAS = 45`. Sigue respetando `vigencia_fin` (corta
  antes).
- Coste: hasta 45 resoluciones en memoria por consulta, y solo cuando no hay
  salidas. El planner mide el tiempo de un caso peor con los datos reales; si
  pasa de ~100 ms, se propone otra cosa en el informe, no se cambia en
  silencio.
- Texto (`messages.py`):
  - siguiente a 7 días o menos: el actual, "El siguiente día con salidas es
    {día} {dd/mm}.";
  - siguiente a más de 7 días: "Ese día no hay servicio en este trayecto. El
    siguiente día con salidas es {día} {dd/mm}.";
  - ninguno en 45 días: el actual ("No hay salidas en los próximos días." +
    teléfono).
- Nada de mensajes específicos tipo "en agosto solo hasta Zafra": exigirían
  saber por qué no hay servicio, y el motor no lo sabe.
- Comprobar que la conversación (`flujo.py`) ofrece ese día siguiente como
  botón, igual que hoy con los 7 días, y que un día `sin_datos` dentro de la
  ventana no se toma como día con salidas.

### 3. Lista de cambios del PDF (`diff.py` y su uso en `tools/revision.py`)
- **Observaciones con su texto:** donde hoy sale `'pasa_por_rivero'`, poner el
  texto de `observaciones.yaml` («Pasa por Rivero de Posadas…»). Se toma del
  modelo actual y, si la observación ya no existe, del anterior. Solo si no
  está en ninguno, el id.
- **Avisos de línea:** "Línea X: se añade el aviso «Horarios de paso
  aproximados»." / "se quita el aviso …".
- **Agrupar cuando un mismo cambio afecta a muchas líneas:** si el mismo aviso
  se añade a 3 líneas o más, una sola frase ("Se añade el aviso «…» a 14
  líneas: …").
- **Calendario:** festivos (generales y locales) añadidos o quitados, días sin
  servicio en todas las líneas, fechas del curso y vigencia.
- **Paradas y localidades:** nuevas, quitadas, renombradas; alias añadidos o
  quitados; pares de `no_vendibles` añadidos o quitados.
- **Textos de observaciones** cambiados: «antes» → «ahora».
- Todo en lenguaje de negocio, con el mismo estilo que los mensajes actuales
  de `diff.py`.

### 4. `docs/preguntas_negocio.txt`
Sin cambios en este ciclo (ver la nota del usuario fuera del RDS).

## Integration Points
- `messages.py` lo usan WhatsApp y `tools/telegram_pruebas.py`: el cambio se ve
  en los dos.
- `query.consultar` ya devuelve `temporadas` (línea, temporada); no hay que
  tocar el modelo.
- `diff.comparar` solo lo llama `tools/revision.py`; nada del bot depende de él.

## Edge Cases
- Consulta que mezcla Pozoblanco – Córdoba (invierno) y Belalcázar – Córdoba
  (anual): la cabecera va sin temporada. Es aceptable: las horas son las
  correctas.
- Un festivo en agosto en Badajoz: la cabecera de festivo gana, como hoy.
- `sin_servicio_general` (25/12, 01/01): su mensaje no cambia, pero
  `siguiente_con_servicio` ahora puede llegar más lejos. Comprobar el texto.
- Ventana de 45 días que cruza `vigencia_fin` (finales de julio de 2027 en
  adelante): se corta en la vigencia, como hoy.
- `diff`: observación renombrada (id distinto, mismo texto) → aparece como
  quitada y añadida. Se acepta.

## Tests
- `test_conversation.py` / `test_interactive.py` o un test de mensajes:
  - Córdoba → Badajoz, viernes 06/08/2027: "El siguiente día con salidas es
    viernes 03/09." (comprobar el día real con el calendario cargado);
  - Pozoblanco → Córdoba, un miércoles de invierno: "horario de invierno";
  - Ochavillos → Córdoba (anual): sin "horario de";
  - Córdoba → Peñarroya, domingo de agosto: sin "horario de".
- `test_query.py`: `siguiente_con_servicio` a más de 7 días, y `None` si no hay
  nada en 45.
- `test_diff.py`:
  - aviso de línea añadido o quitado;
  - el mismo aviso en ≥3 líneas → una sola frase;
  - observación de viaje con su texto, no su id;
  - festivo añadido o quitado; festivo local; día sin servicio en todas las
    líneas;
  - parada nueva o renombrada; alias; `no_vendibles`;
  - texto de observación cambiado.
- `test_revision.py`: la sección de cambios usa esas frases.

## Acceptance Criteria
- `pytest`, `ruff check .` y `make validar` en verde; el cuadre sin cambios
  (100 % en las 18 hojas).
- Ningún mensaje al cliente con "horario de anual", "septiembre-julio" ni dos
  temporadas unidas por "/".
- Córdoba → Badajoz en agosto da la fecha del siguiente día con salidas.
- Regenerando la revisión contra el commit anterior a la actualización del
  07/10 (`--desde <ese commit>`):
  - aparece una sola frase con el aviso de paso aproximado y sus 14 líneas;
  - ninguna frase contiene `pasa_por_rivero` ni `para_en_los_mochos`;
  - salen las paradas nuevas Rivero de Posadas y Los Mochos.
- `design.md` (4.6 y la sección de la vista de revisión) actualizado.

## Fuera de alcance
- Cualquier cambio de horarios o de `horarios/`.
- Borrar `tools/migracion/` (tras el visto bueno de negocio) y fase 5.

## Scope Estimate
Pequeño-mediano: dos funciones de `messages.py`, una constante y un texto en
`query.py`, y la mayor parte del trabajo en `diff.py` y sus tests. Un ciclo
planner → coder → reviewer.
