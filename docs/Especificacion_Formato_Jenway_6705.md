# Especificación del formato de archivos — Espectrofotómetro **Jenway 6705**

> Documento para **verificación técnica independiente** del formato de datos del
> espectrofotómetro Jenway 6705 (serie 67). Reúne todo lo observado y validado
> durante la ingeniería inversa del formato nativo, con el fin de que un experto
> pueda **reproducir y confirmar o refutar** cada afirmación.
>
> **Fecha:** 15/09/2026 · **Firmware del instrumento:** `67xx V1.64.5`
> **Idioma de la interfaz del equipo:** Español.
>
> **Advertencia de método:** todo lo marcado como **VALIDADO** se comprobó
> comparando la lectura de estos archivos contra el reporte que **el propio
> instrumento imprime** (misma medición). Lo marcado como **HIPÓTESIS** o
> **NO VERIFICADO** no debe tomarse como cierto sin comprobación adicional.

---

## 0. Resumen ejecutivo

El equipo entrega los datos en **cuatro tipos de archivo**, todos generados al
guardar resultados en la tarjeta SD/USB o al imprimir:

| Extensión | Nombre típico | Naturaleza | Contenido |
|---|---|---|---|
| `.JWB` | `323BE947.JWB` (nombre = 8 hex) | **Binario** (little-endian) | Método + **datos de la medición** |
| `.JWX` | `SUMMARYQ.JWX` | **XML** (texto) | **Índice**: qué método es cada `.JWB` |
| `.JWU` | `USERSINF.JWU` | **XML** (texto) | Usuarios y PINs |
| `.TXT` | `3A.TXT`, `TEST1.TXT` | **Texto formateado** | Reporte impreso ("Print → CSV") |

**Idea clave:** el `.JWX` es el *índice* y el `.JWB` es el *dato*. Para saber
**qué modo** tiene un `.JWB` hay que leer el atributo `type=` del `.JWX`
(el `.JWB` por sí solo no dice claramente su modo, aunque hay heurísticas).

---

## 1. El instrumento y el contexto

- **Modelo:** Jenway 6705 (UV/Visible, haz partido, 190–1100 nm, ancho de banda 4 nm).
- **Pantalla:** táctil, color; interfaz en español; memoria interna + tarjeta SD/USB (128 MB–2 GB).
- **Modos de medición** (5): Fotometría, Espectro, Multi-longitud, Cinética, Cuantificación.
- **Interfaz a PC:** puerto USB (se enumera en Windows como *FTDI USB Serial Port*, p. ej. COM3).
- **Acción "imprimir"**: el equipo genera un archivo `.TXT` de **reporte de texto**
  (que el manual llama "CSV", pero **no** es CSV delimitado — ver §7).

---

## 2. Tipos de archivo — reglas de nombrado

- `.JWB`: nombre de **8 dígitos hexadecimales en mayúsculas** + `.JWB`
  (p. ej. `323BE947.JWB`). No es un contador lineal; parece un identificador
  interno. **Un mismo archivo puede ser el "método" y a la vez el primer resultado.**
- `.JWX`: fijo `SUMMARY<Letra>.JWX`, una letra por modo:
  **P**=Fotometría, **S**=Espectro, **M**=Multi-longitud, **K**=Cinética, **Q**=Cuantificación.
- `.JWU`: fijo `USERSINF.JWU`.
- `.TXT`: libre (lo nombra el usuario o secuencia `2D/3A/4A/5A`).

Tamaños típicos observados del `.JWB`:
≈ 888–1084 bytes (métodos y mediciones puntuales) y
≈ 4 968 / 29 368 bytes (espectros con muchos puntos).

---

## 3. Codificaciones

| Archivo | Codificación | Nota |
|---|---|---|
| `.JWX`, `.JWU` | XML de 1 byte; **CP1252/Latin-1** | acentos en español (`Método`, `Cinética`) |
| `.JWB` | **Binario** | enteros/flotantes **little-endian** |
| `.TXT` | **CP1252/Latin-1** | **no UTF-8**; los acentos hacen que muchas herramientas lo detecten como "binario" |

> Consecuencia práctica: los `.TXT` deben leerse en **CP1252**, no en UTF-8.

---

## 4. `.JWU` — Usuarios (XML)

Estructura (una entrada `<User>` por usuario):

```xml
<UserTable>
  <User index="0">
    <Level>0</Level>
    <Status>1</Status>
    <Language>0</Language>
    <Brightness>8</Brightness>
    <DisplayTimeDate>0</DisplayTimeDate>
    <DateFormat>0</DateFormat>
    <BypassLogin>0</BypassLogin>
    <TouchScreenClick>1</TouchScreenClick>
    <ShowAllMethods>0</ShowAllMethods>
    <MyMethods>1</MyMethods>
    <ShowReadOnlyMethods>0</ShowReadOnlyMethods>
    <ShowPublicMethods>0</ShowPublicMethods>
    <Offset>0</Offset>
    <Name>Generic</Name>
    <Passcode>1234</Passcode>          <!-- PIN EN CLARO -->
    <Settings>00000926</Settings>
  </User>
  ...
</UserTable>
```

- **`<Passcode>` está en texto plano** (4 dígitos). Verificado: `Generic`=1234, `Supervisor`=1234, `Alumnos`=0000.
- `<Level>`: 0 = Supervisor/genérico, 1 = usuario nombrado (etiquetas inferidas).

---

## 5. `.JWX` — Índice (XML)

Un archivo por modo; puede contener **varios** `<element>`. Estructura:

```xml
<summary>
  <element id="0" type="4">
    <user>Alumnos</user>
    <method_name>Test1</method_name>
    <method_date>15/9/26 12:54:7</method_date>
    <filename>323bfc6f.JWB</filename>     <!-- .JWB del MÉTODO -->
    <lock>0</lock>
    <samples>
      <s_data index="1" val="Lote por defecto 001"
              date="15/9/26 12:54:8" loc="323bfc6f.JWB"/>  <!-- .JWB del RESULTADO -->
    </samples>
  </element>
  ...
</summary>
```

### 5.1 Mapa de `type=` → modo  — **VALIDADO**

| `type` | Modo |
|---|---|
| `0` | Fotometría (Photometrics) |
| `1` | Espectro (Spectrum) |
| `2` | Multi-longitud (Multi-Wavelength) |
| `3` | Cinética (Kinetics) |
| `4` | Cuantificación (Quantitation) |

### 5.2 Semántica de campos

- `<filename>`: `.JWB` del **método**.
- `<s_data loc=...>`: `.JWB` del **resultado** de cada muestra/lote. *Un mismo
  `.JWB` puede aparecer como `filename` y como `loc` del primer lote.*
- Fechas en formato **`d/M/aa h:mm:ss`** (mes/año sin cero inicial; `1/1/0` = fecha no
  inicializada).
- `<lock>`: 0 = desbloqueado, distinto de 0 = bloqueado.

---

## 6. `.JWB` — Binario (el núcleo)

Formato **little-endian**. Los flotantes son **IEEE-754 de 32 bits** (`float32`).

### 6.1 Cabecera común (offsets absolutos en bytes)

| Offset | Tipo | Valor observado | Interpretación | Estado |
|---|---|---|---|---|
| `0x00` | float32 | `20.0` | constante en todos los archivos | **NO VERIFICADO** (¿temperatura? ¿parámetro fijo?) |
| `0x04`–`0x33` | mixto (int16/float) | varía | parámetros de método | **NO MAPEADO** |
| `0x34` | float32 | p. ej. `400.0` | **λ₁** (nm) — o inicio de barrido | VALIDADO |
| `0x38` | float32 | p. ej. `500.0` | **λ₂** = fin de barrido (espectro) / 2ª λ (multi); `0` en otros | VALIDADO |
| `0x3C` | float32 | `300/400` | **λ₃** (multi) | VALIDADO |
| `0x40` | float32 | `600` | **λ₄** (multi) | VALIDADO |
| `0x5C` | float32 | p. ej. `-0.301` | **escala Y mínima** (absorbancia) | VALIDADO (espectro/multi) |
| `0x60` | float32 | p. ej. `3.0` | **escala Y máxima** (absorbancia) | VALIDADO (espectro/multi) |

> Las **lecturas** se guardan siempre al **final del archivo** (bloque "tail").

### 6.2 Modo **ESPECTRO** (type=1) — **VALIDADO punto a punto**

- λ inicio = `f32 @ 0x34`, λ fin = `f32 @ 0x38`.
- **Número de puntos:** `N = (λ_fin − λ_inicio) / 0.1 + 1`  (barrido a **0.1 nm**).
- **Datos:** los **últimos `N` `float32`** del archivo; cada uno es **%Transmitancia**.
- Offset de inicio del bloque: `len(archivo) − N*4` (típicamente `0x3C4`).
- **Absorbancia** derivada: `A = −log10(%T / 100)`.
- Ejemplo verificado: `323BE947.JWB`, λ 190→900 nm ⇒ N = 7101 puntos; a 190 nm %T da A=2.457.

### 6.3 Modo **MULTI-LONGITUD** (type=2) — **VALIDADO**

- 4 longitudes de onda: `f32 @ 0x34, 0x38, 0x3C, 0x40`
  (verificado `[300, 330, 400, 600]`).
- 4 lecturas: **los últimos 4 `float32`** del archivo, en **%T**, en el orden de las λ.
- Absorbancia derivada `A = −log10(%T/100)`.
- Verificado: `%T=199.9 → A=−0.301`; `169.118 → −0.228`; `166.701 → −0.222` (idénticos al reporte).

### 6.4 Modo **FOTOMETRÍA** (type=0) — **PARCIAL**

- λ = `f32 @ 0x34`.
- Lectura: **el último `float32`** del archivo, en **%T**.
- Verificado con un caso **saturado** (%T = 0.0 ⇒ A = ∞) y con un caso **%T=100 ⇒ A=0.0**.
- Pendiente: no se ha observado un caso con varias réplicas simultáneas.

### 6.5 Modo **CINÉTICA** (type=3) — **VALIDADO**

- λ = `f32 @ 0x34`.
- Serie temporal: los valores **%T** del bloque final que están **adyacentes a la
  marca centinela `−99999.0`**.
- ⚠️ **Particularidad importante:** el par puede venir como `(%T, −99999)` **o**
  `(−99999, %T)` según el archivo. Además hay un **valor "guarda" denormal (~0)**
  al inicio del bloque que **NO es una lectura** y debe excluirse.
  Criterio robusto: recoger `%T` con `1e-6 < v ≤ 200` que tengan un vecino `−99999.0`.
- Verificado: 4 series de `Test2`, **60/60 puntos coinciden exactos** con el reporte.
- **NO se almacenan los tiempos explícitos** por punto (los tiempos del reporte se
  infieren; p. ej. ~2 s de intervalo). *(A verificar por el experto.)*

### 6.6 Modo **CUANTIFICACIÓN** (type=4) — **VALIDADO**

- λ = `f32 @ 0x34`.
- **Concentraciones de estándares** (las no nulas): `f32 @ 0x110, 0x114, 0x118`
  (verificado `0.05, 0.5, 1.0`; el estándar 1 = 0 es implícito).
- **Absorbancias de estándares** (¡ya **como absorbancia**, no %T!):
  `f32 @ 0x15C, 0x160, 0x164, 0x168`
  (verificado `0.001, 0.6068, 2.4858, 2.947` ⇒ reporte `0.00, 0.61, 2.49, 2.95`).
- **Lectura de la muestra**: **el último `float32`**, en **%T**
  (verificado `%T=16.8452 ⇒ A=0.774`).
- ⚠️ **Asimetría:** los estándares se guardan **como absorbancia**; la muestra
  **como %T**. Confirmar con más muestras.

### 6.7 Convenciones transversales

1. **Las lecturas son %Transmitancia** (0 … ~200), salvo las absorbancias de
   estándares de Cuantificación (§6.6).
2. **Absorbancia = −log10(%T/100)**, sin recortar.
3. **Saturación — hallazgo validado:** el `.JWB` guarda el %T **real**; el
   **display/reporte recorta (clampa) la absorbancia a 3.000**. Al comparar
   espectro (`Esp-…` 190–900) los **107 puntos** que difieren del reporte son
   **los 107** donde el reporte marca `3.000`. ⇒ La diferencia es del *display*,
   no del dato.
4. **Para reproducir los cálculos del display** (p. ej. `A1/A2` de multi-λ), hay
   que **clampar a 3.000 primero**: con eso `A1/A2 = −9.973` y `A1−A2 = 3.301`
   (idénticos al reporte).
5. Centinela de "celda vacía" en arrays: `−1.0`. Centinela de separación en
   cinética: `−99999.0`.

---

## 7. `.TXT` — Reporte impreso (lo que el manual llama "CSV")

**No es CSV delimitado**: es un **reporte de texto formateado** en español,
codificación **CP1252**.

### 7.1 Estructura general

Un archivo puede contener **varios registros** consecutivos (p. ej. 4 corridas de
cinética, o un consolidado). Cada registro es:

```
========================================        ← línea separadora (sólo '=')
<CABECERA: líneas "Etiqueta: ,valor" o "Etiqueta:,valor">
========================================
<BLOQUE DE DATOS según el modo>
```

Los separadores son líneas compuestas **sólo** de `=`. La cabecera va entre el
1.º y 2.º separador; los datos, entre el 2.º y el 3.º (o EOF).

### 7.2 Detección de modo (por la 1.ª línea de cabecera)

| Texto de la 1.ª línea | Modo |
|---|---|
| `Modo Fotometría...` | Fotometría |
| `Modo Espectro...` | Espectro |
| `Modo Cinética...` | Cinética |
| `Modo Longitud de onda...` | Multi-longitud |
| `Modo Cuantificación...` | Cuantificación |

### 7.3 Bloques de datos por modo (observados)

- **Fotometría:** cabecera de datos `Id,Abs,T,Hora` → filas `002,3.000,0.0,11:25:29`.
- **Espectro:** `Longitud de onda,Absorbancia` → pares `400.0,-0.001` al
  **intervalo de gráfico** (p. ej. 1.0 nm) — *nota: el `.JWB` tiene más
  resolución (0.1 nm); el reporte sale al intervalo de gráfico*.
- **Multi-longitud:** línea de lote `001,<fecha>` → celdas `1-,400.0nm,A1,-0.000`
  → cálculo `A1/A2,22.347,A1-A2,-0.000`.
- **Cinética:** `Lote ...:-` → `Hora (  segundos),Celda,N` → filas `0,-0.001`.
- **Cuantificación:** en la cabecera van los estándares
  (`Std 1:,   0.00,Resultado 1:,   0.00`) y `Ajuste de curva` → datos
  `Id,Abs,Conc,Fecha y hora` → `001, 0.774,   0.09mM,12:54:07`
  (la concentración **incluye unidades** en la cadena: `mM`, `ppm`, …).

### 7.4 Etiquetas de cabecera frecuentes (ES)

`ID instrumento`, `Nombre de usuario` / `ID de usuario`, `Método`, `ID de lote`,
`Longitud de onda`, `WRango de longitud de onda`, `Intervalo de gráfico`,
`Modo de medición`, `Seguridad de método`, `Escala automática`,
`Mínimo eje Y`, `Máximo eje Y`, `última calibración`, `Guardar automáticamente`,
`Estándar cal. concentración`, `Factor de concentración`, `Tiempo de ejecución`,
`Ajuste de curva`, `Número de estánd. usados`.

---

## 8. Validación realizada (método: `decode(.JWB) ≡ reporte(.TXT)`)

Se emparejó cada `.JWB` con el reporte **de la misma medición** (por modo + fecha/hora +
longitudes de onda) y se comparó valor a valor.

| Modo | Archivo `.JWB` | Reporte | Resultado |
|---|---|---|---|
| Espectro | `323BE947` (190–900 nm) | `3 LEC` | Exacto en no saturados; **107/107** diferencias = clamp 3.000 |
| Espectro | `323BD8FF` (400–500 nm) | `3A` | 94/101 dentro de ±0.002 (blanco) |
| Multi-λ | `323BEA26` (300/330/400/600) | `4 LEC` | λ exactas; A2/A3/A4 exactas; `A1/A2=−9.973`, `A1−A2=3.301` |
| Fotometría | `323BE7BA` (330 nm) | `1 LEC` | Saturado (%T=0) — formato confirmado |
| Fotometría | `323BCBA4` (550 nm) | `INTRODUZ` | %T=100 ⇒ A=0.0 |
| Cinética | `323BFDC8/…DF4/…E19/…E3F` | `TEST2` | **60/60 puntos exactos** |
| Cuantificación | `323BFC6F` (450 nm) | `TEST1` | Estándares + muestra (A=0.774) + C°=0.09 mM exactos |

**Conclusión:** el pipeline `decode(.JWB) ≡ reporte` quedó demostrado en los 5 modos.

---

## 9. Aspectos NO verificados / preguntas abiertas (¡importante!)

1. **Cabecera 0x00–0x33**: sólo se identificó `20.0` en `0x00`. El resto de
   parámetros de método (seguridad, lote, flags, factor…) **no está mapeado**.
2. **`type` heurístico**: sin el `.JWX`, distinguir el modo de un `.JWB` es
   heurístico y puede fallar; el modo fiable viene del `.JWX`.
3. **Fotometría**: sólo se observaron casos con **una** lectura. Con réplicas /
   multi-celda, ¿cambia el bloque?, ¿hay más de un `float32` al final?
4. **Cinética**: los **tiempos** por punto no están explícitos; ¿se derivan de un
   campo de la cabecera (p. ej. intervalo) o solo del reporte?
5. **Cuantificación**: la asimetría estándares(Abs) vs muestra(%T) y el punto de
   corte entre ambas zonas deben confirmarse con más muestras.
6. **Escala**: se asumió barrido a **0.1 nm** para espectro por `N=(Δλ)/0.1+1`.
   ¿El paso podría ser configurable y romper esta fórmula?
7. **Varios lotes/muestras por método**: ¿los `.JWB` de resultado crecen o cambian
   de layout cuando hay más de una muestra? (Se vio 1 `.JWB` por muestra.)
8. **Otros accesorios** (peltier, sipper, multi-celda de 8) podrían alterar la
   cabecera. **No probado.**
9. **`type` fuera de 0–4**: no observado; ¿existen otros?

---

## 10. Cómo reproducir / verificar

1. Copiar una **tarjeta** completa (`.JWB` + `.JWX` + `.JWU`) y, del mismo ensayo,
   su reporte `.TXT`.
2. Inspección binaria: `xxd archivo.JWB` y buscar:
   - en `0x34`: la 1.ª longitud de onda (float LE);
   - al final: el bloque de `float32` (lecturas).
   - Lectura de un float en un offset `o`: `struct.unpack('<f', datos[o:o+4])`.
3. Derivar `A = −log10(%T/100)` y comparar con el `.TXT` (a 3 decimales; clampa a 3.000).
4. Suite automatizada de referencia (golden tests) en el proyecto:
   - `tests/test_parser_jwb.py`, `tests/test_parser_txt.py`, `tests/test_fase1.py`,
     `tests/test_fase2.py` (42 pruebas; casos reales versionados en `tests/data/`).

---

## 11. Glosario de etiquetas (ES → EN)

| ES (equipo) | EN | ES (equipo) | EN |
|---|---|---|---|
| Fotometría | Photometrics | Longitud de onda | Wavelength |
| Espectro | Spectrum | Intervalo de gráfico | Plot interval |
| Cinética | Kinetics | Modo de medición | Measurement mode |
| Cuantificación | Quantitation | Lote | Batch |
| Multi-longitud | Multi-Wavelength | Absorbancia | Absorbance |
| Método | Method | Transmitancia | Transmittance (%T) |
| Estándar | Standard | Ajuste de curva | Curve fit |
| Seguridad de método | Method security | Guardar automáticamente | Auto Log |

---

## 12. Anexo — archivos de muestra usados en la validación

Tarjeta de referencia (`…\Jenway6705\Archivos prueba\Nuevos x2\`):

- Índice/usuarios: `SUMMARYP/S/M/K/Q.JWX`, `USERSINF.JWU`
- Espectro: `323BE947.JWB` (190–900), `323BDC04.JWB` (400–500)
- Multi-λ: `323BEA26.JWB`, `323BDC8B.JWB`
- Cinética: `323BFDC8.JWB`, `323BFDF4.JWB`, `323BFE19.JWB`, `323BFE3F.JWB`
- Cuantificación: `323BFC6F.JWB`, `323BEBAF.JWB`, `323BDE31.JWB`
- Fotometría: `323BE7BA.JWB`, `323BCBA4.JWB`
- Reportes: `1..5 LEC.TXT`, `TEST1.TXT`, `TEST2.TXT`, `3A/2D/4A/5A.TXT`, `INTRODUZ.TXT`

---

*Fin del documento.*
