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
  calendario.yaml       festivos y periodo escolar (fase 2)
```

#### `paradas.yaml`

```yaml
zonas:
  los-pedroches: Los Pedroches
localidades:                       # lo que elige el usuario
  pozoblanco: { nombre: Pozoblanco, zona: los-pedroches, alias: [pozo] }
  villafranca-de-cordoba: { nombre: Villafranca de Córdoba, zona: adamuz, alias: [villafranca] }
  villafranca-de-los-barros: { nombre: Villafranca de los Barros, zona: extremadura, alias: [villafranca] }
paradas:                           # lo que muestra el resultado
  POZ: { nombre: Pozoblanco, localidad: pozoblanco }
  PZH: { nombre: Pozoblanco (Hospital), localidad: pozoblanco }
pendientes: [P18]                  # preguntas abiertas que no son de una línea
                                    # concreta (zonas, localidades, paradas)
```

- **`pendientes:`** (opcional, lista): preguntas abiertas (`P\d{2}`, igual que
  las de una línea) que afectan a zonas, localidades o paradas y no a una
  línea concreta. Un pendiente mal formado detiene la validación, igual que
  en `lineas/*.yaml`.

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
  tipo: aviso
  ambitos: [linea]
  texto: "Horarios de paso aproximados."
```

- **Condición**: cambia si el autobús sale o si para. Es un conjunto cerrado
  que el motor conoce (`a_demanda`, `solo_viernes_lectivo`,
  `solo_si_viajeros_desde_cordoba`); el validador rechaza una condición que el
  código no sepa aplicar.
- **Aviso**: solo informa (`entra_en_pueblo`, `pasa_por_rivero`,
  `para_en_los_mochos`, `no_para_en_el_pedrera`, `solo_virgen_remedios`,
  `hora_aproximada`...). Se pueden añadir libremente.
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
  - `sin_datos`: no lo sabemos (por ejemplo, Peñarroya en verano, P01). **El
    bot nunca lo trata como "sin servicio"** (4.8).
- Una tabla puede usar una clave más amplia que las de `dias` (la vuelta de
  Badajoz es `lunes-viernes` aunque `dias` declare `lunes-jueves` y `viernes`),
  siempre que todas sus clases tengan estado `horario`.
- **Temporadas**: rangos `DD/MM - DD/MM` (pueden cruzar el año) o
  `todo el año`. Todo día del año, incluido el 29/02, cae en exactamente una.
  El año no se guarda (D-a).

#### Comprobaciones

| Error: detiene la validación | Aviso: sale en el informe |
|---|---|
| YAML mal formado, campo desconocido u obligatorio ausente | El mismo autobús en dos líneas (se fusiona al consultar) |
| Código de parada, letra u observación sin definir | Tramo con un tiempo anómalo frente al resto de viajes de ese tramo |
| Observación usada en un ámbito no permitido | Clases de día en `sin_datos` |
| Condición que el motor no sabe aplicar | Pendientes abiertos, con su número |
| Fila con un número de valores distinto al de paradas | Paradas o localidades definidas que ninguna línea usa |
| Horas que retroceden o viaje con menos de 2 horas | |
| Temporadas que se solapan o dejan días sin cubrir | |
| Clase de día sin declarar, declarada dos veces, o `horario` sin tabla | |
| `a_demanda` usada sin `telefono_demanda` en la línea | |
| Dos tablas de una línea con la misma temporada, días y extremos de cabecera | |
| Marcador `{xxx}` en el `texto` de una observación distinto de `{telefono}` | |
| Pendiente mal formado en `pendientes:` de `paradas.yaml` | |

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

### 2.4 Modelo de datos en memoria

El loader convierte `horarios/` en objetos inmutables:

| Entidad | Contenido |
|---|---|
| `Zona` | Id y nombre |
| `Localidad` | Lo que elige el usuario: id, nombre, zona, alias |
| `Parada` | Parada física: código, nombre público, localidad |
| `Observacion` | Id, letra, tipo (condición/aviso), ámbitos, texto |
| `Linea` | Id, nombre, teléfono a demanda, avisos, meses sin servicio, temporadas, estado de cada clase de día por temporada, pendientes |
| `Temporada` | Nombre y rangos día/mes |
| `Tabla` | Línea, temporada, clave de días y **la lista ordenada de paradas de su cabecera**. Conserva el sentido y el orden de columnas tal como se escribieron; la vista de revisión pinta una tabla por `Tabla`, nunca mezcla tablas |
| `Viaje` | La tabla a la que pertenece (y, por ella, línea, temporada y días), observaciones de viaje, pendientes y la lista ordenada de pasos |
| `Paso` | Parada, hora y observaciones de parada |

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
llegada, duración, parada concreta y notas.

Pasos:

1. **Resolver el calendario de esa fecha:** temporada vigente **para esa línea**
   (cada línea tiene sus fechas), tipo de día (laborable / sábado / domingo y
   festivos) y banderas (`es_festivo`, `es_lectivo`, `mes`).
2. **Filtrar servicios** cuya línea, temporada y tipo de día encajen, y cuyas
   condiciones se cumplan (descartar Cardeña-Pozoblanco en agosto, etc.).
3. **Buscar el par:** el servicio debe parar en una parada del origen y, *más
   adelante en su orden de paradas*, en una del destino. El orden es lo que
   determina el sentido; no hace falta una columna de sentido para esto.
4. **Fusionar el mismo autobús**: si dos viajes de líneas distintas tienen la
   misma hora de salida y de llegada para el par consultado, se muestran una
   sola vez (decisión D-o).
5. **Ordenar por hora de salida** y anotar las condiciones que aplican.
6. **Si la fecha es hoy**, marcar o retirar las salidas ya pasadas.
7. **Si alguna línea implicada tiene `sin_datos` para ese día**, el resultado
   lo dice en lugar de dar a entender que no hay servicio (2.3 y 4.8).

Todo en memoria, sin E/S. El coste es despreciable frente a los ~0,5 s que
costaba una consulta a Google Calendar en Peluquería.

### Reglas de calendario

- **Festivos:** BOJA — [Decreto 101/2025](https://www.juntadeandalucia.es/organismos/empleoempresaytrabajoautonomo/areas/relaciones-laborales/calendario-fiestas.html)
  para 2026 y [Decreto 84/2026](https://www.juntadeandalucia.es/boja/2026/84/1.html)
  para 2027, más 2 festivos locales por municipio. Se cargan a mano en
  `horarios/calendario.yaml`, una vez al año. Ver duda D3 y P03.
- **Periodo escolar:** calendario escolar de Córdoba 2026-27 — curso del
  01/09/2026 al 30/06/2027, fin de clases el 23/06/2027, Navidad del 23/12 al
  06/01, Semana Santa del 20 al 28/03/2027.
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
  Vie 25/09                5 salidas
  Sáb 26/09                2 salidas
  Dom 27/09                3 salidas
  Lun 28/09                5 salidas
  Mar 29/09                5 salidas
  📅 Otra fecha
```

8 filas. Un día sin servicio aparece como `sin servicio` en la descripción (en
una línea como Ochavillos, sábado y domingo saldrían así de entrada). Un
festivo se marca en la descripción: `festivo · 3 salidas`.

**No se pregunta el tipo de día** (laborable / sábado / festivo): a veces ni el
cliente sabe si el jueves es festivo. Se elige **una fecha real** y el bot
deduce el tipo de día, la temporada, el viernes lectivo y las excepciones.

`📅 Otra fecha` acepta `25/12`, `25 de diciembre`, `el viernes que viene`.

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
viernes. El precio queda como hueco hasta tener los datos (duda D8).

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
| Distancia de edición ≤2 y único (`pozoblnco`) | **Confirma**: "¿Pozoblanco?" [Sí] [No] |
| Sin coincidencia | "No conozco ese pueblo" + lista habitual + `Ver todos por zona` |

**Normalización previa:** mayúsculas, sin tildes, sin puntuación, sin artículos
(`el`, `la`, `los`). La tabla de alias vive en `horarios/paradas.yaml` y recoge
los nombres oficiales, las abreviaturas habituales y los nombres coloquiales que
aporte la empresa (P13).

**Caso que siempre pregunta:** `Villafranca` (de Córdoba o de los Barros).
Nunca se resuelve solo.

**`Ver todos por zona`** es la red de seguridad para quien no sabe escribir el
nombre. 7 zonas: Los Pedroches, Guadiato, Vega del Guadalquivir, Adamuz,
Campiña, Extremadura, Córdoba. Las zonas grandes (Los Pedroches tiene 20
paradas, Guadiato 14, Extremadura 11) se parten en dos listas con una fila
"ver más". No es el camino principal, pero ningún usuario se queda sin salida.

### 4.8 Casos borde

| Caso | Respuesta |
|---|---|
| Día sin servicio | Dice cuál es el siguiente día con servicio y lo ofrece en un botón |
| Día sin datos (`sin_datos`) | Dice que no tiene ese horario y da el teléfono con horario de oficina. **Nunca lo presenta como "no hay servicio"** |
| Sin trayecto directo | Lo dice, enseña los destinos que sí existen desde ese origen y da el teléfono con horario de oficina. **No inventa trasbordos** |
| Origen = destino | "Elige un destino distinto" |
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
  fechas.py       # Parseo de "25/12", "el viernes que viene", "mañana"
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

### Fase 2 · Motor y calendario (2 días)
`loader.py`, `calendario.py`, `query.py`, `horarios/calendario.yaml` del curso
2026-27.
**Criterio:** las pruebas doradas pasan; las condiciones especiales (agosto,
viernes lectivo, a demanda) se aplican; un día sin servicio devuelve el
siguiente con servicio.

### Fase 3 · Coincidencia de texto (1 día)
`matcher.py`, `fechas.py`, tabla de alias, zonas.
**Criterio:** todas las ramas de la tabla 4.7 cubiertas por tests; `Villafranca`
siempre pregunta; las erratas de 1-2 letras piden confirmación.

### Fase 4 · Conversación (2-3 días)
`conversation.py`, `interactive.py`, `messages.py`, `webhook.py`, scheduler de
limpieza, comandos de administrador.
**Criterio:** el flujo completo funciona con la API simulada; ninguna lista
supera 10 filas ni ningún botón 3; todos los casos borde de 4.8 cubiertos.

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
| `test_matcher.py` | Las 7 ramas de 4.7; `Villafranca`; erratas; alias |
| `test_fechas.py` | "mañana" vs "por la mañana"; formatos de fecha |
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
  Semana Santa o feria?
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
  enlaces.
- **D10.** ¿Qué enlaces van en "Información"? Propuesta: teléfono, horario de
  oficina (L-V 9:00-14:00 y 17:00-19:30), compra online, bonos y PDF de
  horarios.
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
