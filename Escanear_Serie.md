# Banco de pruebas serie — Jenway 6705

Herramienta para comunicarse con el espectrofotómetro **Jenway 6705** por su puerto USB/serie.

- Driver seguro de producción: `jenway67/puerto_jenway.py` (`Jenway6705Serial`)
- Lógica de exploración histórica: `jenway67/escaner_serie.py`
- CLI: `Script/escanear_serie.py` · Lanzador: `Escanear_Serie.bat`
- Pruebas (sin hardware): `tests/test_puerto_jenway.py` + `tests/test_escaneo_serie.py` +
  `tests/test_tiempos_respuesta.py` + `tests/test_artefactos.py`
- Informes: `maestro/_escaneo_serie/` (`*.txt` legible + `*.json` completo)

## Protocolo verificado (DataWay v0.21) y protección contra bloqueo

Mediante ingeniería inversa de `DataWay v0.21` (`Jenway_67xx.dll`, `CommBase.dll`, `Comms.dll`) y capturas reales de `API Monitor`, el protocolo serie nativo del **Jenway 6705** queda completamente determinado:

1. **Configuración fija:** `57600 8N1` (`57600` baudios, 8 bits de datos, sin paridad, 1 bit de parada).
2. **Líneas de control:** `DTR = True`, `RTS = True`, sin control de flujo (`Handshake.none`) y sin condición `BREAK`.
3. **Asentamiento:** Pausa obligatoria de **`100 ms`** tras abrir el puerto antes de enviar cualquier comando.
4. **Lista blanca estricta de 2 únicos comandos de 1 byte (sin `\r` ni `\n`):**
   - `b"*"` (`0x2A`): Handshake de identificación $\rightarrow$ el equipo responde `"67XX \r\n"`.
   - `b"#"` (`0x23`): Solicitud de lectura $\rightarrow$ el equipo vuelca el ticket de 40 columnas terminado en `========================================\r\n`.
5. **Drenaje `PauseAndLook`:** Nunca se cierra el puerto ni se envía otro byte hasta que el flujo recibido permanezca en silencio al menos `500 ms` tras completar el ticket.

> **Importante:** Por defecto, `Script/escanear_serie.py` utiliza ahora este modo seguro (`Jenway6705Serial`) sobre cualquier puerto real para evitar que el barrido multi-baudio o las sondas abiertas bloqueen la UART del espectrofotómetro durante ~10 minutos.

```powershell
# Probar sin equipo conectado usando el simulador interno:
py -3.12 Script\escanear_serie.py --puerto SIMULADOR --pedir-lectura

# Conectar de forma segura al equipo real (57600 8N1, solo '*' y '#'):
py -3.12 Script\escanear_serie.py --puerto COM4 --pedir-lectura
```

## Por qué existía el barrido exploratorio

El manual del 6705 **no documenta ningún protocolo de control remoto**: solo USB
(transferencia de ficheros a la tarjeta), Centronics (impresora) y salida analógica.
El fabricante no responde sobre su software. Antes de desensamblar `DataWay v0.21`, este módulo servía para explorar configuraciones clásicas en laboratorio.

## Seguridad: tres juegos de sondas, separados por lo que HACEN

No es lo mismo **preguntar** que **cambiar algo**, así que las sondas están en tres
juegos y solo el primero se envía por defecto:

| Juego | Cuántas | Qué es | ¿Se envía? |
|---|---|---|---|
| `SONDAS_RAPIDAS` | 11 | Consultas puras: ENQ, CR, LF, CRLF, NUL, ESC, XON, `*IDN?`, `?`, `V`, STX/ETX | **Sí** (por defecto) |
| `SONDAS_AMPLIADAS` | +20 | Consultas de otros protocolos (ver abajo) | Con `--sondas ampliadas` |
| `SONDAS_ESTADO` | 7 | Cambian estado o arrancan un modo de transferencia | Solo con `--permitir-estado` |
| `sondas_de_bytes()` | 256 | Barrido exhaustivo de 1 byte (0x00–0xFF) | Solo con `--barrido-bytes` |
| `SONDAS_CONTROL` | 6 | Control para distinguir una respuesta de un ARTEFACTO (ver abajo) | Con `--sondas control` |

La separación no es cosmética: permite **seguir afirmando** "el juego por defecto
solo pregunta" con una prueba automática detrás
(`test_todos_los_juegos_de_consulta_siguen_siendo_benignos`, con lista negra:
FORMAT, ERASE, DELETE, *RST, RESET, CLEAR, INIT, DOWNLOAD, UPDATE).

**Las 7 de estado, y por qué están aparte:** `NAK x3`, `C x3`, `SOH`, `ACK`, `CAN`
(XMODEM: piden o cancelan una transferencia), `*CLS` (limpia banderas de estado) y
`AT` (solo para descartarlo). Ninguna borra ni formatea, pero **no son consultas**.

## Qué sondas se envían (y por qué en este orden)

| Grupo | Sondas | Mecanismo detrás | Expectativa |
|---|---|---|---|
| Consultas genéricas | ENQ, CR, LF, NUL, ESC, XON, `*IDN?`, `?`, `V` | Handshake universal | Baja, pero se prueba siempre lo primero |
| **XMODEM / transferencia** | `NAK x3`, `C x3`, SOH, ACK, CAN | El software OEM movía **ficheros** por este puerto, y XMODEM es *la* forma clásica de moverlos por un serie en un instrumento de esa época | **La más prometedora**: si el firmware trae receptor XMODEM, contesta con un bloque |
| Jenway 63xx/73xx | `S`, `R`, `T`, `M`, `W`, `D` + CR | Otras generaciones de Jenway usaban órdenes de una letra | Baja (el 6705 no tiene RS-232, aunque el FTDI sí es un UART) |
| SCPI | `*TST?`, `*OPC?`, `*STB?`, `*ESE?` | Norma de instrumentación por bus | Muy baja (el manual no menciona SCPI ni GPIB) |
| Tramas STX/ETX | `STX '0' ETX`, `STX 'S' ETX` | Estilo Shimadzu/PerkinElmer | Muy baja (otro fabricante) |
| Handshakes ASCII | `JENWAY`, `CONNECT`, `HELLO`, `LIST`, `DIR`, `READY` | Conjeturas de protocolo de ficheros | Baja |
| Wake-up | doble y triple CR | Despertar un enlace dormido | Complementaria |
| Barrido de 1 byte | 0x00–0xFF | Cubre **todo** el espacio de órdenes de un byte | Sistemático |

> **Nota honesta sobre `AT`:** el FT232R es un puente USB↔serie, **no** un módem: no
> interpreta `AT`. Se incluye solo para poder descartarlo por escrito.

> **Sobre el barrido de 1 byte:** es lo más sistemático posible (cubre de golpe las
> órdenes de una letra), pero es también el único juego que puede topar con una
> orden **desconocida** de un byte. Por eso no se envía solo.

## Cuánto tarda (para planear la sesión)

Cuidado con una confusión fácil: `--ventana` (por defecto **0,4 s**) es lo que se
escucha **por sonda**, no el tiempo que se espera que tarde el equipo en contestar.
El cálculo es `sondas × ventana × configuraciones + asentamiento × configuraciones`, y
el propio programa lo estima al arrancar:

| Corrida | Sondas | Configs | Tiempo |
|---|---|---|---|
| `--sondas rapidas` (por defecto) | 11 | 15 | ~1 min |
| `--sondas ampliadas` | 31 | 15 | ~4 min |
| `--sondas ampliadas --completo` | 31 | 132 | ~27 min |
| `--sondas ampliadas --permitir-estado --barrido-bytes` | 294 | 15 | ~30 min |

## Los tres tiempos de espera, y por qué son esos

Los tres son **segundos**, no minutos, y cada uno responde a una pregunta distinta:

| Opción | Por defecto | Qué significa |
|---|---|---|
| `--ventana` | `0.4` = 0,4 s | Lo que se escucha por sonda, **siempre** |
| `--ventana-larga` | `90s` = 1 min 30 s | Hasta dónde se **amplía** la escucha **solo si algo empieza a llegar** |
| `--asentar` | `1.5` = 1,5 s | Pausa tras abrir el puerto, antes de la primera sonda |

Aceptan unidad escrita: `0.4`, `90s`, `1m30s`, `2min`, `500ms`. Un número suelto son
segundos.

**Por qué 0,4 s basta para una CONSULTA.** `*IDN?\r` son 6 bytes = 60 bits: a 9600
baudios tarda **6 ms** en el cable. Súmale los 16 ms del temporizador del FTDI y los
50 ms del *timeout* del puerto → **unos 70 ms en el peor caso**. 0,4 s es 5-6 veces
eso. Ningún firmware de esta época tarda 90 s en decir su nombre.

**Por qué 90 s sí hacen falta para una OPERACIÓN.** Volcar un espectro completo (7101
puntos) no es una consulta: son ~28 KB en binario o ~57 KB en texto. A 9600 baudios
eso es **30 s en binario y 59 s en ASCII**; a 115200, 2,5 s. El *minuto y medio* es
exactamente la escala de una **transferencia**, no de una respuesta.

**Por qué la ventana larga es adaptativa y no fija.** Con 90 s fijos por sonda, la
corrida agotadora (294 sondas × 15 configuraciones = 4410 sondas) serían **110 horas
(4,6 días)**. Con la ventana adaptativa los casos silenciosos siguen costando 0,4 s
(29 min en total) y **solo la sonda que contesta** se espera entera. El informe marca
esas filas con `<ESPERA AMPLIADA: X s de escucha>` y cada resultado guarda `espera_s`
(los segundos que se escuchó de verdad): si una respuesta **agota** los 90 s, es que la
transferencia es más larga que la ventana y hay que subirla.

**Por qué el asentamiento.** Sin esa pausa, la primera sonda de cada configuración sale
inmediatamente después de abrir el puerto, cuando el chip USB↔serie aún no está listo
(y si el equipo acaba de escanear o de imprimir, tampoco está escuchando): esa sonda
cae al vacío y **ensucia** esa configuración. Cuesta 1,5 s × 15 = 22 s en total.

```bat
:: esperar minuto y medio solo cuando algo contesta (por defecto)
Escanear_Serie.bat

:: forzar la espera corta y desactivar la ampliacion
Escanear_Serie.bat --ventana 0.4 --ventana-larga 0

:: dar mas margen a una transferencia lenta
Escanear_Serie.bat --ventana-larga 3m --asentar 5s

:: consultas de otros protocolos
Escanear_Serie.bat --sondas ampliadas

:: agotando: estado (XMODEM) y barrido de 1 byte
Escanear_Serie.bat --sondas ampliadas --permitir-estado --barrido-bytes
```

## ARREGLOS: cuando parece que contesta y NO contesta

**Medido el 23/09 contra el 6705 real** (`_escaneo_serie/escaneo_20260923-103546`).
El barrido dio 88 lecturas "que no son eco" y anuncio *"El equipo habla"*.
**84 de ellas eran artefacto.** Tres senales lo delatan:

| Senal | Lo que se midio | Por que no puede ser el instrumento |
|---|---|---|
| El byte es siempre el mismo | `FF` en **todas** las configuraciones de 8 bits de datos; `7F` en **todas** las de 7 | El valor lo decide **nuestra** configuracion del puerto. El equipo no puede saber si tenemos 7 u 8 bits |
| No depende de lo que preguntamos | `0x05`, `0x0D`, `0x00`, `0x1B`, `*IDN?`... todas -> `FF` | Ningun protocolo contesta lo mismo a preguntas distintas |
| Crece con lo que enviamos | 1 B -> 1 B; 6 B -> 2 B; 7 B -> 3 B | La "respuesta" sigue a nuestra transmision, no a la pregunta |
| Con el puerto en reposo no llega nada | 60 s de escucha pasiva -> **0 bytes** | Si el equipo emitiera, se veria sin preguntarle |

Es la firma clasica de un **artefacto de recepcion**: la linea en reposo (alta) y el
receptor creyendo ver un bit de arranque durante nuestra propia transmision.

**Lo que de verdad queda en pie** de aquella corrida son 4 lecturas: `E6` (NUL a
38400), `15` (NUL a 57600) y `36 37 58 58 20 0D` = `"67XX " + CR` (a 57600, dos
veces). Las tres primeras tambien tienen explicacion de artefacto: transmitir `0x00`
deja la linea baja nueve tiempos de bit, como un *break*, y el flanco de liberacion
puede generar un byte suelto. Y la cuarta: a 57600 tenemos dos sondas largas (6 y 7
bytes) y son justo las dos que devuelven 6 bytes, mientras las de 1-2 bytes no
devuelven nada -- otra vez el tamano sigue a lo que enviamos. Que el resultado sea
ASCII legible puede ser casualidad del muestreo.

**Conclusion honesta: no hay (todavia) ninguna prueba de que el equipo hable.** Lo que
hay es un artefacto que el banco no sabia distinguir. Eso ya esta arreglado (ver
abajo), pero el dato hay que confirmarlo con una prueba, no con una corazonada.

### El juego de control: `--sondas control`

```bat
Escanear_Serie.bat --sondas control
```

6 sondas, ~2 min, y decide por **comparacion**:

| Sonda | Que prueba | Si es artefacto | Si es de verdad |
|---|---|---|---|
| `CTL-TAM-A/B/C` — 9 B: `AAAAAAAA`+CR, `ZZZZZZZZ`+CR, `*IDN?`+CR | Mismo tamano, distinto contenido | Sale lo **mismo** en las tres | `*IDN?` da **otra cosa** |
| `CTL-CORTO` vs `CTL-LARGO` — `A`+CR (2 B) y 26 B de `A` | Mismo contenido, distinto tamano | Lo recibido **crece** con lo enviado | Contesta igual (o nada) a la basura |
| `CTL-INERTE` — 20 B de relleno inerte | Basura | Devuelve bytes igualmente | Ningun equipo contesta util a basura |

**Criterio:** si las tres del mismo tamano dan lo mismo, o si lo recibido crece con lo
que enviamos, es artefacto -- aunque el byte no sea `FF`.

### Lo que ahora hace el banco solo

- El **veredicto** separa cuatro grupos: respuestas reales, ecos, **artefactos**
  (byte todo-a-uno bajo *nuestra* configuracion) y **repetidos** (la misma respuesta a
  >=3 preguntas de contenido distinto). Con la corrida del 23/09 el veredicto nuevo
  dice `RESPUESTA: 4 ... (OJO: se han descartado 84 artefactos)`, no "88, el equipo
  habla".
- La tabla del informe marca cada fila sospechosa con `<ARTEFACTO...>`.
- `<ESPERA AMPLIADA>` ya **no** se marca en filas vacias: solo cuando la escucha se
  amplio y de verdad llego algo (antes bastaba con la granularidad del puerto).

## Antes de ejecutar

1. **Conecta y enciende** el 6705. El puerto COM lo crea el chip FTDI al alimentarse
   el equipo; con el equipo apagado no existe (Windows lo marca como fantasma,
   `Code 45`).
2. **Cierra cualquier otro programa** que pueda tener el puerto abierto: el puerto
   serie es exclusivo. Si está ocupado, la herramienta lo dice (`NO SE PUDO ABRIR`).

## Las tres corridas, en orden

```bat
:: 1. ¿Hay puerto?  (resuelve dudas de driver)
Escanear_Serie.bat --listar

:: 2. ¿Habla por su cuenta?  Mientras corre: pulsa PRINT en el equipo
::    e inserta/retira la tarjeta. No se envía nada.
Escanear_Serie.bat --escuchar 60 --sin-sondas

:: 3. Escaneo rápido: 15 configuraciones x 11 sondas (~1 minuto)
Escanear_Serie.bat

:: 3b. Si quieres agotar: 132 configuraciones (~10 minutos)
Escanear_Serie.bat --completo

:: 3c. Repetir con handshake, por si exige RTS/CTS
Escanear_Serie.bat --flujo rtscts
```

## Cómo leer el veredicto

| Veredicto | Significa | Qué hacer |
|---|---|---|
| `NO HAY PUERTO` | El equipo está apagado, desconectado o el driver FTDI falla | Enciende el equipo / reinstala driver `VID_0403:PID_6001` |
| `NO SE PUDO ABRIR EL PUERTO` | Ocupado por otro programa, o sin permisos | Cierra el otro programa; prueba otro puerto con `--puerto` |
| `SILENCIO TOTAL` | Ningún byte en ninguna configuración ni con ninguna sonda | Lo más probable según el manual. Con `--completo` + `--flujo rtscts` agotas las opciones |
| `SOLO ECO` | Devuelve exactamente lo enviado: es el lazo del chip, **no** es una respuesta | Igual que silencio para efectos prácticos |
| `RESPUESTA` | **¡Algo contesta!** Ahí empieza la ingeniería inversa de verdad | Guardar el informe y ampliar sondas alrededor de la que funcionó |
| `SILENCIO al sondear, pero SI llegaron N bytes` | Emite por su cuenta sin que se le pida | Revisar la escucha pasiva: hay una vía de salida |

## Si contesta algo

1. Guarda el `.txt` y el `.json` (se guardan solos) — son la **primera evidencia real**.
2. Anota la **configuración exacta** que funcionó (velocidad, trama, flujo) y la sonda.
3. Amplía `SONDAS` en `jenway67/escaner_serie.py` con variantes de esa sonda
   (mayúsculas, con/sin CR, con STX/ETX, número de comando…) y repite con
   `--puerto COM3` para no re-barrer todo.
4. Con dos o tres intercambios documentados ya se puede escribir un
   `Especificacion_Protocolo_Serie_6705.md` como el del formato `.JWB`.

## Notas técnicas

- El barrido normal prueba primero las **clásicas de laboratorio** (9600 8N1, 9600 7E1,
  9600 7O1, 9600 8N2, 19200 8N1, 4800 8N1, 4800 7E1, 2400 8N1, 1200 8N1, 38400/57600/
  115200 8N1, 9600 8E1, 9600 8O1, 9600 7N1) = 15. `--completo` hace el producto
  cartesiano de 10 velocidades × {7,8} bits × {N,E,O} × {1,2} stop y añade una segunda
  pasada: **132 configuraciones** en total (~10 min).
- **Control de flujo**: `--flujo rtscts|xonxoff|dsrdtr` repite el barrido con handshake.
  Y con `--completo` se añade automáticamente una **segunda pasada** sobre las 6
  configuraciones más probables probando RTS/CTS y probando con **DTR/RTS bajados**
  (`sin-DTR/RTS`). Esto importa: hay instrumentos que exigen handshake o que no
  contestan si el PC mantiene las líneas activas, y así un "silencio" es un negativo
  **fuerte**, no un falso negativo.

  ```bat
  Escanear_Serie.bat --flujo rtscts
  ```
- Se **reabre** el puerto en cada configuración (algunos equipos necesitan renegociar).
- Se registran los estados de línea (DTR/RTS/CTS/DSR/RI/CD): si CTS o DSR cambian,
  el instrumento está alimentado y manejando las líneas — información útil aunque calle.
- Un `eco` exacto de lo enviado se **marca aparte** para no confundirlo con una respuesta.
- Si el puerto se cae a mitad del barrido (cable, apagón), la fila queda con el error
  y el barrido **no** se tumba.
- `--simular silencio|eco|idn` ejercita la herramienta entera sin instrumento
  (autoprueba). Esos informes llevan el sufijo `_SIMULADO` y lo dicen en la cabecera.

## Guía de ejecución (diagrama de flujo)

Versión visual: `Escanear_Serie_Guia.html` (se abre en el navegador). La misma guía,
en texto:

```text
Punto de partida: equipo ENCENDIDO · cable USB · tarjeta insertada
        │
        ├─ ¿Aparece algún puerto COM?   →  Escanear_Serie.bat --listar
        │     └─ NO → SIN PUERTO: apagado, cable o driver FTDI (VID_0403:PID_6001).
        │              Nada que sondear hasta resolverlo.   [FIN]
        │     └─ SÍ ↓
        │
        ├─ 1 · ¿Habla por su cuenta?    →  --escuchar 60 --sin-sondas
        │     (mientras corre: pulsa PRINT, mete/saca la tarjeta; no envía nada)
        │     └─ SÍ llegan bytes ─────────────────────→  ★ SI CONTESTA
        │     └─ NO ↓
        │
        ├─ 2 · Escaneo base (~1 min)    →  Escanear_Serie.bat
        │     ├─ RESPUESTA ───────────────────────────→  ★ SI CONTESTA
        │     ├─ NO SE PUDO ABRIR → cierra el otro programa (el puerto es exclusivo)
        │     ├─ SOLO ECO → es el lazo del chip, NO es una respuesta
        │     └─ SILENCIO ↓
        │
        ├─ 3a · Handshake (~2 min)      →  --flujo rtscts
        │     └─ SÍ ──────────────────────────────────→  ★ SI CONTESTA     └ NO ↓
        │
        ├─ 3b · Otros protocolos (~4 min) →  --sondas ampliadas
        │     (incluye XMODEM: el software OEM movía FICHEROS por este puerto)
        │     └─ SÍ ──────────────────────────────────→  ★ SI CONTESTA     └ NO ↓
        │
        ├─ 3c · Exhaustivo (~27 min)    →  --completo --sondas ampliadas
        │     └─ SÍ ──────────────────────────────────→  ★ SI CONTESTA     └ NO ↓
        │
        ├─ 4 · Agotar (~30 min)         →  --sondas ampliadas
        │                                  --permitir-estado --barrido-bytes
        │     (XMODEM + *CLS + AT, y barrido de 1 byte 0x00-0xFF)
        │     └─ SÍ ──────────────────────────────────→  ★ SI CONTESTA     └ NO ↓
        │
        └─ SILENCIO en todo lo anterior
              La vía serie queda CERRADA: es un negativo MEDIDO, coherente con el
              manual. Ahí se acaba: el .JWB sigue siendo la fuente de verdad.   [FIN]

★ SI CONTESTA  (en cualquier paso, si sale una RESPUESTA que no sea eco)
   1. Guarda el informe (se guarda solo en _escaneo_serie/).
   2. Anota la config exacta: velocidad, trama, flujo, y la sonda que contestó.
   3. Repite afinando: --puerto COM3 con sondas alrededor de la que ganó.
   4. Si la respuesta agota la ventana (mira espera_s), sube --ventana-larga 3m.
   5. Con 2-3 intercambios documentados ya se escribe la especificación del protocolo.

CUÁNDO NO CORRERLO
   Solo tiene sentido tras un cambio REAL: otro cable o puerto, otro firmware, o si
   el fabricante por fin responde. Si nada cambió, repetirlo da el mismo silencio.
   El informe es EVIDENCIA: no lo borres (lleva fecha y equipo, y se puede comparar).
```

Se va **de lo barato y probable a lo exhaustivo**: no saltes al paso 4 sin agotar el
1-3. Los tiempos son los de la corrida por defecto y el programa los estima al arrancar.

## RESUELTO (23/09): memoria interna "no montada" tras usar el puerto USB

**Sintoma:** en el Memory Manager (Supervisor, PIN 1234) **si** aparecia la memoria
EXTERNA (la tarjeta); la que aparecia **como no montada era la INTERNA**.

**CURA CONFIRMADA:** apagar el instrumento del todo y dejarlo **10 minutos** apagado,
despues encender -> la memoria interna **vuelve a montarse**. (Antes se habia probado
un apagado corto, que no basto.)

**No hubo perdida de datos. No hizo falta formatear nada.** Era un estado volatil, no
una averia.

**Regla practica:** si al usar el puerto USB aparece el icono de comunicacion con el PC
y despues el Memory Manager muestra la memoria interna como no montada, es ese estado
**volatil** -> apagon completo de ~10 minutos y listo. Nada de formatear.

**Lo aprendido, para no perderlo:**

1. Los bytes `FF`/`7F` que el banco llamo "respuesta" son un **artefacto de
   recepcion** (ver la seccion de artefactos): el valor lo decide nuestra propia
   configuracion de bits de datos.
2. **El puerto SI es un canal vivo.** Al abrir el puerto y enviar sondas aparecio en
   la pantalla del instrumento el icono de comunicacion con el PC (computadora + dos
   flechas + espectro), y desaparecio al cerrar el programa. El manual lo confirma:
   el conector USB tipo B es *"for communication to PC"*.
3. **Hipotesis principal del fallo**: el manual (3.2.1) dice que **al encender, la
   memoria INTERNA es el destino por defecto** de guardado/transferencia. Si el
   firmware interpretaba el trafico del USB como el arranque de una sesion de
   transferencia con el PC (eso indica el icono) y esa sesion se cortaba al cerrar el
   puerto (15 configuraciones = 15 aperturas y cierres), es plausible que la memoria
   interna quedara con una sesion a medias y el instrumento la marque como no
   montada. **No esta probado**, y ninguno de los bytes enviados era de escritura,
   borrado ni formato.
4. La tarjeta **NO esta danada**: el PC la lee, los ficheros estan, y ademas estan
   copiados en `Archivos prueba/` y `maestro/tests/data/tarjeta/`.

**Si volviera a pasar, por orden:**

1. Mirar el autotest del encendido: *"System test... Checks internal and external
   memory status"*.
2. **Apagado COMPLETO y largo** (minimo 10 minutos, desenchufado de la red). Un apagon
   corto NO basta: esta medido.
3. Solo si aun asi no monta: valorar el formateo de la memoria interna desde el Memory
   Manager (es irreversible: *"this will permanently delete all information stored in
   the location being formatted"*) o consultar con el servicio tecnico. Los metodos que
   usabamos estan en la tarjeta y copiados en el PC, asi que el formateo de la interna
   no perderia nada nuestro.

**No volver a lanzar el banco serie** contra el instrumento.