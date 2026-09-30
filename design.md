# Buscabus — Bot de WhatsApp de horarios de autobús

> Documento base del repositorio. Define el alcance, los datos, la conversación,
> la reutilización del proyecto Peluquería, la infraestructura y las fases de
> implementación. Las dudas abiertas están al final.
>
> Estado: **esbozo aprobado para planificar**. No es un diseño cerrado.
> Fecha: 2026-09-23. Revisado el 2026-09-26: los horarios pasan a mantenerse a
> mano en `horarios/` (sección 2) y el Excel es de un solo uso.

---

## 1. Qué es

Bot de WhatsApp que informa de los horarios de autobús de una empresa de
transporte interurbano de la provincia de Córdoba. El cliente pregunta origen,
destino y día, y el bot responde con las salidas de ese día.

- **Nombre de la app / repositorio:** `buscabus`
  (alternativa descartada por sosa: `autobuses`).
- **Operador:** por el teléfono `957 42 90 30` que aparece en las notas del
  Excel, es **Autocares San Sebastián** (Córdoba). *Pendiente de confirmar con
  Mariano.*
- **Base técnica:** mismo esqueleto que el bot `Peluqueria` (FastAPI + WhatsApp
  Cloud API + systemd + nginx + DuckDNS en una VM de GCP).
- **Diferencia esencial con Peluquería:** no hay API externa ni escrituras. Los
  horarios se cargan en memoria al arrancar y solo se leen. No hay reservas,
  ni bloqueos, ni estado que persistir.

### Alcance de la v1

| Dentro | Fuera (v2 o más adelante) |
|---|---|
| Consulta de horarios origen → destino → día | Trasbordos y rutas combinadas |
| Solo trayectos **directos** | Avisos / banner de incidencias |
| Información de contacto y enlaces | Recordar el pueblo del usuario |
| Precios (cuando lleguen los datos) | Ubicación de la parada en el mapa |
| Comandos de administrador por WhatsApp | Tiempo real, retrasos, ocupación |
| | Venta de billetes, IA/NLP |

Decisiones ya tomadas por Mariano:

1. **Sin IA.** Coincidencia de texto determinista (normalización + alias +
   distancia de edición). La IA queda como refuerzo futuro solo si se mide que
   más del ~10-15 % de los textos no se entienden.
2. **Menú principal aparte**, no fusionado con la primera pregunta.
3. **Botones del resultado:** `Otro día` / `Ver la vuelta` / `Otra consulta`.
4. **Sin avisos y sin recordar-pueblo en la v1.**
5. **El precio va al final del mensaje de horarios.**

---

## 2. Los datos de horarios

> **Cambio de enfoque (2026-09-26).** El Excel de la empresa se usa **una sola
> vez** para obtener los horarios iniciales. Las actualizaciones futuras no
> llegarán como Excel: negocio comunicará los cambios (correo, teléfono, PDF...)
> y el desarrollador los aplicará a mano en `horarios/`, que pasa a ser la
> **fuente de verdad**. Se abandona el importador robusto y los CSV de `data/`.

### 2.1 Origen: el Excel inicial (uso único)

`HORARIOS NUEVOS.xlsx` (en `horarios_fuente/`) tiene 18 hojas. Salen de él
**15 líneas comerciales**: 11 hojas son una línea en invierno y verano, y la
hoja `TORR` contiene 4 líneas distintas sin nombre.

Cifras recalculadas el 2026-09-24:

- **64 paradas** distintas tras normalizar (65 si se separan las dos
  Villafrancas; `C.MURIANO` tiene columna pero ninguna hora y se descarta).
- **~222 viajes públicos**: 217 filas más las 5 columnas de Badajoz. Los ~236
  que se daban antes contaban también las 8 filas ocultas y las 6 de régimen
  interno de Belalcázar-Pozoblanco.
- **Hay autobuses repetidos en varias hojas**: el de Badajoz aparece entero
  dentro de `PYA INV`, y dos viajes de `PYA` están también en `BLAZQUEZ`.
  El motor los fusiona (sección 3).
- Pendiente de recalcular sobre los datos migrados: pares origen→destino con
  servicio directo (se estimaron 706), destinos por origen y pares servidos
  por más de una línea (se estimaron 95, parte de ellos son el mismo autobús).

### 2.2 Problemas del Excel (solo afectan a la migración)

Se documentan para migrar bien, no porque el sistema tenga que tolerarlos en el
futuro. El análisis completo, las preguntas a negocio (P01-P27) y las
decisiones ya tomadas (D-a a D-p) están en
[`docs/preguntas_negocio.txt`](docs/preguntas_negocio.txt).

1. **El significado está en los colores, y cada hoja tiene su leyenda.** El
   amarillo es "a demanda" en Pozoblanco, Belalcázar-Córdoba y Badajoz, pero
   "entran en pueblo" en Peñarroya; en Los Blázquez eso mismo es verde.
2. **Las marcas actúan a tres niveles**: toda la hoja (Badajoz, "horarios de
   paso aproximado"), todo el viaje (Posadas: Rivero, Los Mochos, El Pedrera) o
   **una sola parada de un viaje** (a demanda; "solo viernes lectivo" solo en
   la última parada; "solo si hay viajeros desde Córdoba" solo en Villanueva de
   Córdoba).
3. **Formatos de hora heterogéneos**: `datetime.time`, `"8:00*"`, `"18.10"`,
   `"21:45**"` y `"VIERNES ESCOLAR 16:00"`. Hay paradas consecutivas con la
   misma hora: la regla es "las horas no retroceden", no "avanzan".
4. **Contenido no público**: 17 notas internas, filas ocultas en
   `BELAL - POZ INV` **y** `BELAL - POZ VER`, un bloque "SOLO PARA RÉGIMEN
   INTERNO", y las columnas `RUTA` y `VALIDADORA`.
5. **Estructuras distintas**: `BADAJOZ` está traspuesta (paradas en filas);
   `TORR` no tiene nombres de línea; las tablas de fin de semana de `POZOB` y
   `BELAL- COR` tienen otras columnas que las de entre semana; `PYA` no tiene
   `RUTA` ni `VALIDADORA`.
6. **Muchos tipos de día**: lunes; martes-viernes; lunes-viernes;
   lunes-jueves; viernes; sábado; domingo; domingos y festivos; "sábado,
   domingos y festivos"; "no hay servicio". Villaviciosa no dice nada de los
   domingos.
7. **Nombres inconsistentes**: `GUALDALCAZAR`/`GUADALCAZAR`, `ST`/`STA
   EUFEMIA`, cuatro grafías de Cruce de Villaharta, tres del hospital de
   Pozoblanco. `VILLAFRANCA` es de Córdoba en Adamuz y de los Barros en
   Badajoz.
8. **Temporadas incoherentes**: `POSADAS INV` y `BLAZQUEZ` llevan fechas de
   2025/26 (decisión D-a: el año se ignora, solo cuentan día y mes); `PYA` y
   `BLAZQUEZ` no tienen verano; el verano termina en "fin verano" sin fecha;
   `ADAMUZ VER` dice "DESDE AQUASIERRA" (errata, D-b).
9. **Posibles erratas y contradicciones**: el Córdoba 10:30 llega a Peñarroya a
   las 11:55 según `PYA` y a las 12:30 según `BLAZQUEZ` (P21), y hay varios
   tramos con tiempos anómalos (P22-P26). Mientras negocio no responda, se
   migran tal cual con su pendiente marcado.

### 2.3 La fuente de verdad: `horarios/`

**Principio:** los horarios viven en ficheros de texto **editados a mano** y
versionados en git. Están pensados para dos personas:

- **El desarrollador** aplica un cambio que comunica negocio editando una fila
  de texto. El diff de git muestra exactamente qué cambió.
- **Negocio** no lee estos ficheros: lee una vista **HTML + PDF** generada a
  partir de ellos, que incluye los cambios respecto a la versión publicada.

**Regla de oro (sustituye a la del importador): el validador no deja pasar
nada ambiguo.** Una parada desconocida, una letra de observación sin definir,
unas horas que retroceden, un día de la semana sin declarar o una temporada que
no cubre el año detienen `make validar`, el arranque del bot y los tests con un
mensaje concreto (fichero, tabla, fila, motivo). Un horario mal cargado hace
que alguien pierda un autobús.

#### Estructura

```
horarios/
  paradas.yaml          zonas, localidades y paradas (código, nombre público, alias)
  observaciones.yaml    catálogo de observaciones y el texto exacto que ve el cliente
  lineas/
    pozoblanco-cordoba.yaml   una por línea comercial; el nombre del fichero es su id
    ...
  calendario.yaml       festivos y periodo escolar
```

#### `paradas.yaml`

```yaml
zonas:
  los-pedroches: Los Pedroches
localidades:                       # lo que elige el usuario
  pozoblanco: { nombre: Pozoblanco, zona: los-pedroches, alias: [pozo] }
  villafranca-de-cordoba: { nombre: Villafranca de Córdoba, zona: adamuz, alias: [villafranca] }
  villafranca-de-los-barros: { nombre: Villafranca de los Barros, zona: extremadura, alias: [villafranca] }
  aldea-ejemplo:                   # localidad pendiente (P15/P32): sin hora propia
    nombre: Aldea Ejemplo
    zona: los-pedroches
    pendiente: P32
    ver: pozoblanco
    minutos: 4
    aviso: pasa_por_aldea_ejemplo
paradas:                           # lo que muestra el resultado
  POZ: { nombre: Pozoblanco, localidad: pozoblanco }
  PZH: { nombre: Pozoblanco (Hospital), localidad: pozoblanco }
pendientes: [P18]                  # preguntas abiertas que no son de una línea
                                    # concreta (zonas, localidades, paradas)
no_vendibles:                      # P12b: pares de localidades sin venta de
  - [cordoba, alcolea]              # billetes, en ninguno de los dos sentidos
```

- **`pendientes:`** (opcional, lista): preguntas abiertas (`P\d{2}`, igual que
  las de una línea) que afectan a zonas, localidades o paradas y no a una
  línea concreta. Un pendiente mal formado detiene la validación, igual que
  en `lineas/*.yaml`.

- **Localidad pendiente** (P15/P32, ciclo C2): una aldea en la que algunos
  autobuses paran pero de la que no se conoce la hora de paso. Campos:
  `pendiente: Pnn` (debe estar también en `pendientes:` de este fichero),
  `ver: <localidad>` (la localidad en cuyo lugar se consulta; obligatorio con
  `pendiente`), `minutos: <entero 1-60>` (obligatorio; distancia a `ver`, con
  ella se construye el mensaje "a unos N minutos de X"; nada en config ni en
  código) y `aviso: <observación>` (opcional; observación de tipo aviso con
  ámbito `viaje` que los viajes que paran ahí llevan tras el `|`; solo sirve a
  la vista de revisión). `ver`, `minutos` y `aviso` sin `pendiente` son
  errores. Una localidad pendiente no puede tener paradas en `paradas:`
  (no tiene horas), `ver` no puede ser ella misma ni otra pendiente, y no
  cuenta como "sin uso". El motor de consulta nunca la recibe (`consultar`
  lanza `ValueError`); la conversación la intercepta (4.7, 4.8).
  `no_vendibles` o `festivos_locales` que nombren una localidad pendiente no
  se validan: es un caso límite sin efecto.
- **`no_vendibles:`** (opcional, lista de pares `[localidad, localidad]`):
  trayectos que la empresa no puede vender, en ambos sentidos (P12b:
  Córdoba-Campus de Rabanales, Córdoba-Alcolea, Campus de Rabanales-Alcolea).
  Localidad sin definir, la misma localidad dos veces o un par repetido
  (también invertido: `[a, b]` y `[b, a]` son el mismo) son errores. Un par
  que ninguna línea conecta es un aviso. El motor lo trata como un estado
  propio (`no_vendible`, sección 3), no como "sin trayecto".
- **Códigos de parada de 3 caracteres** (mayúsculas ASCII, únicos,
  mnemotécnicos: `COR`, `CVH`, `POZ`, `PZH`, `VFC`, `VFB`). Mantienen las
  tablas estrechas; la vista de negocio muestra siempre el nombre completo.
- Un alias compartido por varias localidades (`villafranca`) es la forma de
  declarar una ambigüedad: el matcher debe preguntar (4.7).

#### `observaciones.yaml`

```yaml
a_demanda:
  letra: D                       # obligatoria si se puede usar a nivel de parada
  tipo: condicion                # condicion | aviso
  ambitos: [parada]              # parada | viaje | linea
  texto: "A demanda: llama al {telefono} con 24 horas laborables de antelación."
hora_aproximada:
  letra: A                       # libre: también se usa en la celda (ámbito parada)
  tipo: aviso
  ambitos: [linea, parada]
  texto: "Horarios de paso aproximados."
```

- **Condición**: cambia si el autobús sale o si para. Es un conjunto cerrado
  que el motor conoce (`a_demanda`, `solo_viernes_lectivo`,
  `solo_si_viajeros_desde_cordoba`); el validador rechaza una condición que el
  código no sepa aplicar.
- **Aviso**: solo informa (`pasa_por_rivero`, `para_en_los_mochos`,
  `no_para_en_el_pedrera`, `solo_virgen_remedios`, `hora_aproximada`...). Se
  pueden añadir libremente. `entra_en_pueblo` ya no existe: en Villanueva del
  Rey "entrar en el pueblo" es **otra parada** (P20, `VRE` frente a `VRC`), no
  una nota. `hora_aproximada` lleva la letra `A` y sirve como aviso de línea o
  de parada; con la letra en una celda, la nota solo sale cuando esa parada es
  el origen o el destino de la consulta.
- **El texto al cliente vive aquí**, no en `messages.py`, para que negocio lo
  valide en la vista de revisión. `messages.py` solo le da formato.
- **El único marcador admitido en `texto` es `{telefono}`**, sustituido por el
  `telefono_demanda` de la línea (`formato.texto_observacion`). Cualquier otro
  `{xxx}` es un error de validación, no un marcador ignorado en silencio.

#### Un fichero de línea

```yaml
# horarios/lineas/pozoblanco-cordoba.yaml
nombre: Pozoblanco – Córdoba
telefono_demanda: 957 42 90 30     # obligatorio si alguna tabla usa a_demanda
avisos: []                         # observaciones de ámbito línea, p.ej. [hora_aproximada]
no_circula: []                     # meses sin servicio, p.ej. [agosto]

temporadas:                        # día/mes sin año; deben cubrir el año entero sin solaparse
  invierno: 15/09 - 22/06
  verano:   23/06 - 14/09          # "todo el año" para las líneas anuales

dias:                              # cada temporada declara las 8 clases de día
  invierno: { lunes-viernes: horario, sabado: horario, domingos-festivos: horario }
  verano:   { lunes-viernes: horario, sabado: horario, domingos-festivos: horario }

horarios:
  - temporada: invierno
    dias: lunes-viernes
    tabla: |
      CON     VVC     PZH    POZ    ALC    VHA     CVH    COR
      -       06:25D  06:45  06:55  07:05  -       -      08:15
      07:20D  07:45   08:05  08:15  08:25  08:50D  08:55  09:30
      -       17:30   -      18:00  18:10  -       18:40  19:15

  - temporada: invierno
    dias: lunes-viernes
    tabla: |
      COR    CVH    VHA     ALC    POZ    PZH    VVC     CON
      20:00  20:30  20:35D  21:00  21:10  21:15  21:45C  -

pendientes: [P02, P10, P12]        # preguntas abiertas que afectan a esta línea
```

Reglas del formato:

- **Tabla**: la primera fila son códigos de parada (al menos 2, sin repetir);
  cada fila siguiente es un viaje con un valor por parada. `-` significa que no
  para. **El sentido se deduce del orden de las columnas.** Las líneas que
  empiezan por `#` son comentarios.
- **Hora**: `HH:MM` seguida opcionalmente de letras de observación de ámbito
  parada (`06:25D`, `16:35DP`). Cada viaje tiene al menos 2 horas y **las horas
  no retroceden** (no se admite cruzar la medianoche; no hay ningún caso).
- **Llegada y salida distintas** (P21): `HH:MM>HH:MM[LETRAS]`, p. ej.
  `11:55>12:30P`. Es la llegada y luego la salida de la misma parada, y solo
  vale en una parada **intermedia** (ni en la primera ni en la última celda con
  hora del viaje). Con la llegada igual que la salida se escribe una sola hora;
  la salida no puede ser anterior a la llegada. "Las horas no retroceden"
  compara la salida de una parada con la llegada de la siguiente, y la llegada
  con la salida de la misma parada. Se usa `>` y no `/` (que se leería "una u
  otra") ni `-` (que significa "no para").
- **Mismo autobús** (`bus:<id>`, T-1/D-o): un token tras el `|`, con el id en
  minúsculas, cifras y guiones (`| bus:cor-1030`). Todos los viajes que llevan
  el mismo id son **un único autobús físico** que negocio o el Excel han
  confirmado; se declara solo donde hay esa confirmación, nunca por parecido.
  El validador exige que lo declarado cuadre (ver Comprobaciones). Puede ir
  junto a observaciones de viaje y `Pnn`: `| bus:cor-1030 pasa_por_rivero P21`.
- **Observaciones de viaje y pendientes** tras `|` al final de la fila:
  `06:15 06:35 06:50 07:30 | pasa_por_rivero P21`. Los tokens `Pnn` son
  referencias a preguntas abiertas.
- **Clases de día**: `lunes`...`domingo` y `festivos`. Claves admitidas en
  `dias` y en las tablas: los días sueltos, `lunes-viernes`, `lunes-jueves`,
  `martes-viernes`, `sabados-domingos`, `domingos-festivos`,
  `sabados-domingos-festivos`. En `dias`, cada temporada cubre las 8 clases
  **exactamente una vez**, con uno de tres estados:
  - `horario`: hay al menos una tabla que la cubre.
  - `sin_servicio`: el horario dice expresamente que no hay autobús.
  - `sin_datos`: no lo sabemos (por ejemplo, el horario de una temporada que
    negocio aún no ha enviado). **El bot nunca lo trata como "sin servicio"**
    (4.8). Peñarroya y Los Blázquez ya no son un ejemplo: P01 se respondió "el
    mismo que en invierno, vale todo el año", así que son anuales.
- Una tabla puede usar una clave más amplia que las de `dias` (la vuelta de
  Badajoz es `lunes-viernes` aunque `dias` declare `lunes-jueves` y `viernes`),
  siempre que todas sus clases tengan estado `horario`.
- **Temporadas**: rangos `DD/MM - DD/MM` (pueden cruzar el año) o
  `todo el año`. Todo día del año, incluido el 29/02, cae en exactamente una.
  El año no se guarda (D-a).

#### Comprobaciones

| Error: detiene la validación | Aviso: sale en el informe |
|---|---|
| YAML mal formado, campo desconocido u obligatorio ausente | Posible mismo autobús con horas distintas, entre pares **no declarados** (heurística, ver abajo; no se fusionará) |
| Código de parada, letra u observación sin definir | Clases de día en `sin_datos` |
| Observación usada en un ámbito no permitido | Pendientes abiertos, con su número |
| Condición que el motor no sabe aplicar | Paradas o localidades definidas que ninguna línea usa |
| Fila con un número de valores distinto al de paradas | |
| Horas que retroceden (salida anterior frente a llegada siguiente, o llegada frente a la salida de la misma parada) o viaje con menos de 2 horas | |
| `>` en la primera o la última celda con hora; salida anterior a la llegada; la misma hora dos veces (`11:55>11:55`) | |
| `bus:` con identificador mal formado o más de un `bus:` en la misma fila | |
| `bus:X` en un solo viaje (errata en el id) | |
| `bus:X`: un viaje sin ningún día en común con el resto del grupo, o dos viajes de la **misma línea** con días solapados | |
| `bus:X`: viajes que comparten menos de 2 localidades | |
| `bus:X`: horas distintas en una parada común (la llegada siempre; la salida solo si la parada no es la última de ninguno de los dos viajes) | |
| `bus:X`: paradas distintas dentro de una misma localidad (p. ej. `VRE` frente a `VRC`) | |
| Temporadas que se solapan o dejan días sin cubrir | |
| Clase de día sin declarar, declarada dos veces, o `horario` sin tabla | |
| `a_demanda` usada sin `telefono_demanda` en la línea | |
| Dos tablas de una línea con la misma temporada, días y extremos de cabecera | |
| Marcador `{xxx}` en el `texto` de una observación distinto de `{telefono}` | |
| Pendiente mal formado en `pendientes:` de `paradas.yaml` | Ambigüedades declaradas: un alias que comparten varias localidades o que coincide con el nombre de otra (`villafranca`) |
| Alias que no es texto, que queda vacío al normalizar o repetido en la misma localidad | |
| Dos localidades cuyo nombre normalizado coincide (ambigüedad no declarada) | |
| Localidad pendiente: `pendiente` sin `ver` (o al revés), `pendiente` mal formado o no listado en `pendientes:` de `paradas.yaml`, `minutos` ausente, no entero o fuera de 1-60, `aviso`/`ver`/`minutos` sin `pendiente` | Localidad pendiente (con su Pnn) |
| Localidad pendiente: `ver` sin definir, ella misma u otra pendiente; con paradas en `paradas:`; `aviso` sin definir, que no es tipo aviso o sin ámbito `viaje` | Localidad pendiente cuyo `aviso` no contiene sus `minutos` en el texto |
| `no_vendibles`: localidad sin definir, misma localidad dos veces o par repetido (también invertido) | `no_vendibles`: par que ninguna línea conecta |
| `calendario.yaml`, `sin_servicio_todas_las_lineas`: fecha `DD/MM` inválida (`31/02`), repetida o lista mal formada | `festivos_locales`: localidad que ninguna línea usa |
| `calendario.yaml`, `festivos_locales`: localidad sin definir, fecha fuera de `vigencia`, repetida en la localidad o ya presente en `festivos` | |

**Mismo autobús, heurística (solo aviso).** Para cada par de viajes de líneas
distintas que no declaran el mismo `bus:` se avisa si comparten 2 o más
localidades en el mismo orden, sus días se solapan (temporadas incluidas), llevan
la misma hora en la primera parada común y alguna otra parada común discrepa.
El aviso es «posible mismo autobús con horas distintas: … (no se fusionará)»,
una vez por par de líneas y parada discrepante. Los pares declarados con el
mismo `bus:` no se avisan (si discrepan es error). La fusión del motor sigue
siendo por horas idénticas; el aviso solo señala un posible descuido al editar
a mano. **"Tramo con tiempo anómalo" se descartó** (T-1): P22 era un error de
datos ya corregido, P23 y P25 son anomalías confirmadas por negocio y la
espera de P21 también saltaría, así que serían falsos avisos permanentes; esa
comprobación la hace la revisión del PDF.

El parser y el validador son **un único módulo** (`app/services/horarios/formato.py`)
que usan `make validar`, los tests y el loader al arrancar el bot.

#### Herramientas

| Comando | Qué hace |
|---|---|
| `make validar` | Valida todo `horarios/` y lista errores y avisos |
| `make formatear` | Realinea las columnas de todas las tablas. No cambia ningún dato |
| `make revision` | Genera `revision/horarios.html` y `revision/horarios.pdf` (ver abajo) |
| `make publicar` | Crea el tag `horarios-AAAA-MM-DD` y despliega (fase 5) |

**Vista de revisión para negocio** (HTML y PDF A4 apaisado, del mismo HTML):

1. Portada: fecha, versión, número de líneas y viajes, pendientes abiertos.
2. **Cambios desde la versión publicada** (el último tag `horarios-*`), en
   lenguaje de negocio: *"Pozoblanco – Córdoba, invierno, lunes a viernes,
   hacia Córdoba: la salida de las 10:00 pasa a las 10:05"*. Si no hay versión
   publicada, pone "primera versión".
3. Una sección por línea: temporadas en palabras ("del 15 de septiembre al 22
   de junio"), un cuadro de qué días hay servicio, sin servicio o sin datos,
   las tablas con nombres de parada completos y `—` donde no para, y bajo cada
   tabla la leyenda con **el texto literal que dirá el bot**. Lo pendiente,
   resaltado con su número.
4. Anexo con las preguntas pendientes.

`revision/` no se versiona: se regenera desde cualquier versión.

#### Ciclo de actualización

Negocio comunica un cambio → se edita la fila en `horarios/lineas/...` →
`make validar` → `make revision` → se envía el PDF (con la sección de cambios)
→ negocio confirma → commit → `make publicar`. Si algo sale mal, se vuelve al
tag anterior.

**Cambios con fecha futura** ("desde el 1 de noviembre..."): no se modelan en
la v1. Se publican el día que entran en vigor. Si se vuelve habitual, se añade
un campo de vigencia por viaje.

#### `calendario.yaml`

```yaml
vigencia: 01/01/2026 - 31/08/2027   # fechas con año real (a diferencia de las
                                     # temporadas de línea, que no lo llevan)

festivos:
  01/01/2026: Año Nuevo
  25/12/2026: Navidad

curso:
  inicio_clases: 10/09/2026
  fin_clases: 22/06/2027
  vacaciones:
    - 23/12/2026 - 07/01/2027       # Navidad
    - 22/03/2027 - 28/03/2027       # Semana Santa
  no_lectivos: [26/02/2027]

sin_servicio_todas_las_lineas: [25/12, 01/01]   # DD/MM, todos los años (P03g)

festivos_locales:                  # por localidad, no por municipio suelto (P03e)
  cordoba:
    08/09/2026: Virgen de la Fuensanta
    24/10/2026: San Rafael

pendientes: [P28]
```

- Validado por `formato.py`, como el resto de `horarios/`: campo desconocido
  u obligatorio ausente, fecha inválida, rango invertido (`vigencia` o un
  tramo de `vacaciones`), festivo duplicado, festivo o fecha de `curso` fuera
  de `vigencia`, `inicio_clases` posterior a `fin_clases` y pendiente mal
  formado son todos errores concretos, nunca avisos.
- **`sin_servicio_todas_las_lineas`** (opcional, lista `DD/MM`, sin año: vale
  para todos los años; 29/02 admitido, 31/02 no). Son días sin servicio en
  ninguna línea (P03g: 25/12 y 01/01). Ambas fechas siguen en `festivos:`
  para conservar el nombre del festivo. Fecha inválida, repetida, lista mal
  formada o campo desconocido son errores.
- **`festivos_locales`** (opcional, mapa `localidad -> {DD/MM/AAAA: nombre}`;
  P03e). Una línea aplica los festivos locales de una localidad si alguno de
  sus viajes tiene una parada en ella (se deduce de las paradas, no se
  declara: `loader.calcular_festivos_por_linea`). Errores: localidad sin
  definir, fecha fuera de `vigencia`, fecha repetida en la localidad o ya
  presente en `festivos`. Aviso: localidad que ninguna línea usa. El festivo
  local solo cambia la clase de día de **esa línea** (`festivos`);
  `InfoDia` y `es_lectivo` no cambian (P04). Córdoba 2026: Resolución de
  6/10/2025 de la Dirección General de Trabajo, Seguridad y Salud Laboral
  (BOJA n.º 197, 14/10/2025). Los de 2027 quedan pendientes de la resolución
  de 2027 y caerían después de `vigencia_fin`.
- **Un festivo siempre gana sobre el día de la semana** (decisión 1): un
  festivo en sábado usa la clase de día `festivos`, no `sabado`.
- `calendario.py` (fase 2) es lógica pura sobre este objeto ya validado: no
  vuelve a parsear YAML ni lee el reloj salvo en `hoy()`/`ahora()`, pensadas
  para quien las llame en fases posteriores, no para uso interno del motor.
- **`vigencia_fin` no puede ir más allá de lo que realmente se conoce del
  curso escolar.** Durante la implementación de la fase 2 se ensanchó
  `vigencia_fin` de 31/08/2027 a 31/12/2027 para que cupieran 5 festivos de
  2027 pedidos por esta RDS (12/10, 01/11, 06/12, 08/12 y 25/12/2027), que de
  otro modo habrían caído fuera de vigencia y `formato.py` los habría
  rechazado. Ese ensanchamiento fue un error: daba por buenos festivos de
  después del fin del curso cargado (fin_clases 22/06/2027) sin tener el
  calendario escolar 2027-28, una suposición no verificada — pese a llevar en
  el código una nota de "confirmado por negocio" que no era cierta. Corregido
  el 2026-09-27: `vigencia_fin` vuelve a 31/08/2027 y los 5 festivos
  afectados quedan comentados en `calendario.yaml` con una nota, hasta que se
  cargue el curso 2027-28 y se pueda ampliar la vigencia con base cierta.

#### Decisiones provisionales de la fase 2 (P03, P04)

| # | Decisión | Pendiente |
|---|---|---|
| 1 | Un festivo siempre determina la clase de día (`festivos`), sea cual sea el día de la semana en que caiga. | — |
| 1b | Los festivos locales se declaran por localidad en `festivos_locales` (hoy, Córdoba 2026) y cada línea aplica los de las localidades por las que pasa, como clase de día `festivos` solo para esa línea (P03e, ciclo B). | — |
| 1c | Los festivos locales de 2027 esperan a la resolución de 2027, que caerían después de `vigencia_fin` (31/08/2027); se añadirán al ampliar la vigencia con el curso 2027-28. | — |
| 2 | El periodo lectivo usa el calendario escolar de Córdoba 2026-27 tal como está publicado, sin margen de confirmación de negocio sobre las fechas exactas. | P04 |
| 3 | Los días sueltos no lectivos (p.ej. 26/02/2027) se declaran en `no_lectivos`, no como una `vacacion` de un solo día. | P04 |
| 4 | Si una línea tiene `sin_datos` para una fecha pero otra línea sí cubre ese mismo par con `horario`, el resultado muestra las salidas de la que sí sabe, más el aviso de que otra línea no tiene datos ese día. Si solo la línea `sin_datos` cubre el par, el resultado es `sin_datos`, nunca `sin_servicio`. | — |
| 5 | Los días sin servicio en ninguna línea (25/12 y 01/01) se declaran en `DD/MM`, fuera de `festivos`, y tienen prioridad sobre `sin_datos` y sobre la vigencia: son un hecho conocido aunque el calendario no llegue a esa fecha. Orden: `no_vendible` → `sin_trayecto` → sin servicio general → vigencia (`sin_datos`) → líneas. | P03g; abierto P28 |
| 6 | Los festivos locales se agrupan por localidad y la línea afectada se deduce de sus paradas (una línea que pasa por Córdoba aplica los de Córdoba), no se listan por línea. | P03e |
| 7 | `no_vendible` es un estado propio del motor, con un único filtro (`query.es_no_vendible`) que usan `consultar` y `destinos_desde`; la conversación nunca lo trata como `sin_trayecto`. | P12b |

### 2.4 Modelo de datos en memoria

El loader convierte `horarios/` en objetos inmutables:

| Entidad | Contenido |
|---|---|
| `Zona` | Id y nombre |
| `Localidad` | Lo que elige el usuario: id, nombre, zona, alias y, solo en las pendientes (P15/P32), `pendiente`, `ver`, `minutos` y `aviso` (opcionales, `None` por defecto) |
| `Parada` | Parada física: código, nombre público, localidad |
| `Observacion` | Id, letra, tipo (condición/aviso), ámbitos, texto |
| `Linea` | Id, nombre, teléfono a demanda, avisos, meses sin servicio, temporadas, estado de cada clase de día por temporada, pendientes |
| `Temporada` | Nombre y rangos día/mes |
| `Tabla` | Línea, temporada, clave de días y **la lista ordenada de paradas de su cabecera**. Conserva el sentido y el orden de columnas tal como se escribieron; la vista de revisión pinta una tabla por `Tabla`, nunca mezcla tablas |
| `Viaje` | La tabla a la que pertenece (y, por ella, línea, temporada y días), observaciones de viaje, pendientes, la lista ordenada de pasos y `bus` (id del mismo autobús declarado, o `None`) |
| `Paso` | Parada, `llegada`, `salida` y observaciones de parada. En una celda simple `llegada == salida`; con `HH:MM>HH:MM` son distintas (P21). No hay campo `hora` |

Puntos clave:

- **El usuario elige una localidad; el resultado muestra la parada.**
  Pozoblanco tiene varias paradas (pueblo, hospital, estación; P10) y hacer
  elegir entre ellas es confuso. **Cuidado:** Villaharta y Cruce de Villaharta
  **no** son el mismo sitio (P14) y no se fusionan.
- **Las condiciones son datos con ámbito**: una condición de parada solo
  afecta a los pares que usan esa parada. El Córdoba 15:30 de Belalcázar sale
  todos los días; solo su llegada a Cabeza del Buey es "solo viernes lectivo".
- Se inspira en GTFS (servicio separado del calendario, parada a demanda,
  hora aproximada) sin adoptarlo. Exportar a GTFS más adelante sería un
  script sobre este modelo.

---

## 3. El motor de consulta

Entrada: `(localidad_origen, localidad_destino, fecha)`.
Salida: lista ordenada de salidas, cada una con hora de salida, hora de
llegada, duración, parada concreta y notas. La hora de salida es la **salida**
del `Paso` del origen y la de llegada es la **llegada** del `Paso` del destino
(P21: Córdoba→Peñarroya 10:30→11:55, Peñarroya→Los Blázquez 12:30→13:20 y
Córdoba→Los Blázquez una sola salida 10:30→13:20).

Pasos:

0. **Casos previos, en este orden:** el par es **no vendible** (P12b, 2.3) →
   `no_vendible`, sin salidas ni "siguiente día"; ninguna línea conecta el
   par → `sin_trayecto`; la fecha es un día **sin servicio en ninguna línea**
   (P03g) → `sin_servicio` (con `sin_servicio_general`), aunque caiga fuera de
   la vigencia; la fecha está fuera de la vigencia → `sin_datos`.
1. **Resolver el calendario de esa fecha:** temporada vigente **para esa línea**
   (cada línea tiene sus fechas), tipo de día **de esa línea** (laborable /
   sábado / domingo y festivos; un festivo local vuelve `festivos` la clase
   solo de las líneas que lo aplican, P03e) y banderas (`es_festivo`,
   `es_lectivo`, `mes`).
2. **Filtrar servicios** cuya línea, temporada y tipo de día encajen, y cuyas
   condiciones se cumplan (descartar Cardeña-Pozoblanco en agosto, etc.).
3. **Buscar el par:** el servicio debe parar en una parada del origen y, *más
   adelante en su orden de paradas*, en una del destino. El orden es lo que
   determina el sentido; no hace falta una columna de sentido para esto.
4. **Fusionar el mismo autobús**: si dos viajes de líneas distintas tienen la
   misma hora de salida y de llegada (y las mismas paradas de origen y destino)
   para el par consultado, se muestran una sola vez, con las líneas y las notas
   de ambos (decisión D-o). La fusión es siempre por horas idénticas del par
   consultado; `bus:` no la cambia, porque el validador ya garantiza que lo
   declarado es idéntico. Las salidas pasadas de hoy (paso 6) se deciden con la
   **salida** del origen.
5. **Ordenar por hora de salida** y anotar las condiciones que aplican.
6. **Si la fecha es hoy**, marcar o retirar las salidas ya pasadas.
7. **Si alguna línea implicada tiene `sin_datos` para ese día**, el resultado
   lo dice en lugar de dar a entender que no hay servicio (2.3 y 4.8).

Todo en memoria, sin E/S. El coste es despreciable frente a los ~0,5 s que
costaba una consulta a Google Calendar en Peluquería.

### Reglas de calendario

- **Festivos:** BOJA — [Decreto 101/2025](https://www.juntadeandalucia.es/organismos/empleoempresaytrabajoautonomo/areas/relaciones-laborales/calendario-fiestas.html)
  para 2026 y [Decreto 84/2026](https://www.juntadeandalucia.es/boja/2026/84/1.html)
  para 2027, más los festivos locales de las localidades que declara
  `festivos_locales` (hoy, los de Córdoba: 08/09 y 24/10/2026), que aplica
  cada línea que pasa por esa localidad. Se cargan a mano en
  `horarios/calendario.yaml`, una vez al año. El 25/12 y el 01/01 no hay
  servicio en ninguna línea (P03g). Los días con horario especial
  (Nochebuena, Nochevieja, Semana Santa, feria) siguen abiertos (P28): hoy no
  hay ningún día especial. Ver duda D3, P03 y P28.
- **Periodo escolar:** calendario escolar de Córdoba 2026-27 — curso del
  10/09/2026 al 22/06/2027, vacaciones de Navidad del 23/12/2026 al
  07/01/2027, Semana Santa del 22 al 28/03/2027, y el 26/02/2027 como día no
  lectivo suelto.
- **Temporadas:** cada línea declara sus rangos día/mes en su fichero de
  `horarios/lineas/`, y el validador exige que cubran el año sin huecos ni
  solapes (2.3). El fin del verano está pendiente de negocio (P02).

---

## 4. La conversación

Límites reales de la WhatsApp Cloud API, ya documentados en
`app/utils/interactive.py` de Peluquería:

- **Lista:** máximo **10 filas en total** (sumando todas las secciones), título
  de fila 24 caracteres, descripción 72.
- **Botones:** máximo **3**, texto de 20 caracteres.
- **Texto:** 4096 caracteres.

### 4.1 Flujo

```
                    ┌─────────────┐
                    │    MENÚ     │  [🚌 Horarios] [ℹ️ Información]
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │   ORIGEN    │  lista: 8 pueblos + ✍️ otro + ↩️ menú
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │   DESTINO   │  lista filtrada por el origen elegido
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │     DÍA     │  lista: 7 días con nº de salidas + otra fecha
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │  RESULTADO  │  [📅 Otro día] [🔄 Ver la vuelta] [🔍 Otra consulta]
                    └─────────────┘
```

Estados de la máquina: `MENU → SEL_ORIGEN → SEL_DESTINO → SEL_DIA → RESULTADO`,
más `ESCRIBIR_ORIGEN`, `ESCRIBIR_DESTINO`, `ESCRIBIR_FECHA` y `CONFIRMAR_PUEBLO`
para las ramas de texto libre. Mismo patrón que `conversation.py` de Peluquería.

### 4.2 Paso 1 — Menú

```
🚌 Autocares · Horarios
¿Qué necesitas?
          [🚌 Ver horarios]  [ℹ️ Teléfono y contacto]
```

### 4.3 Paso 2 — Origen

```
🚌 Horarios de autobús
¿Desde qué pueblo sales?
                                      [ Ver pueblos ▾ ]
  Córdoba                  Pozoblanco
  Peñarroya-Pueblonuevo    Villanueva de Córdoba
  Posadas                  Almodóvar del Río
  Hinojosa del Duque       Hornachuelos
  ✍️ Otro pueblo
  ↩️ Volver al menú
```

8 pueblos + 2 filas de servicio = **10 filas exactas**, el máximo.

**El orden de esos 8 lo decide la empresa**, que sabe dónde vende billetes. El
ranking por número de servicios del Excel no sirve tal cual: sobrevalora
paradas de carretera como Cruce de Villaharta (61 servicios) o El Vacar (37),
por las que pasan todos los buses y no sube casi nadie. Ver duda D7.

El usuario puede escribir en cualquier momento sin pulsar "✍️ Otro pueblo".

### 4.4 Paso 3 — Destino

Ya se conoce el origen, así que **solo se ofrecen destinos que existen**.

```
🚌 Desde Pozoblanco
¿A dónde vas?
                                      [ Ver destinos ▾ ]
  Córdoba                  Alcaracejos
  Villanueva de Córdoba    Villaharta
  Conquista                Cruce de Villaharta
  Pozoblanco (hospital)    …
  ✍️ Otro destino
  ↩️ Cambiar origen
```

- **Los destinos no vendibles no se ofrecen** (P12b): `destinos_desde` los
  filtra (Córdoba no ofrece Alcolea ni Campus de Rabanales, y viceversa). Si
  el usuario escribe uno, el bot dice "Entre {origen} y {destino} no vendemos
  billetes, en ninguno de los dos sentidos. Puedes elegir otro destino." y
  no el "No hay trayecto directo" de un par sin línea; sin recomendaciones.
- Córdoba siempre primero (la alcanzan 53 de 63 paradas).
- **Para los 31 orígenes con ≤9 destinos la lista es completa**: no hace falta
  la fila de escribir, y lo que no está, no existe. Cero ambigüedad.
- Para el resto, los 8 destinos más relevantes + `✍️ Otro destino`.

### 4.5 Paso 4 — Día

La mejor idea del diseño: **como ya se conocen origen y destino, cada día puede
mostrar cuántas salidas tiene**. El usuario nunca elige a ciegas un día sin
servicio, y calcularlo es gratis porque los datos están en memoria.

```
🚌 Pozoblanco → Córdoba
¿Qué día viajas?
                                      [ Ver días ▾ ]
  Hoy · mié 23/09          5 salidas · próxima 15:15
  Mañana · jue 24/09       5 salidas · de 06:55 a 18:00
  Vie 25/09                5 salidas · de 06:55 a 18:00
  Sáb 26/09                sin servicio
  Dom 27/09                sin servicio
  Lun 28/09                1 salida · 08:00
  Mar 29/09                5 salidas · de 06:55 a 18:00
  📅 Otra fecha
```

8 filas (`app/handlers/flujo.py`, `_descripcion_dia`, corregido en la
revisión del 2026-09-27 — `docs/rds_fase4_correcciones.md`). Reglas, en este
orden, con el prefijo `festivo · ` cuando `info_dia.es_festivo` o el día es
festivo local para alguna línea del par (`festivo_local`):

| Consulta | Descripción |
|---|---|
| `con_salidas`, hoy, quedan salidas | `N salidas · próxima HH:MM` |
| `con_salidas`, hoy, ninguna pendiente | `ya no quedan salidas hoy` |
| `con_salidas`, otro día, N ≥ 2 | `N salidas · de HH:MM a HH:MM` |
| `con_salidas`, otro día, N = 1 | `1 salida · HH:MM` (singular) |
| cualquiera de las anteriores, si alguna línea de ese par no tiene datos ese día (`lineas_sin_datos`) | + ` · puede haber más` |
| `sin_servicio` (también el día sin servicio en ninguna línea, P03g) | `sin servicio` |
| `sin_datos` | `horario no disponible` (nunca "sin servicio": son estados distintos, 2.3 y 4.8) |

Un día sin servicio (en una línea como Ochavillos, sábado y domingo saldrían
así de entrada) aparece como `sin servicio`. Un festivo con 3 salidas sale
como `festivo · 3 salidas · de HH:MM a HH:MM`.

**No se pregunta el tipo de día** (laborable / sábado / festivo): a veces ni el
cliente sabe si el jueves es festivo. Se elige **una fecha real** y el bot
deduce el tipo de día, la temporada, el viernes lectivo y las excepciones.

**`📅 Otra fecha` usa un formato cerrado** (decidido el 2026-09-27, fase 3).
Al pulsarla, el bot dice exactamente cómo escribir la fecha:

```
📅 Escribe la fecha así: día/mes
Por ejemplo: 25/12
```

Solo se acepta **día y mes en números, en ese orden**, con año opcional. Se
toleran variaciones de escritura, nunca de contenido:

| Escribe | Entiende |
|---|---|
| `25/12`, `25-12`, `25.12`, `25 12`, ` 25 / 12 ` | 25 de diciembre |
| `5/1`, `05/01` | 5 de enero |
| `25/12/2026`, `25/12/26` | con año explícito (2 cifras = 20xx) |

No se interpreta lenguaje natural: `mañana`, `el viernes`, `25 de diciembre`
o `por la mañana` se rechazan igual que una fecha imposible (`31/02`,
`12/25`), repitiendo el formato: "No he entendido la fecha. Escríbela así:
día/mes, por ejemplo 25/12". Los próximos 7 días ya están en la lista con su
fecha; `Otra fecha` es para días más lejanos, y un único formato elimina
ambigüedades como "el viernes que viene" (¿este viernes o el de la semana
siguiente?).

**Año cuando no se escribe:** se miran la última vez que ese día/mes ya pasó
y la próxima vez que llega (hoy incluido).
- Si la última vez fue hace **30 días o menos** (`20/09` escrito el 27/09, o
  `28/12` escrito el 05/01): "Esa fecha ya ha pasado". Casi seguro es un
  error del cliente, no una fecha de dentro de un año.
- Si no, la próxima vez que llega (`3/1` escrito el 27/09 → 03/01 del año
  siguiente; `27/09` escrito el 27/09 → hoy).
- `29/02`: igual, contando solo años bisiestos (hoy, 29/02/2028, fuera del
  calendario cargado → `sin_datos`).

Con año explícito y fecha ya pasada: "Esa fecha ya ha pasado". Una fecha
válida pero fuera de la vigencia de `calendario.yaml` no es asunto del lector
de fechas: el motor responde `sin_datos`.

Si el cliente escribe en la lista de días sin pulsar `Otra fecha`, se usa el
mismo lector: una fecha válida se acepta; si no, se le recuerda que elija de
la lista o pulse `Otra fecha` (fase 4).

### 4.6 Paso 5 — Resultado

```
🚌 Pozoblanco → Córdoba
📅 Miércoles 23/09 · horario de invierno

06:55 → 08:15    (1h 20)
08:15 → 09:30    (1h 15)
10:00 → 11:25    (1h 25)
15:15 → 16:30    (1h 15)
18:00 → 19:15    (1h 15)

📍 Salidas desde: Pozoblanco (estación)
💶 Precio: — €

[📅 Otro día]  [🔄 Ver la vuelta]  [🔍 Otra consulta]
```

Los horarios del ejemplo son los reales de la hoja `POZOB INV`, lunes a
viernes. El precio queda como hueco hasta tener los datos (duda D8): la fase
4 no añade ninguna línea de precio; se implementa en la fase 7.

**Formato de notas implementado en la fase 4** (`app/utils/messages.py`):
una nota de observación que se repite en TODAS las salidas listadas de la
respuesta sale como una única línea `⚠️` sin número, al final; una nota que
solo afecta a algunas sale con una marca numérica (¹, ², ³...) asignada por
orden de primera aparición entre las salidas listadas, y esa misma marca se
repite junto a la hora de cada salida afectada. Las salidas ya pasadas (hoy)
no se listan ni participan en la numeración; su recuento sale en
`(hoy ya han salido N)`. Si el texto superaría 4096 caracteres, se corta en
la última salida completa que entre y se añade
"…y N salidas más, llama al <teléfono>".

**Cabecera de día especial.** Un festivo general sale `festivo (Navidad)`; un
festivo local sale `festivo en Córdoba (Virgen de la Fuensanta)`; si coinciden
gana el general. En el 25/12 y el 01/01 el resultado dice "El 25/12 no hay
servicio en ninguna línea", añade el siguiente día con salidas si se puede
calcular, y da el teléfono con el horario de oficina; si el día cae fuera de
la vigencia y no hay siguiente, da solo el hecho y el teléfono, nunca "no hay
salidas en los próximos días". El horario de oficina se muestra **por días**
(`config.yaml`, `negocio.horario_oficina`, P19c), por ejemplo "lunes a
miércoles laborables de 08:00 a 15:00 y de 17:00 a 19:00; jueves y viernes
laborables de 08:00 a 15:00": solo para mostrar, el bot nunca calcula si la
oficina está abierta. Un par no vendible da el mensaje de 4.4, con un único
botón `Otra consulta` si llegara a mostrarse como resultado.

Los tres botones cubren lo que de verdad se repite: mismo trayecto otro día,
el viaje de vuelta, y empezar de cero. `Otra consulta` va directo al paso de
origen, sin pasar por el menú.

### 4.7 Reglas de coincidencia de texto

**El bot nunca adivina en silencio.** O hay una coincidencia única, o pregunta.
Todas las ramas, sin excepciones:

| Entrada del usuario | Acción |
|---|---|
| Coincide exacto con nombre o alias | Continúa |
| Es prefijo único (`pozo`, `hornach`) | Continúa |
| Coincide con 2-3 | Botones para elegir |
| Coincide con 4-9 | Lista para elegir |
| Coincide con más de 9 | "Sé más concreto" + repregunta |
| Errata única (`pozoblnco`) | **Confirma**: "¿Pozoblanco?" [Sí] [No] |
| Sin coincidencia | "No conozco ese pueblo" + lista habitual + `Ver todos por zona` |

Reglas precisas (decididas el 2026-09-27, fase 3):

- **Orden de evaluación: exacto → prefijo → errata.** La primera regla que
  encuentra algo decide; un exacto gana siempre a los prefijos (`adamuz` es
  Adamuz aunque otro nombre empezara igual).
- **Qué se compara.** Nombres de localidad y sus alias (exacto y prefijo) y
  nombres de parada (solo exacto: "Pozoblanco (Hospital)" lleva a
  Pozoblanco). Cada clave apunta a un **conjunto** de localidades: un alias
  compartido (`villafranca`) da 2 candidatas y se pregunta.
- **Prefijo del nombre entero**, no de cualquier palabra: `cordoba` no
  coincide con "Villanueva de Córdoba". `pueblonuevo` u `obejuna` solo se
  reconocerán cuando haya alias (P13); hoy no se añaden.
- **Localidades pendientes** (P15/P32) se buscan igual que las demás
  (exacto, prefijo, errata, candidatas). Al elegirse una, la conversación no
  continúa con ella: muestra "Algunos autobuses paran en X, a unos N minutos
  de Y, pero aún no tenemos su hora de paso." con los botones `Usar Y` y
  `Otro pueblo` (4.8). El matcher no cambia.
- **Mínimo 3 letras** (tras normalizar) para prefijo y errata. Por debajo,
  solo cuenta un exacto; si no, `sin coincidencia` (`z` no es Zafra).
- **Errata** (distancia de Damerau-Levenshtein contra el nombre o alias
  completo): **≤1 si la clave tiene 5 letras o menos, ≤2 si es más larga**.
  Si la errata queda cerca de una sola localidad, se confirma; si queda cerca
  de 2 o más (incluido `villafranka`), se ofrecen para elegir como cualquier
  coincidencia múltiple, **nunca** un "¿Villafranca de Córdoba?" de sí o no.
- **Tras [No] en una confirmación**, el bot pide que lo escriba de otra forma
  y ofrece `Ver todos por zona`.
- **Candidatas en orden alfabético.**
- **Se busca siempre entre todas las localidades**, también en el destino: si
  se buscara solo entre las alcanzables, `Mérida` desde Pozoblanco daría "no
  conozco ese pueblo" en vez de "sin trayecto directo" (4.8). Una localidad
  que ninguna línea usa se reconoce igual (la conversación dirá que no hay
  trayecto).
- **Dos pueblos en un mensaje** (`pozoblanco cordoba`) no se interpretan: es
  un texto no reconocido.
- **Textos no reconocidos** (localidad o fecha) se registran en el log con el
  texto normalizado y el paso (origen, destino, fecha), **nunca con el
  teléfono del cliente**. Sirven a la fase 8 para decidir qué alias faltan.

**Normalización previa:** minúsculas, sin tildes (`ñ` → `n`), sin puntuación
(el guion pasa a espacio), espacios colapsados, sin artículos (`el`, `la`,
`los`, `las`) ni `de`/`del` (`villanueva duque` = Villanueva del Duque). En
el texto del cliente se quita además el relleno inicial `desde`, `a`,
`hacia`, `para`, `voy a` (`desde pozoblanco`). Es **una sola función**, en
`formato.py`, compartida por el validador y el matcher. La tabla de alias vive
en `horarios/paradas.yaml` y recoge los nombres oficiales, las abreviaturas
habituales y los nombres coloquiales que aporte la empresa (P13).

**Caso que siempre pregunta:** `Villafranca` (de Córdoba o de los Barros).
Nunca se resuelve solo, ni escrito con errata.

**`Ver todos por zona`** es la red de seguridad para quien no sabe escribir el
nombre. 7 zonas: Los Pedroches, Guadiato, Vega del Guadalquivir, Adamuz,
Campiña, Extremadura, Córdoba. Las zonas grandes (Los Pedroches tiene 18
localidades en uso, en 3 páginas de 8+8+2; Guadiato 14, Extremadura 11) se
parten en varias listas con una fila "ver más". No es el camino principal, pero ningún usuario se queda sin salida.
Se muestran en el orden de `paradas.yaml`, **ocultando las zonas sin
localidades en uso** (hoy Campiña); dentro de cada zona, localidades en orden
alfabético y solo las que alguna línea usa. Zonas pendientes de negocio (P18).

### 4.8 Casos borde

| Caso | Respuesta |
|---|---|
| Día sin servicio | Dice cuál es el siguiente día con servicio y lo ofrece en un botón |
| 25/12 y 01/01 (sin servicio en ninguna línea, P03g) | "El 25/12 no hay servicio en ninguna línea" + teléfono con horario de oficina, y el siguiente día con salidas si existe |
| Trayecto no vendible (P12b) | "Entre X y Y no vendemos billetes, en ninguno de los dos sentidos. Puedes elegir otro destino." Nunca se ofrece como destino |
| Día sin datos (`sin_datos`) | Dice que no tiene ese horario y da el teléfono con horario de oficina. **Nunca lo presenta como "no hay servicio"** |
| Sin trayecto directo | Lo dice, enseña los destinos que sí existen desde ese origen y da el teléfono con horario de oficina. **No inventa trasbordos** |
| Origen = destino | "Elige un destino distinto" |
| Localidad pendiente como origen (P15/P32) | "Algunos autobuses paran en X, a unos N minutos de Y, pero aún no tenemos su hora de paso." con `Usar Y` y `Otro pueblo`. No se guarda como origen; `Usar Y` continúa con Y como origen |
| Localidad pendiente como destino | Igual; `Usar Y` continúa con Y como destino (origen ya elegido). Nunca "sin trayecto" |
| Localidad pendiente cuyo `ver` es el origen (o el destino ya elegido) | `Usar Y` cae en las reglas normales: "Elige un destino distinto" |
| `usar:<id>` manipulado (id desconocido o pendiente) | Repite el paso actual sin cambiar el estado y sin error |
| `no_vendibles` o `festivos_locales` que nombran una localidad pendiente | No se valida (sin efecto: la pendiente nunca llega al motor) |
| Fecha ya pasada (hace ≤30 días sin año, o con año) | "Esa fecha ya ha pasado" + repregunta (4.5) |
| Hoy sin salidas restantes | "Hoy ya no quedan salidas" + botón a mañana |
| Servicio a demanda | `⚠️ A demanda: llama 24 h laborables antes al 957 42 90 30` |
| Viernes lectivo | `⚠️ Solo viernes en periodo escolar` |
| Línea de Badajoz | `⚠️ Horarios de paso aproximados` |
| Audio, imagen, sticker | Responde pidiendo texto o botones (ya resuelto en el webhook de Peluquería) |
| Estado caducado (30 min) | Vuelve al menú |

---

## 5. Qué se reutiliza de Peluquería

### 5.1 Copiar casi tal cual

| Fichero origen | Cambios |
|---|---|
| `app/services/whatsapp.py` | Ninguno. Reintentos, backoff, 429, pooling y enmascarado de teléfono ya resueltos |
| `app/utils/rate_limiter.py` | Ninguno |
| `app/utils/dedup.py` | Ninguno |
| `app/utils/security.py` | Ninguno |
| `app/utils/metrics.py` | Ninguno |
| `app/handlers/webhook.py` | Solo cambia el import de `conversation`. HMAC, límite de 64 KB, validación de identificador, dedup, límites por IP y teléfono, semáforo de concurrencia: todo se queda |
| `app/main.py` | Cambiar `/health` (ver 6.3) y el título. El logging rotatorio y el manejador global de excepciones se quedan |
| `app/utils/interactive.py` | Los helpers `_trunc`, `_button`, `_row`, `_section`, `_interactive_buttons`, `_interactive_list` son genéricos. Los constructores concretos se reescriben |
| `watchdog.py` | Cambiar URL y claves de alerta. Las 5 comprobaciones (salud, RAM, disco, pico de errores, dominio público) valen igual |
| `Makefile` | Cambiar puerto, dominio y nombre de servicio. Toda la estructura de targets vale |
| `app/utils/admin.py` | Quitar la salud de Calendar, añadir la de datos cargados. `/status`, `/help`, `/logs`, `/restart` se quedan |

### 5.2 Adaptar

- **`app/handlers/conversation.py`** — se conserva la **arquitectura**: bloqueo
  por teléfono, `ConversationState` con caducidad a 30 min, `_get`/`_clear`,
  `clean_expired_states()`, despacho por estado, `_safe_fallback`, manejo de
  comandos de administrador. Cambia la máquina de estados entera.
- **`app/config.py`** — se conserva el patrón: constantes + carga y validación
  de `config.yaml` + `validate_config()` que falla al arrancar si falta algo.
  Cambia el contenido.
- **`app/utils/messages.py`** — mismo patrón (todos los textos en español en un
  solo módulo), contenido nuevo.
- **`app/services/scheduler.py`** — de 3 jobs se queda **1**: limpieza de
  estados cada 10 min. (Opcional: recarga diaria de datos, útil solo si algún
  día se despliegan horarios sin reiniciar; por defecto no.)

### 5.3 Descartar por completo

Todo `app/services/calendar/` (service, queries, mutations, engine, caches,
locks, client, repository), `app/utils/parser.py`, `app/utils/slots.py`, los
jobs de recordatorios y sincronización, `generar_qr.py` (salvo que se quiera QR
de captación) y las dependencias `google-api-python-client`, `google-auth`.

### 5.4 Módulos nuevos

```
app/services/horarios/
  modelo.py       # Entidades inmutables del punto 2.4
  formato.py      # Parser + validador de horarios/ (punto 2.3). Único para tools, tests y loader
  diff.py         # Diferencias entre dos versiones de horarios/, en lenguaje de negocio
  loader.py       # Carga horarios/ a memoria al arrancar usando formato.py
  query.py        # El motor del punto 3
  calendario.py   # Temporada, tipo de día, festivos, periodo escolar
app/utils/
  matcher.py      # Reglas de coincidencia de texto del punto 4.7
  fechas.py       # Lector de fechas en formato cerrado día/mes[/año] (punto 4.5)
tools/
  validar.py      # make validar
  formatear.py    # make formatear
  revision.py     # make revision: HTML + PDF para negocio
  migracion/      # Solo mientras dure la migración desde el Excel; se borra en la fase 1b
```

### 5.5 Mapa de módulos resultante

```
buscabus/
  config.yaml            # Negocio: teléfono, horario oficina, enlaces, pueblos del menú
  horarios/              # FUENTE DE VERDAD de los horarios, editada a mano (2.3)
  revision/              # HTML + PDF generados para negocio. No se versiona
  horarios_fuente/       # El Excel inicial, de uso único (se archiva tras la fase 1b)
  app/
    config.py  main.py
    handlers/    webhook.py  conversation.py
    services/    whatsapp.py  scheduler.py  horarios/
    utils/       interactive.py  messages.py  matcher.py  fechas.py
                 metrics.py  dedup.py  rate_limiter.py  security.py  admin.py
  tools/         validar.py  formatear.py  revision.py  migracion/
  tests/
  watchdog.py  Makefile  requirements.txt
```

### 5.6 Dependencias

Se quitan `google-api-python-client` y `google-auth`. En `requirements-dev.txt`
(no se instalan en la VM): `openpyxl` (solo para la migración; se quita tras la
fase 1b) y `weasyprint` (PDF de la vista de revisión; necesita Pango en el
sistema). Se mantiene el resto: fastapi, starlette, uvicorn,
python-dotenv, httpx, apscheduler, pyyaml, pytest, pytest-cov, psutil, ruff,
mypy. **Migrar `pytz` a `zoneinfo`** desde el principio: es código nuevo y no
arrastra la deuda de Peluquería.

---

## 6. Infraestructura

### 6.1 Máquina

**Misma VM que Peluquería** (`instance-peluqueria`, e2-micro de 1 GB,
us-east1-b, proyecto `peluqueria-dm-barber-shop`, IP 104.196.210.121).

Justificación: este bot es **más ligero** que el de la peluquería. No hay
llamadas externas por consulta (los horarios están en memoria), los datos
ocupan pocos MB y el uso estimado es de 15-100 consultas al día frente a los
picos de 20-30 usuarios simultáneos que ya soporta Peluquería.

- Antes de instalar, comprobar RAM libre con `free -m`.
- Una segunda VM **no sería gratis**: el nivel gratuito es una instancia por
  cuenta de facturación.
- **Contrapartida:** comparten destino. Un reinicio o un problema de la VM
  afecta a los dos bots.
- **Plan de salida:** si la empresa acaba dependiendo del bot en serio, mover
  a su propia VM y su propia cuenta de facturación. El diseño no lo impide.

### 6.2 Aislamiento respecto a Peluquería

Nada se comparte salvo la máquina:

| Recurso | Peluquería | Buscabus |
|---|---|---|
| Repositorio | `Peluqueria` | `buscabus` (nuevo, independiente) |
| Directorio en la VM | `~/app` | `~/buscabus` |
| Servicio systemd | el actual | `buscabus.service` |
| Puerto (solo 127.0.0.1) | 8000 | **8001** |
| Subdominio | `peluqueriabot.duckdns.org` | `buscabus.duckdns.org` (o el que se elija) |
| Certificado TLS | el suyo | el suyo (certbot, mismo método DNS-01) |
| Bloque nginx | el suyo | server block nuevo |
| Cron del watchdog | el suyo | entrada propia, cada 60 min |
| Número de WhatsApp | el suyo | **número nuevo y distinto** |

uvicorn sigue escuchando **solo en 127.0.0.1**, con nginx por delante
terminando TLS y pasando `X-Real-IP` y `X-Forwarded-For` (`--proxy-headers`
para que el límite por IP funcione).

### 6.3 Salud y vigilancia

`/health` ya no comprueba Google Calendar. Comprueba que los datos están
cargados y son coherentes:

```json
{
  "status": "ok",
  "datos": {"paradas": 63, "servicios": 236, "cargado": "2026-09-23T08:00:00"},
  "metrics": {...}
}
```

Devuelve 503 si los datos no están cargados o vienen vacíos. El watchdog
(mismas 5 comprobaciones) vigila esa URL con su propia clave de alerta.

### 6.4 Meta / WhatsApp

Lo verificado en la documentación de Meta (septiembre 2026):

- **Los límites de mensajes NO afectan a este bot.** Meta los define como
  *"el número máximo de usuarios únicos a los que se puede enviar mensajes
  **fuera de una ventana de atención al cliente** en 24 horas"*. Este bot solo
  responde a mensajes que inicia el usuario, siempre dentro de esa ventana. Los
  250 mensajes/día de una cuenta nueva sin verificar **no son un problema**.
- **Verificación de empresa:** necesaria para que el nombre visible ("Autocares
  San Sebastián") aparezca en lugar del número, y para levantar límites. Pide
  documentos legales en Meta Business Manager y tarda entre 2 y 5 días
  hábiles. **Hay que empezarlo pronto**, en paralelo al desarrollo.
- **Nombre visible:** mínimo 3 caracteres, coherente con la marca, y **no se
  aprueba sin una web activa**. La empresa tiene web, así que no debería haber
  problema.
- **Un número nuevo**, que no puede estar dado de alta en WhatsApp ni en
  WhatsApp Business app (habría que darlo de baja antes).
- **El portafolio de negocio debe ser de la empresa de autobuses**, no el de la
  peluquería: la verificación usa sus documentos y su nombre visible.
- **Token:** System User permanente, igual que en Peluquería.
- **`WHATSAPP_APP_SECRET` obligatorio** desde el primer día. En Peluquería, si
  falta solo se emite un aviso y la verificación HMAC queda desactivada; aquí
  debe fallar al arrancar.
- **Graph API:** `v23.0` como en Peluquería, configurable por
  `WHATSAPP_API_VERSION`. Caducará previsiblemente en 2027.

### 6.5 Variables de entorno

```ini
WHATSAPP_PHONE_NUMBER_ID=   # Obligatoria
WHATSAPP_ACCESS_TOKEN=      # Obligatoria — System User permanente
WHATSAPP_VERIFY_TOKEN=      # Obligatoria
WHATSAPP_APP_SECRET=        # Obligatoria (a diferencia de Peluquería)
WHATSAPP_API_VERSION=       # Opcional, por defecto v23.0
ADMIN_PHONE=                # Obligatoria — comandos de administrador
PUBLIC_DOMAIN=              # Obligatoria — subdominio sin https://
DUCKDNS_TOKEN=              # Obligatoria
LOG_LEVEL=INFO              # Opcional
LOG_FILE=                   # Opcional
```

Ya no hacen falta `GOOGLE_CALENDAR_ID` ni `GOOGLE_CREDENTIALS_PATH`.

---

## 7. Coste

**Cambio importante a 8 días vista.** Según la
[documentación oficial de Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages),
**desde el 1 de octubre de 2026** los mensajes de servicio dentro de la ventana
de 24 h pasan a cobrarse por mensaje: *"Meta will charge on a per-message basis
for service messages, consistent with how Meta charges for template messages."*
Hasta ahora eran gratis. **Esto afecta también al bot de la peluquería.**

Dos avisos sobre las cifras:

- La tarifa concreta de España, **~0,0166 €/mensaje**, procede de blogs de
  proveedores, no de la tarifa oficial. Meta dijo que publicaría las tarifas
  definitivas antes del 1 de septiembre de 2026: **hay que mirar la tarifa real
  de la cuenta antes de decidir nada**.
- La "franja de 1.000 mensajes gratis al mes" que circula por algunos blogs
  **no aparece en la documentación oficial**. Se descarta.

Con 4 mensajes salientes por consulta (origen, destino, día, resultado):

| Escenario | Consultas/día | Consultas/mes | Mensajes/mes | Coste aprox. |
|---|---|---|---|---|
| Bajo | 15 | ~450 | 1.800 | ~30 € |
| Medio | 45 | ~1.350 | 5.400 | ~90 € |
| Alto | 100 | ~3.000 | 12.000 | ~200 € |

El menú añade un 5.º mensaje a la primera consulta de cada conversación.

**Palancas de ahorro, si el coste aprieta:** fusionar el menú con la pregunta
de origen (−1 mensaje), recordar el pueblo del usuario (−1 para repetidores) y
aceptar "Pozoblanco a Córdoba" en un solo mensaje (−2). Las tres están
descartadas para la v1 pero se pueden activar después sin rehacer nada.

---

## 8. Fases de implementación

Cada fase termina con `pytest` en verde y `ruff` limpio. Se sigue el ciclo
planner → coder → reviewer del `CLAUDE.md`.

### Fase 0 · Esqueleto (0,5 día)
Repositorio nuevo, estructura de directorios, `requirements.txt`,
`pytest.ini`, `pyproject.toml`, `config.py` con carga y validación de YAML,
`main.py` mínimo con `/health`. Copiar los módulos del punto 5.1 que no
requieren cambios.
**Criterio:** el servidor arranca, `/health` responde, los tests pasan.

### Fase 1 · Formato de horarios, validador y vista de revisión (2-3 días) — cerrada el 2026-09-27
`horarios/` (formato de 2.3), `modelo.py`, `formato.py`, `diff.py`,
`tools/validar.py`, `tools/formatear.py`, `tools/revision.py` (HTML + PDF),
`Makefile` mínimo con `validar`, `formatear` y `revision`, y **5 líneas de
prueba** migradas del Excel con sus pendientes marcados: Ochavillos–Córdoba,
Pozoblanco–Córdoba, Belalcázar–Córdoba, Adamuz–Córdoba y Badajoz–Córdoba.
Juntas cubren una línea anual sin fin de semana, dos temporadas, a demanda, las
tres condiciones, varias paradas por localidad, Villaharta frente a su cruce y
las dos Villafrancas. Sustituye a `config_import.yaml` y `data/`.
**Criterio:** el validador rechaza con mensaje concreto cada error de la tabla
de 2.3; las 5 líneas validan sin errores; sus horas cuadran al 100 % con las
hojas del Excel (script de cuadre en `tools/migracion/`); `make revision`
genera HTML y PDF legibles con la sección de cambios; `formatear` es
idempotente y no altera datos.

### Fase 1b · Migración completa (cuando responda negocio)
Las 10 líneas restantes y las correcciones que salgan de P01-P27. Revisión de
todo el PDF con negocio. Después se borra `tools/migracion/`, se quita
`openpyxl` y se archiva el Excel. Puede ir en paralelo a las fases 2-4, que se
desarrollan con las 5 líneas de prueba.
**Criterio:** las 15 líneas validan; el cuadre de horas con el Excel es del
100 % salvo las correcciones documentadas; negocio aprueba el PDF.

**Avance (fase 1b-1, `docs/rds_fase1b1_siete_lineas.md`):** migradas 7 líneas
que caben en el formato actual: Fuente Carreteros – Córdoba, Villaviciosa –
Córdoba, Belalcázar – Pozoblanco y las 4 de la hoja TORR (Línea Torrecampo,
Santa Eufemia – Villaralto, Cardeña, Estación AVE Vva de Córdoba). El bot pasa
a 12 líneas; el cuadre con el Excel es del 100 % en las hojas nuevas y la
única discrepancia sigue siendo POZOB VER, fila 48.
**Faltan 3 líneas (fase 1b-2 / ciclo C):** Posadas/Hornachuelos (P15, P32,
P16), Peñarroya (P20, P21, P33) y Los
Blázquez (P21, D-e). P01 se respondió: ambas son anuales (P27 deja de
importar).

**Ciclo C1 (`docs/rds_cicloC_extensiones_modelo.md`):** hecho el modelo de
horas (`Paso.llegada`/`salida`, celda `HH:MM>HH:MM`), el mismo autobús
declarado (`bus:<id>`, errores y aviso heurístico; T-1 cerrado) y el ajuste de
`observaciones.yaml` (sin `entra_en_pueblo`). Ninguna línea real usa todavía
`>` ni `bus:`: es la fase 1b-2. Quedan C2 (localidades pendientes, P15/P32) y
C3 (pueblos por línea en lugar de zonas, P18); la fixture
`tests/fixtures/horarios_cicloC/` se migrará en C3. Dependen de preguntas abiertas de negocio y de T-1
(mismo autobús en dos líneas) y de las zonas por línea (P18).

### Correcciones de la fase 1 (revisión del 2026-09-26) — resueltas el 2026-09-27
Resueltas en un ciclo propio (`docs/rds_fase1_correcciones.md`). Verificado el
2026-09-27: 64 tests en verde, `ruff` limpio, `make validar` con 0 errores,
cuadre con el Excel al 100 %, `formatear` idempotente, PDF con una tabla por
sentido, Badajoz traspuesta sin cortes, y el diff da un solo mensaje al quitar
un viaje. Se conserva la lista como registro:

1. **Tablas mezcladas en la revisión.** `revision.py` junta en una sola tabla
   la ida y la vuelta de la misma temporada y días, y ordena las columnas por
   aparición. Resultado en Adamuz: Alcolea sale después de Córdoba y los
   viajes de vuelta se leen al revés. Causa: el modelo no tenía la entidad
   `Tabla` (ya añadida en 2.4). Hay que pintar una tabla por `Tabla` con sus
   columnas en el orden del fichero, incluidas las paradas sin ninguna hora.
2. **Tablas anchas cortadas en el PDF.** En Badajoz (20 paradas) se pierden en
   el PDF las columnas de Villagarcía en adelante: faltan datos en el
   documento que firma negocio. Hay que partir la tabla o trasponerla
   (paradas en filas) cuando no quepa. Ninguna columna puede quedar fuera.
3. **El diff empareja viajes por posición.** Al quitar el Adamuz 14:45 (L-V
   invierno), dice que se quita el de las 18:00 y que el de las 14:45 "pasa a
   las 18:00" en 4 paradas. Hay que emparejar por cercanía de horas, o tratar
   como alta y baja todo lo que no sea un cambio pequeño. Hace falta un test
   con este caso.
4. **`{telefono}` sin sustituir** en la leyenda de `a_demanda`. Debe salir el
   `telefono_demanda` de la línea.
5. **Los avisos de línea y `no_circula` no aparecen en la revisión.** El
   `hora_aproximada` de Badajoz no sale en ningún sitio.
6. **Los pendientes marcados solo en comentarios de `paradas.yaml`** (P12,
   P18) no llegan a la revisión. Hace falta un campo `pendientes:` en
   `paradas.yaml`, igual que en las líneas.
7. Menores:
   - El diff llama "salida" a la hora de llegada a la última parada.
   - P09 está marcado también en el domingo de invierno (Córdoba 14:30), pero
     la pregunta es solo sobre verano. Es inofensivo; se revisa cuando
     responda negocio.

### Fase 2 · Motor y calendario (2 días) — cerrada el 2026-09-27
`loader.py`, `calendario.py`, `query.py`, `horarios/calendario.yaml` del curso
2026-27.
**Criterio:** las pruebas doradas pasan; las condiciones especiales (agosto,
viernes lectivo, a demanda) se aplican; un día sin servicio devuelve el
siguiente con servicio.

Verificado el 2026-09-27: pruebas doradas contra `horarios/` real
(Pozoblanco-Córdoba, Ochavillos-Córdoba) en verde, `tests/fixtures/
horarios_motor/` cubre viernes lectivo (a nivel de viaje y de parada),
`no_circula`, `sin_datos` combinado con `horario` (decisión 4), fusión de
autobuses y `a_demanda` en origen frente a parada intermedia. `make validar`,
`formatear` y `revision` sin regresión sobre las 5 líneas de la fase 1.
`calendario.yaml` deja P03 y P04 abiertos, visibles como avisos en
`make validar`.

Corregido el 2026-09-27: se detectó y corrigió un ensanchamiento indebido de
`vigencia_fin` (31/08/2027 → 31/12/2027) hecho durante esta fase para que
cupieran festivos de después del curso cargado; ver "`vigencia_fin` no puede
ir más allá de lo que realmente se conoce del curso escolar" en la sección
2.3.

### Fase 3 · Coincidencia de texto (1 día) — cerrada el 2026-09-27
`matcher.py`, `fechas.py`, zonas, normalización compartida y validación de
alias en `formato.py`. Sin alias nuevos (P13 sigue abierta). RDS:
`docs/rds_fase3_matcher.md`.
**Criterio:** todas las ramas de la tabla 4.7 cubiertas por tests; `Villafranca`
siempre pregunta, también con errata; las erratas piden confirmación según la
longitud del nombre; `fechas.py` solo acepta el formato cerrado de 4.5.

Verificado el 2026-09-27: 158 tests en verde, `ruff` limpio, `make validar`
sin errores (con el aviso esperado de la ambigüedad declarada `villafranca`).
Probados contra `horarios/` real todos los ejemplos de 4.5 y 4.7, incluidos
mayúsculas, tildes, `ñ` y espacios sobrantes. Corregido en la revisión: el
relleno inicial (`desde`, `hacia`...) se quitaba antes de normalizar y fallaba
con puntuación (`¿desde pozoblanco?`); ahora se quita sobre el texto ya
normalizado. P13 (alias) y P18 (zonas) siguen abiertas: son datos y no
cambian el código.

### Fase 4 · Conversación (2-3 días) — cerrada el 2026-09-27
`conversation.py` (infraestructura), `flujo.py` (máquina de estados),
`interactive.py`, `messages.py`, `webhook.py`, `datos.py`, scheduler de
limpieza, comandos de administrador. RDS: `docs/rds_fase4_conversacion.md`.
**Criterio:** el flujo completo funciona con la API simulada; ninguna lista
supera 10 filas ni ningún botón 3; todos los casos borde de 4.8 cubiertos.

Verificado el 2026-09-27: 210 tests en verde, `ruff` limpio. Los 8 pueblos de
`pueblos_menu_inicio` (config.yaml) se verificaron contra `horarios/` real
antes de fijarlos: los 8 dan coincidencia `unico` en `Matcher.buscar()` y
tienen viajes en `horarios.localidad_viajes` (D7 sigue provisional: el orden
y la selección definitivos los tiene que confirmar la empresa). El precio
del resultado queda pendiente de la fase 7 (D8): no se añadió ninguna línea
de precio. `WHATSAPP_APP_SECRET` es obligatorio y `_verify_signature` falla
cerrado (403) si falta, al contrario que en Peluquería.

Cerrada el 2026-09-27, tras las correcciones de abajo: 258 tests en verde,
`ruff` limpio, `make validar` sin errores y cada caso de 4.8 con test de
conversación.

### Correcciones de la fase 4 (revisión del 2026-09-27) — resueltas el 2026-09-27
Resueltas en un ciclo propio (`docs/rds_fase4_correcciones.md`). La revisión
superficial de la fase 4 encontró que su criterio de cierre ("todos los
casos borde de 4.8 cubiertos") no se cumplía todavía: `test_conversation.py`
no tenía ningún caso de `sin_datos`, `sin_servicio`, a demanda, viernes
lectivo ni horas aproximadas; `test_webhook.py` tenía 8 tests frente a los
26 de Peluquería (faltaban límites por IP/teléfono, BSUID, payloads mal
formados); y `_descripcion_dia`, `_leer_fecha_libre` y el registro de textos
no reconocidos en `flujo.py` se desviaban en tres puntos pequeños de
`docs/rds_fase4_conversacion.md`. Verificado el 2026-09-27: 258 tests en
verde (70 en `test_conversation.py` + `test_webhook.py`, 38 y 32
respectivamente), `ruff` limpio, `test_query.py` sin regresión tras añadir
`linea-aproximada.yaml` a `tests/fixtures/horarios_motor/`. Se añadió el
fixture `datos_motor` (no autouse) en `tests/conftest.py`, se corrigió
`_descripcion_dia` para dar `próxima HH:MM` / `de HH:MM a HH:MM` / `1
salida` / `horario no disponible` / ` · puede haber más` (ver 4.5), se
redujo `_leer_fecha_libre` a un mensaje por paso, y se añadió
`_texto_para_log` (normaliza y sustituye por `<numero>` si hay 6 dígitos
o más en total, seguidos o no: más estricto que el RDS, aceptado en la
revisión porque protege mejor la privacidad) en los dos puntos de registro `[NO_RECONOCIDO]`. Queda sin
colapsar, documentado y aceptado, el camino de `Ver la vuelta` sin trayecto
de vuelta (`_handle_resultado`): manda un texto y después un interactivo del
menú, porque `build_menu()` no acepta un aviso en el cuerpo y esta
corrección no tocaba `interactive.py`.

### Fase 5 · Infraestructura (1 día)
`Makefile` adaptado, systemd en el puerto 8001, server block de nginx,
subdominio DuckDNS, certificado certbot, cron del watchdog.
**Criterio:** `make status` en verde, `/health` responde por el dominio
público, TLS válido, el watchdog alerta al admin.

### Fase 6 · Alta en Meta (en paralelo desde la fase 0)
Portafolio de negocio de la empresa, verificación, número nuevo, nombre
visible, App, token de System User permanente, webhook apuntando al dominio.
**Criterio:** mensaje real enviado y recibido desde un móvil.
**Empieza el primer día**: la verificación tarda entre 2 y 5 días hábiles y es
la dependencia externa más lenta del proyecto.

### Fase 7 · Precios (cuando lleguen los datos)
Precios en `horarios/` (formato por decidir según D8), regla de cálculo, línea
de precio en el resultado.
**Criterio:** el precio sale en el resultado y cuadra con la tarifa oficial.

### Fase 8 · Piloto y ajuste
Pruebas con personas reales de la empresa, métricas de uso, y revisión de qué
textos no se entienden para decidir sobre IA de refuerzo, avisos y recordar
pueblo.

**Estimación total: 9-11 días de trabajo**, sin contar las esperas de Meta ni
las respuestas de la empresa.

---

## 9. Pruebas

Mismo enfoque que Peluquería: todas las APIs externas simuladas, sin
credenciales reales.

| Fichero | Qué cubre |
|---|---|
| `test_formato.py` | Cada regla de 2.3 rechaza su caso con mensaje concreto; `horarios/` real valida |
| `test_diff.py` | Altas, bajas y cambios de hora, de observaciones, de temporadas y de días, en lenguaje de negocio |
| `test_formatear.py` | Idempotente; no cambia ningún dato |
| `test_revision.py` | El HTML contiene cada línea, temporada, leyenda y pendiente |
| `test_calendario.py` | Temporadas, festivos, viernes lectivo, agosto |
| `test_query.py` | Pruebas doradas; sentido correcto; sin servicio; sin trayecto |
| `test_matcher.py` | Las 7 ramas de 4.7; `Villafranca` (también con errata); erratas por longitud; mínimo de 3 letras; zonas |
| `test_fechas.py` | Separadores y espacios; año implícito y explícito; fechas imposibles; fechas pasadas; rechazo de lenguaje natural (`mañana`, `el viernes`) |
| `test_conversation.py` | Flujo completo; casos borde; caducidad de estado |
| `test_interactive.py` | **Ninguna lista supera 10 filas ni ningún botón 3** |
| `test_webhook.py` | HMAC, dedup, límites, payloads inválidos |

`test_interactive.py` merece mención aparte: es la prueba que impide el fallo
más fácil de cometer, porque la lista de destinos se genera dinámicamente y su
longitud depende del origen elegido.

---

## 10. Dudas abiertas

> Las dudas sobre los datos se han detallado y enviado a negocio el
> 2026-09-26: [`docs/preguntas_negocio.txt`](docs/preguntas_negocio.txt)
> (P01-P27, y las decisiones ya tomadas D-a a D-p). D1, D2, D4 y D5 quedan
> desglosadas allí: D1 → P01, D-a; D2 → P06, D-m; D4 → P02, D-b, D-c;
> D5 → P10-P14. D3 → P03 y P04. D6 deja de aplicar: el Excel no se mantiene.

### Datos
- **D1.** ¿Es el Excel actual el definitivo? ¿Qué hacemos con `POSADAS INV` y
  `BLAZQUEZ`, fechadas en 2025/26, y con la falta de hoja de verano en `PYA`?
- **D2.** ¿Se descartan todas las notas internas y las 4 filas ocultas de
  `BELAL - POZ INV`, o alguna es información pública?
- **D3.** Festivos: ¿solo los nacionales y andaluces, o también los locales de
  cada municipio? Si un festivo cae en sábado, ¿se aplica el horario de sábado
  o el de "domingos y festivos"? ¿Hay servicios especiales en Nochebuena,
  Semana Santa o feria? *(Nota, ciclo B: negocio ha respondido P03 (festivos
  locales, 25/12 y 01/01 sin servicio) y está implementado, ver 2.3; los días
  con horario especial siguen abiertos como P28.)*
- **D4.** Temporadas: fechas exactas de inicio y fin por línea, incluidos los
  arranques del 01/09 y del 15/09 y el "fin de verano" sin fecha. ¿Y después
  del verano de 2027?
- **D5.** ¿Qué paradas cuentan como la misma localidad? Pozoblanco
  pueblo/hospital/estación parece que sí; Villaharta y su cruce, que no.
- **D6.** ¿Quién mantiene el Excel y con qué antelación avisa de un cambio?

### Producto
- **D7.** ¿Qué 8 pueblos van en la lista de inicio? Lo tiene que decir la
  empresa, que sabe dónde vende billetes.
- **D8.** Precios: ¿dependen solo de la línea o del tramo entre paradas? (En
  interurbano lo normal es por tramo.) ¿Hay bonos y descuentos? La web menciona
  un Abono Único. ¿Cambian en festivos? ¿Hay ida y vuelta?
- **D9.** ¿Confirmamos que el operador es Autocares San Sebastián y que hay
  encargo suyo? El diseño asume su teléfono, su horario de oficina y sus
  enlaces. *(Nota, ciclo B: el horario de oficina ya está cargado por días en
  `config.yaml` (P19c); el operador y los enlaces siguen sin confirmar.)*
- **D10.** ¿Qué enlaces van en "Información"? Propuesta: teléfono, horario de
  oficina (L-V 9:00-14:00 y 17:00-19:30), compra online, bonos y PDF de
  horarios. *(Nota, ciclo B: el horario de oficina propuesto queda
  sustituido por el de P19c, por días, en `config.yaml`; los enlaces siguen
  abiertos.)*
- **D11.** ¿Solo español? El diseño lo asume.

### Técnicas
- **D12.** ¿Subdominio definitivo? ¿Se sigue con DuckDNS o la empresa pone
  dominio propio? DuckDNS no tiene SLA y ya figura como riesgo asumido en
  Peluquería.
- **D13.** ¿Hace falta aviso de privacidad? El bot procesa números de teléfono.
  Hoy no se guarda nada en disco (el estado vive en memoria y caduca a los 30
  min), lo cual ayuda, pero conviene confirmarlo con la empresa.
- **D14.** ¿Repositorio propio en GitHub y quién lo administra?

## 11. Fuentes

- [Autocares San Sebastián — horarios](https://www.autocaressansebastian.es/es/horarios.html)
- [Meta — mensajes no plantilla (cambio del 1-oct-2026)](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
- [Meta — precios](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- [Meta — límites de mensajes](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits)
- [BOJA — Decreto 84/2026, fiestas laborales de Andalucía 2027](https://www.juntadeandalucia.es/boja/2026/84/1.html)
- [Junta de Andalucía — calendario laboral y fiestas locales](https://www.juntadeandalucia.es/organismos/empleoempresaytrabajoautonomo/areas/relaciones-laborales/calendario-fiestas.html)
- [Calendario escolar de Córdoba 2026-27](https://www.cordobabn.com/articulo/educacion/calendario-escolar-curso-2026-27-andalucia-cuando-comienza-curso-vacaciones-festivos/20260907105155266945.html)
- [Punto de Acceso Nacional de transporte](https://nap.transportes.gob.es/)
