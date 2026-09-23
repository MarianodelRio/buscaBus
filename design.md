# Buscabus — Bot de WhatsApp de horarios de autobús

> Documento base del repositorio. Define el alcance, los datos, la conversación,
> la reutilización del proyecto Peluquería, la infraestructura y las fases de
> implementación. Las dudas abiertas están al final.
>
> Estado: **esbozo aprobado para planificar**. No es un diseño cerrado.
> Fecha: 2026-09-23.

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

## 2. Los datos de origen

### 2.1 Qué hay hoy

`HORARIOS NUEVOS.xlsx`: 18 hojas = 12 líneas, con temporada de invierno y
verano separadas en hojas distintas. Cada hoja contiene matrices con las
paradas en columnas y un viaje por fila, agrupadas por sentido y tipo de día.
Una celda vacía significa que ese viaje no para ahí.

Cifras de la red (calculadas sobre el Excel actual):

- **63 paradas** distintas tras normalizar los nombres.
- **~236 filas de servicio** (viajes).
- **706 pares origen→destino** con servicio directo.
- Córdoba alcanza **53 de las 63** paradas; aparece en el 15 % de los pares
  pero es, con diferencia, el destino más frecuente.
- **31 de los 63 orígenes tienen 9 destinos o menos** → su lista de destinos
  cabe entera en un mensaje de WhatsApp.
- 95 pares están servidos por más de una línea (Córdoba↔El Vacar y
  Córdoba↔Cruce de Villaharta, por 4 hojas cada uno). **Ahí el bot aporta más
  que el PDF**, porque fusiona y ordena todas las salidas.

### 2.2 Por qué el Excel no se puede leer solo por valores

Estos son los problemas reales detectados, y el importador debe resolverlos
todos de forma explícita:

1. **El significado está en los colores.** Amarillo y verde codifican
   "a demanda", "entra en el pueblo", "tiene parada en Los Mochos", etc., y
   **cada hoja usa su propia leyenda**.
2. **Formatos de hora heterogéneos:** `datetime.time`, `"8:00*"`, `"18.10"`,
   `"21:45**"` y hasta `"VIERNES ESCOLAR 16:00"` dentro de una celda de hora.
   Los asteriscos significan cosas distintas en cada hoja.
3. **Contenido interno que no es público:** *"No tendríamos que entrar en
   Rabanales, pero lo hacemos"*, *"PREGUNTAR A ANTONIO SOBRE ESTE HORARIO"*,
   *"SOLO PARA REGIMEN INTERNO"*, y **4 filas ocultas** en `BELAL - POZ INV`.
4. **Muchos tipos de día:** lunes; martes-viernes; lunes-viernes; lunes-jueves;
   viernes; sábado; domingo; "domingos y festivos"; "no hay servicio". En
   Villaviciosa el lunes tiene horario propio, distinto de martes-viernes.
5. **Condiciones que no son de calendario:** "solo viernes en periodo escolar",
   "Cardeña-Pozoblanco no está disponible en agosto", "solo lleva a Villanueva
   de Córdoba si tiene viajeros desde Córdoba", servicios bajo demanda, y en la
   línea de Badajoz "los horarios son de paso aproximado".
6. **Nombres inconsistentes:** `GUALDALCAZAR`/`GUADALCAZAR`, seis grafías de
   Villanueva de Córdoba, `ST EUFEMIA`/`STA EUFEMIA`. Y un caso peligroso:
   **`VILLAFRANCA`** es Villafranca de Córdoba en la línea de Adamuz y
   Villafranca de los Barros en la de Badajoz.
7. **Fechas de temporada incoherentes:** `POSADAS INV` y `BLAZQUEZ` llevan
   fechas de 2025/26 (parecen hojas sin actualizar); `PYA` no tiene hoja de
   verano; el invierno empieza el 01/09 en unas líneas y el 15/09 en otras; las
   de verano terminan en "fin de vacaciones", sin fecha.
8. **Dos columnas no son para clientes:** `RUTA` (número de vehículo o
   circuito) y `VALIDADORA` (código interno).

### 2.3 El importador

```
HORARIOS NUEVOS.xlsx ─┐
                      ├─▶ tools/import_excel.py ─▶ data/*.csv
config_import.yaml ───┘                         ├─▶ informe de importación
                                                ├─▶ diff contra la versión previa
                                                └─▶ vista de revisión (Markdown)
```

**Principio:** el Excel es lo que edita la empresa. Los CSV generados **no se
tocan a mano jamás**. Todo el conocimiento que el Excel no dice explícitamente
vive en `config_import.yaml`, escrito una vez y versionado en git:

- Leyenda de colores **por hoja** (qué significa amarillo en `POZOB INV`).
- Significado de cada asterisco **por hoja**.
- Tabla de alias y normalización de nombres de parada.
- Qué hojas, filas, columnas y notas se ignoran.
- Agrupación parada → localidad y parada → zona.

**Regla de oro: ante lo desconocido, falla; nunca adivines.** Si el script
encuentra un color nuevo, un asterisco sin leyenda, una parada sin mapear, un
bloque sin título de tipo de día o unas horas que retroceden, **aborta con un
mensaje concreto** (`hoja POZOB INV, celda H24: marca desconocida '**'`). Un
horario mal importado hace que alguien pierda un autobús: es el peor fallo
posible de este producto.

**Formato de salida: CSV en el repositorio, sin base de datos.** Son pocas
tablas, se ven bien en los diffs de git, se abren en Excel para depurar y caben
de sobra en memoria (~236 viajes). Una base de datos añadiría operación sin
aportar nada a este volumen.

**La revisión debe ser barata**, no repasar 236 filas a ojo. El script produce:

1. **Diff contra la versión anterior**, en lenguaje de negocio:
   *"Línea Pozoblanco-Córdoba, L-V: añadida salida 07:05; 15:15 → 15:20;
   eliminada 18:00"*. La empresa solo revisa lo que ha cambiado.
2. **Cuadre de horas:** toda hora del Excel debe aparecer en los CSV y
   viceversa. Si sobra o falta una sola, no se publica.
3. **Vista de revisión:** regenera en Markdown una tabla por línea con la misma
   forma que el Excel original, para comparar de un vistazo.
4. **Pruebas doradas:** 10-15 consultas con su respuesta correcta validada por
   la empresa (ej. `Pozoblanco → Córdoba, lunes de invierno = 06:55, 08:15,
   10:00, 15:15, 18:00`), ejecutadas como tests en cada importación.

**Ciclo de actualización:** llega el Excel nuevo → `make import` → se revisan
diff e informe → se aprueba → commit de los CSV → `make update` en la VM. Si
algo sale mal, se revierte el commit. Los CSV en git dan historial y vuelta
atrás gratis.

**Peticiones a la empresa** (facilitan el mantenimiento, no son obligatorias):
mantener la estructura de hojas y bloques, mover los comentarios internos a una
hoja aparte, y no ocultar filas.

### 2.4 Modelo de datos

Inspirado en **GTFS** (el estándar internacional de horarios de transporte)
sin adoptarlo entero. Se toman prestados sus conceptos útiles: separación entre
servicio y calendario, marca de "parada a demanda" (`pickup_type=2`) y marca de
"hora aproximada" (`timepoint=0`). Adoptarlo del todo permitiría más adelante
publicar en el [Punto de Acceso Nacional](https://nap.transportes.gob.es/) o en
Google Maps; hoy sería sobreingeniería.

| Fichero | Contenido |
|---|---|
| `localidades.csv` | Lo que elige el usuario. Nombre canónico, zona, alias. |
| `paradas.csv` | Parada física. Pertenece a una localidad. Nombre público. |
| `lineas.csv` | Línea comercial, nombre público, teléfono si es a demanda. |
| `temporadas.csv` | Por línea: nombre, fecha inicio, fecha fin. |
| `servicios.csv` | Un viaje: línea, sentido, tipo de día, temporada, condiciones. |
| `horas.csv` | Hora de un servicio en una parada, con orden y marcas. |
| `calendario.csv` | Festivos y periodo escolar, con su ámbito. |

Puntos clave del modelo:

- **El usuario elige una localidad; el resultado muestra la parada.** Pozoblanco
  tiene tres paradas en el Excel (pueblo, hospital, estación) y hacer elegir
  entre ellas es confuso. Se elige "Pozoblanco" y el resultado dice de dónde
  sale cada bus. **Cuidado:** Villaharta y Cruce de Villaharta **no** son el
  mismo sitio (el cruce está en la carretera, lejos del pueblo) y no deben
  fusionarse. Ver duda D5.
- **Las condiciones son datos, no texto libre**: `a_demanda`,
  `solo_viernes_lectivo`, `no_en_agosto`, `hora_aproximada`,
  `solo_con_viajeros_desde`. Cada una tiene su mensaje al cliente en
  `messages.py` y su regla en el motor.

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
4. **Ordenar por hora de salida** y anotar las condiciones que aplican.
5. **Si la fecha es hoy**, marcar o retirar las salidas ya pasadas.

Todo en memoria, sin E/S. El coste es despreciable frente a los ~0,5 s que
costaba una consulta a Google Calendar en Peluquería.

### Reglas de calendario

- **Festivos:** BOJA — [Decreto 101/2025](https://www.juntadeandalucia.es/organismos/empleoempresaytrabajoautonomo/areas/relaciones-laborales/calendario-fiestas.html)
  para 2026 y [Decreto 84/2026](https://www.juntadeandalucia.es/boja/2026/84/1.html)
  para 2027, más 2 festivos locales por municipio. Se cargan a mano en
  `calendario.csv`, una vez al año. Ver duda D3.
- **Periodo escolar:** calendario escolar de Córdoba 2026-27 — curso del
  01/09/2026 al 30/06/2027, fin de clases el 23/06/2027, Navidad del 23/12 al
  06/01, Semana Santa del 20 al 28/03/2027.
- **Temporadas:** hoy son incoherentes entre hojas (ver 2.2 punto 7). Hasta
  aclararlo, el importador exige fecha de inicio y fin explícitas por línea en
  `config_import.yaml`, y falla si falta alguna.

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
(`el`, `la`, `los`). La tabla de alias vive en `config_import.yaml` y recoge las
variantes del Excel más los nombres coloquiales que aporte la empresa.

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
  día se despliegan CSV sin reiniciar; por defecto no.)

### 5.3 Descartar por completo

Todo `app/services/calendar/` (service, queries, mutations, engine, caches,
locks, client, repository), `app/utils/parser.py`, `app/utils/slots.py`, los
jobs de recordatorios y sincronización, `generar_qr.py` (salvo que se quiera QR
de captación) y las dependencias `google-api-python-client`, `google-auth`.

### 5.4 Módulos nuevos

```
app/services/horarios/
  loader.py       # Carga los CSV a memoria al arrancar. Valida integridad
  query.py        # El motor del punto 3
  calendario.py   # Temporada, tipo de día, festivos, periodo escolar
app/utils/
  matcher.py      # Reglas de coincidencia de texto del punto 4.7
  fechas.py       # Parseo de "25/12", "el viernes que viene", "mañana"
tools/
  import_excel.py # El importador del punto 2.3
  diff_datos.py   # Diff en lenguaje de negocio entre dos versiones de CSV
```

### 5.5 Mapa de módulos resultante

```
buscabus/
  config.yaml            # Negocio: teléfono, horario oficina, enlaces, pueblos del menú
  config_import.yaml     # Conocimiento del Excel: leyendas, alias, zonas
  data/                  # CSV generados. NO editar a mano
  horarios_fuente/       # El Excel tal cual lo manda la empresa
  app/
    config.py  main.py
    handlers/    webhook.py  conversation.py
    services/    whatsapp.py  scheduler.py  horarios/
    utils/       interactive.py  messages.py  matcher.py  fechas.py
                 metrics.py  dedup.py  rate_limiter.py  security.py  admin.py
  tools/         import_excel.py  diff_datos.py
  tests/
  watchdog.py  Makefile  requirements.txt
```

### 5.6 Dependencias

Se quitan `google-api-python-client` y `google-auth`. Se añade `openpyxl`
(solo para el importador; puede ir en un `requirements-dev.txt` para no
instalarlo en la VM). Se mantiene el resto: fastapi, starlette, uvicorn,
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

### Fase 1 · Importador (2-3 días) — *la fase de mayor riesgo, va primero*
`tools/import_excel.py` + `config_import.yaml` + informe + `diff_datos.py` +
vista de revisión. Incluye mapear a mano las leyendas de las 18 hojas.
**Criterio:** los 63 nombres de parada mapeados; las ~236 filas importadas; el
cuadre de horas al 100 %; el script **aborta** ante cualquier marca desconocida;
la vista de revisión reproduce el Excel.

### Fase 2 · Motor y calendario (2 días)
`loader.py`, `calendario.py`, `query.py`, `calendario.csv` del curso 2026-27.
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
`precios.csv`, regla de cálculo, línea de precio en el resultado.
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
| `test_import.py` | Cada hoja del Excel; marcas desconocidas abortan; cuadre de horas |
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
