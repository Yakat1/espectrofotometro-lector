# -*- coding: utf-8 -*-
"""Banco de pruebas serie para el espectrofotometro Jenway 6705.

PARA QUE SIRVE
--------------
El fabricante no documenta ningun protocolo de control remoto para el 6705:
el manual solo describe USB (transferencia de ficheros a la tarjeta),
Centronics (impresora) y salida analogica.  El unico puerto "de datos" que
aparece en Windows es un puente FTDI (VID_0403:PID_6001) que el software
original usaba para mover ficheros, no para dar ordenes.

Por tanto, la unica via para saber si el equipo puede "hablar" es dejarle
hablar: abrir el puerto, barrer las configuraciones clasicas de laboratorio,
enviar sondas BENIGNAS y registrar TODO byte que entre o salga, tanto de ida
como de vuelta, en hexadecimal y en texto.

DISENO
------
La logica no depende de la GUI ni de pyserial: el abridor de puerto es un
parametro inyectable (``abrir=``), de modo que el barrido completo se puede
probar SIN hardware usando :class:`PuertoSimulado`.  Ver
``tests/test_escaneo_serie.py``.

SEGURIDAD
---------
Las sondas de :data:`SONDAS` solo piden identificacion o hacen handshake
(ENQ, CR, LF, ``*IDN?``...).  Ninguna ordena borrar, formatear ni reiniciar
nada; hay una prueba automatica que lo verifica.

USO
---
    from jenway67 import escaner_serie as es
    es.puertos_disponibles()
    info = es.escanear(puerto="COM3")
    print(es.informe_texto(info))
    es.guardar(info, carpeta="maestro/_escaneo_serie")
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime

try:  # pyserial es opcional: el modulo debe importarse (y probarse) sin el
    import serial
    from serial.tools import list_ports as _list_ports

    HAY_PYSERIAL = True
except Exception:  # pragma: no cover
    serial = None
    _list_ports = None
    HAY_PYSERIAL = False


# ---------------------------------------------------------------------------
# Configuraciones de puerto
# ---------------------------------------------------------------------------
#: Ajustes "de laboratorio" clasicos, probados primero (los mas probables).
COMUNES = (
    (9600, 8, "N", 1),
    (9600, 7, "E", 1),
    (9600, 7, "O", 1),
    (9600, 8, "N", 2),
    (19200, 8, "N", 1),
    (4800, 8, "N", 1),
    (4800, 7, "E", 1),
    (2400, 8, "N", 1),
    (1200, 8, "N", 1),
    (38400, 8, "N", 1),
    (57600, 8, "N", 1),
    (115200, 8, "N", 1),
    (9600, 8, "E", 1),
    (9600, 8, "O", 1),
    (9600, 7, "N", 1),
)

BAUDIOS = (300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)


@dataclass(frozen=True)
class Config:
    """Una configuracion de puerto serie (velocidad, trama y control de flujo).

    ``lineas="off"`` abre el puerto y BAJA DTR y RTS: algunos instrumentos
    rechazan hablar si el PC mantiene esas lineas activas.
    """

    baudios: int = 9600
    bits: int = 8
    paridad: str = "N"
    stop: int = 1
    flujo: str = "no"
    lineas: str = "on"

    @property
    def etiqueta(self) -> str:
        etiqueta = "%d %d%s%d" % (self.baudios, self.bits, self.paridad, self.stop)
        if self.flujo != "no":
            etiqueta += " " + self.flujo
        if self.lineas != "on":
            etiqueta += " sin-DTR/RTS"
        return etiqueta

    def kwargs(self) -> dict:
        """Argumentos para ``serial.Serial``."""
        if not HAY_PYSERIAL:  # pragma: no cover
            return {"baudrate": self.baudios}
        paridad = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
        }[self.paridad]
        return {
            "baudrate": self.baudios,
            "bytesize": serial.SEVENBITS if self.bits == 7 else serial.EIGHTBITS,
            "parity": paridad,
            "stopbits": serial.STOPBITS_TWO if self.stop == 2 else serial.STOPBITS_ONE,
            "rtscts": self.flujo == "rtscts",
            "xonxoff": self.flujo == "xonxoff",
            "dsrdtr": self.flujo == "dsrdtr",
        }


def configuraciones(completo: bool = False, flujo: str = "no") -> list:
    """Lista de configuraciones a probar.

    ``completo=False`` -> solo las clasicas de laboratorio (rapido, ~15).
    ``completo=True``  -> producto cartesiano de velocidad x trama, mas una
    segunda pasada con handshake RTS/CTS y con DTR/RTS bajados.
    """
    lista, vistos = [], set()

    def agrega(config):
        if config.etiqueta not in vistos:
            vistos.add(config.etiqueta)
            lista.append(config)

    for tupla in COMUNES:
        agrega(Config(*tupla, flujo=flujo))
    if not completo:
        return lista
    for baudios in BAUDIOS:
        for bits in (7, 8):
            for paridad in ("N", "E", "O"):
                for stop in (1, 2):
                    agrega(Config(baudios, bits, paridad, stop, flujo=flujo))
    # Segunda pasada sobre las mas probables: por si el equipo exige handshake
    # o rechaza que el PC mantenga DTR/RTS activos.
    for tupla in COMUNES[:6]:
        agrega(Config(*tupla, flujo="rtscts"))
        agrega(Config(*tupla, lineas="off"))
    return lista


# ---------------------------------------------------------------------------
# Sondas benignas
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Sondas: tres juegos, porque no es lo mismo PREGUNTAR que CAMBIAR ALGO
# ---------------------------------------------------------------------------
#: ``(nombre, bytes, descripcion)``.
#:
#: * :data:`SONDAS_RAPIDAS`   — consultas puras, las de siempre.
#: * :data:`SONDAS_AMPLIADAS` — consultas de otros protocolos (Jenway clasico,
#:   SCPI, tramas STX/ETX, handshakes ASCII, wake-ups).
#: * :data:`SONDAS_ESTADO`    — las que cambian algo, aunque sea poco, o que
#:   arrancan un modo de transferencia.  **No se envian** salvo que se pidan.
#:
#: La separacion no es cosmetica: permite seguir afirmando "el juego por defecto
#: solo pregunta" con una prueba automatica detras.
SONDAS_RAPIDAS = (
    ("ENQ", b"\x05", "ASCII ENQ: peticion de atencion (handshake clasico)"),
    ("CR", b"\r", "retorno de carro suelto"),
    ("LF", b"\n", "salto de linea suelto"),
    ("CRLF", b"\r\n", "retorno de carro + salto de linea"),
    ("NUL", b"\x00", "byte nulo"),
    ("ESC", b"\x1b", "ASCII ESC"),
    ("XON", b"\x11", "ASCII XON / DC1"),
    ("IDN", b"*IDN?\r", "consulta de identificacion estilo SCPI"),
    ("INT", b"?\r", "consulta corta generica"),
    ("VER", b"V\r", "peticion de version generica"),
    ("STX", b"\x02*IDN?\x03", "IDN enmarcado con STX/ETX"),
)

SONDAS_AMPLIADAS = SONDAS_RAPIDAS + (
    # -- Protocolo Jenway/Bibby de generaciones anteriores (63xx/73xx): eran de
    #    UNA letra + CR.  El 6705 no tiene RS-232, pero el FTDI si es un UART.
    ("STA", b"S\r", "status: comando clasico Jenway (series 63xx/73xx)"),
    ("RDG", b"R\r", "reading: pedir lectura activa (Jenway legacy)"),
    ("TYP", b"T\r", "type: pedir tipo/modelo (variante de V)"),
    ("MOD", b"M\r", "mode: pedir modo actual"),
    ("WAV", b"W\r", "wavelength: pedir longitud de onda actual"),
    ("DAT", b"D\r", "data: pedir dato actual"),
    # -- SCPI mas completo (el 6705 no documenta SCPI: barato de descartar)
    ("SYS", b"*TST?\r", "SCPI autotest query"),
    ("OPC", b"*OPC?\r", "SCPI operation complete query"),
    ("STB", b"*STB?\r", "SCPI status byte query"),
    ("ESE", b"*ESE?\r", "SCPI event status enable query"),
    # -- Tramas STX/cmd/ETX (estilo Shimadzu/PerkinElmer)
    ("HELLO", b"\x02\x30\x03", "STX + '0' (poll) + ETX"),
    ("STAT2", b"\x02S\x03", "STX + 'S' (status) + ETX"),
    # -- Handshakes ASCII genericos
    ("JNWY", b"JENWAY\r", "eco del nombre del fabricante como handshake"),
    ("CONN", b"CONNECT\r", "peticion de conexion generica"),
    ("HELO", b"HELLO\r", "saludo generico"),
    ("LIST", b"LIST\r", "listar archivos (si hay protocolo de transferencia)"),
    ("DIR", b"DIR\r", "directorio (protocolo de ficheros)"),
    ("READY", b"READY\r", "status ready check"),
    # -- Wake-ups
    ("2CR", b"\r\r", "doble retorno de carro (wake-up)"),
    ("3CR", b"\r\r\r", "triple retorno de carro"),
)

#: Sondas que **cambian estado** (aunque sea poco) o arrancan un modo de
#: transferencia.  Requieren pedirlo expresamente.
#:
#: Las de XMODEM (NAK, C, SOH, ACK, CAN) son la hipotesis con mas mecanismo
#: detras: el software OEM movia **ficheros** por este puerto y XMODEM/YMODEM es
#: la forma clasica de mover ficheros por un serie en un instrumento de esa
#: epoca.  El disparador se repite (``NAK x3``, ``C x3``) porque los receptores
#: XMODEM ignoran las repeticiones y arrancan con la primera.
SONDAS_ESTADO = (
    ("NAK3", b"\x15" * 3, "XMODEM NAK x3: pedir transmision"),
    ("CRCC", b"C" * 3, "XMODEM-CRC: inicio con CRC (C repetida)"),
    ("SOH", b"\x01", "XMODEM SOH: inicio de bloque"),
    ("ACK", b"\x06", "ACK generico"),
    ("CAN", b"\x18", "XMODEM CAN: cancelar"),
    ("CLS", b"*CLS\r", "SCPI clear status (solo limpia banderas)"),
    ("ATT", b"AT\r", "AT (por descartar: el FT232R no interpreta AT)"),
)

#: Compatibilidad: ``SONDAS`` es el juego de consultas rapidas de siempre.
SONDAS = SONDAS_RAPIDAS

#: Palabras que NUNCA deben aparecer en una sonda de CONSULTA (red de seguridad).
PALABRAS_PROHIBIDAS = (
    "FORMAT",
    "ERASE",
    "DELETE",
    "*RST",
    "RESET",
    "CLEAR",
    "INIT",
    "DOWNLOAD",
    "UPDATE",
)


def sondas_benignas() -> bool:
    """True si ningun juego de CONSULTAS lleva una orden potencialmente destructiva."""
    for juego in (SONDAS_RAPIDAS, SONDAS_AMPLIADAS):
        for _nombre, carga, _desc in juego:
            texto = carga.decode("latin-1").upper()
            for mala in PALABRAS_PROHIBIDAS:
                if mala in texto:
                    return False
    return True


def sondas_de_bytes() -> tuple:
    """Barrido sistematico de **1 byte**: 0x00..0xFF, una sonda por byte.

    Es lo mas sistematico que se puede hacer (cubre de golpe el espacio de
    ordenes de un byte, donde caerian las clasicas de una letra), pero es tambien
    el unico juego que puede topar con una orden desconocida de un byte, asi que
    no se envia salvo que se pida.
    """
    return tuple(("%02X" % b, bytes([b]), "barrido de 1 byte (0x%02X)" % b)
                 for b in range(256))


# ---------------------------------------------------------------------------
# Sondas de CONTROL: distinguir una respuesta de un artefacto
# ---------------------------------------------------------------------------
# En la primera corrida real TODAS las sondas devolvieron el mismo byte -- 0xFF
# con el puerto a 8 bits de datos y 0x7F con el puerto a 7 -- y el numero de
# bytes recibidos no dependia de lo que se preguntaba.  Eso no es un protocolo:
# es la firma de un artefacto de recepcion.  Este juego lo comprueba:
#
#   * mismo TAMANO, distinto CONTENIDO -> una respuesta de verdad cambia
#   * mismo CONTENIDO, distinto TAMANO -> si lo recibido crece con lo enviado,
#                                         lo esta fabricando nuestra transmision
#   * relleno inerte                   -> ningun equipo protocolario contesta
#                                         a 20 bytes de basura con algo util
SONDAS_CONTROL = (
    ("CTL-TAM-A", b"AAAAAAAA\r", "control: 9 B con 'A'"),
    ("CTL-TAM-B", b"ZZZZZZZZ\r", "control: 9 B con 'Z' (mismo tamano, otro contenido)"),
    ("CTL-TAM-C", b"*IDN?\r\r\r\r", "control: 9 B y SI son una consulta (*IDN? + CR)"),
    ("CTL-CORTO", b"A\r", "control: 2 B, el mismo caracter"),
    ("CTL-LARGO", b"AAAAAAAAAAAAAAAAAAAAAAAAA\r", "control: 26 B, el mismo caracter"),
    ("CTL-INERTE", b"UUUUUUUUUUUUUUUUUUUU", "control: 20 B de relleno inerte"),
)


def juego_de_sondas(nivel: str = "rapidas", permitir_estado: bool = False,
                    barrido_bytes: bool = False) -> tuple:
    """Sondas a enviar segun el nivel pedido.

    ``nivel``: ``rapidas`` (11 consultas) o ``ampliadas`` (+21 de otros
    protocolos).  ``permitir_estado`` anade :data:`SONDAS_ESTADO` y
    ``barrido_bytes`` anade las 256 del barrido de 1 byte.
    """
    nivel = (nivel or "rapidas").lower()
    if nivel == "rapidas":
        sondas = list(SONDAS_RAPIDAS)
    elif nivel == "ampliadas":
        sondas = list(SONDAS_AMPLIADAS)
    elif nivel == "control":
        # El juego de control se basta solo: no se le anaden estado ni barrido.
        return tuple(SONDAS_CONTROL)
    else:
        raise ValueError(
            "Nivel de sondas '%s' no valido (rapidas|ampliadas|control)." % nivel)
    if permitir_estado:
        sondas += list(SONDAS_ESTADO)
    if barrido_bytes:
        sondas += list(sondas_de_bytes())
    return tuple(sondas)


# ---------------------------------------------------------------------------
# Utilidades de volcado
# ---------------------------------------------------------------------------
def volcado_hex(datos: bytes) -> str:
    """``b'\\x05A'`` -> ``'05 41'`` (facil de leer en un log)."""
    if not datos:
        return ""
    return " ".join("%02X" % b for b in datos)


def volcado_legible(datos: bytes) -> str:
    """Byte a byte como texto, con puntos para los no imprimibles."""
    if not datos:
        return ""
    return "".join(chr(b) if 32 <= b < 127 else "." for b in datos)


# ---------------------------------------------------------------------------
# Puerto simulado (para pruebas y demostracion sin instrumento)
# ---------------------------------------------------------------------------
class PuertoSimulado:
    """Puerto de mentira con la minima interfaz que usa el escaner.

    ``modo``:
      * ``"silencio"`` -> nunca contesta (escenario mas probable).
      * ``"eco"``      -> devuelve exactamente lo recibido (lazo/eco del chip).
      * ``"idn"``      -> contesta a las sondas de identificacion.
    """

    RESPUESTA = b"JENWAY,6705,SN000000,1.64\r\n"

    def __init__(self, modo: str = "silencio") -> None:
        self.modo = modo
        self.escrito = bytearray()
        self._cola = bytearray()
        self.timeout = 0.0
        self.cerrado = False
        self.dtr = True
        self.rts = True
        self.cts = False
        self.dsr = False
        self.ri = False
        self.cd = False

    @property
    def in_waiting(self) -> int:
        return len(self._cola)

    def write(self, datos) -> int:
        datos = bytes(datos)
        self.escrito += datos
        if self.modo == "eco":
            self._cola += datos
        elif self.modo == "idn" and datos.rstrip(b"\r\n") in (b"*IDN?", b"?", b"V"):
            self._cola += self.RESPUESTA
        return len(datos)

    def read(self, n: int = 1) -> bytes:
        if not self._cola:
            time.sleep(0.002)
            return b""
        datos = bytes(self._cola[:n])
        del self._cola[:n]
        return datos

    def reset_input_buffer(self) -> None:
        self._cola.clear()

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.cerrado = True


# ---------------------------------------------------------------------------
# Apertura / lectura
# ---------------------------------------------------------------------------
class ErrorPuerto(Exception):
    """No se pudo abrir el puerto (ocupado, inexistente, sin permisos...)."""


def _abrir_real(puerto: str, config: Config, timeout: float = 0.05):
    if not HAY_PYSERIAL:  # pragma: no cover
        raise ErrorPuerto("pyserial no esta instalado")
    return serial.Serial(
        port=puerto, timeout=timeout, write_timeout=1.0, **config.kwargs()
    )


def _cerrar(puerto) -> None:
    try:
        puerto.close()
    except Exception:
        pass


def _abrir_y_preparar(abrir, puerto: str, config: Config):
    """Abre el puerto y aplica los ajustes que van DESPUES de abrir.

    Con ``lineas="off"`` se bajan DTR y RTS: hay instrumentos que no contestan
    si el PC mantiene esas lineas activas.
    """
    conexion = abrir(puerto, config)
    if config.lineas == "off":
        for nombre in ("dtr", "rts"):
            try:
                setattr(conexion, nombre, False)
            except Exception:
                pass
    return conexion


def estado_lineas(puerto) -> dict:
    """Estado de las lineas de control (None si no se puede consultar)."""
    salida = {}
    for nombre in ("dtr", "rts", "cts", "dsr", "ri", "cd"):
        try:
            salida[nombre] = bool(getattr(puerto, nombre))
        except Exception:
            salida[nombre] = None
    return salida


def leer_hasta(puerto, segundos: float) -> bytes:
    """Lee todo lo que llegue durante ``segundos`` y lo devuelve."""
    fin = time.monotonic() + max(0.0, float(segundos))
    datos = bytearray()
    while True:
        restante = fin - time.monotonic()
        if restante <= 0:
            break
        pendientes = int(getattr(puerto, "in_waiting", 0) or 0)
        if pendientes > 0:
            datos += puerto.read(pendientes)
            continue
        trozo = puerto.read(1)
        if trozo:
            datos += trozo
        else:
            time.sleep(min(0.005, max(0.0, restante)))
    return bytes(datos)


# ---------------------------------------------------------------------------
# Tiempos de espera
# ---------------------------------------------------------------------------
# Cuanto se escucha por defecto, cuanto como maximo cuando algo empieza a
# llegar, cuanto silencio se tolera entre bloques, y cuanto se espera tras
# abrir el puerto antes de la primera sonda.
VENTANA_POR_DEFECTO = 0.4
VENTANA_LARGA_POR_DEFECTO = 90.0
SILENCIO_ENTRE_BLOQUES = 0.3
ASENTAMIENTO_POR_DEFECTO = 1.5

_UNIDADES = {
    "ms": 0.001,
    "s": 1.0,
    "seg": 1.0,
    "segs": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "h": 3600.0,
}
_PATRON_TIEMPO = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+)")


def parsear_tiempo(texto) -> float:
    """Interpreta un tiempo CON su unidad: 0.4, 90s, 1m30s, 1.5min, 500ms.

    Un numero suelto se toma como SEGUNDOS.  Existe porque "0.4" no dice nada:
    se puede leer como segundos o como minutos, y no es lo mismo (0.4 s es una
    espera normal; 0.4 min son 24 s).
    """
    if isinstance(texto, (int, float)):
        return float(texto)
    limpio = str(texto).strip().lower().replace(",", ".")
    if not limpio:
        raise ValueError("tiempo vacio")
    if _PATRON_TIEMPO.search(limpio) and _PATRON_TIEMPO.sub("", limpio).strip() == "":
        total = 0.0
        for numero, unidad in _PATRON_TIEMPO.findall(limpio):
            if unidad not in _UNIDADES:
                raise ValueError(
                    "unidad desconocida %r en %r (usa ms, s, m/min, h)" % (unidad, texto)
                )
            total += float(numero) * _UNIDADES[unidad]
        return total
    try:
        return float(limpio)
    except ValueError:
        raise ValueError(
            "no entiendo el tiempo %r: usa 0.4 (segundos), 90s, 1m30s, 500ms" % (texto,)
        )


def leer_hasta_que_calle(
    puerto, primera: float, larga: float, silencio: float = SILENCIO_ENTRE_BLOQUES
) -> bytes:
    """Escucha ``primera`` segundos; si ALGO llego, sigue hasta que la linea calle.

    Responde a "¿de verdad contesta tan rapido un equipo de esta epoca?": una
    CONSULTA se contesta en milisegundos, pero una OPERACION (volcar un espectro
    de 7101 puntos) puede tardar minuto y medio.  Con esta ventana adaptativa un
    caso silencioso cuesta solo ``primera``, y una respuesta larga no se corta a
    la mitad.  Si la linea se queda callada ``silencio`` segundos, se da por
    terminada; y nunca se escucha mas de ``larga`` segundos.
    """
    datos = bytearray(leer_hasta(puerto, primera))
    if not datos:
        return b""
    fin = time.monotonic() + max(float(larga), float(primera))
    silencio = max(0.05, float(silencio))
    while True:
        restante = fin - time.monotonic()
        if restante <= 0:
            break
        trozo = leer_hasta(puerto, min(silencio, restante))
        if not trozo:
            break  # la linea lleva ``silencio`` segundos callada
        datos += trozo
    return bytes(datos)


# ---------------------------------------------------------------------------
# Inventario de puertos
# ---------------------------------------------------------------------------
def puertos_disponibles() -> list:
    """Puertos serie presentes, con VID/PID cuando el sistema los da."""
    if not HAY_PYSERIAL:
        return []
    salida = []
    for puerto in _list_ports.comports():
        vid_pid = ""
        if getattr(puerto, "vid", None) is not None:
            vid_pid = "%04X:%04X" % (puerto.vid, puerto.pid)
        salida.append(
            {
                "puerto": puerto.device,
                "descripcion": puerto.description or "",
                "fabricante": puerto.manufacturer or "",
                "vid_pid": vid_pid,
                "hwid": puerto.hwid or "",
            }
        )
    return salida


def elegir_puerto(inventario: list, preferido: str = "") -> str:
    """Elige puerto: el pedido, o el primer FTDI (0403), o el primero."""
    if preferido:
        return preferido
    for dato in inventario:
        if dato.get("vid_pid", "").upper().startswith("0403"):
            return dato["puerto"]
    return inventario[0]["puerto"] if inventario else ""


# ---------------------------------------------------------------------------
# Escucha pasiva y sondeo
# ---------------------------------------------------------------------------
def escuchar(puerto, segundos: float, muestreo: float = 0.5, progreso=None) -> dict:
    """Escucha sin enviar nada: ¿el equipo habla por su cuenta?

    Util para pulsar PRINT en el instrumento o meter la tarjeta mientras corre.
    """
    inicio = time.monotonic()
    datos = bytearray()
    instantaneas = []
    while time.monotonic() - inicio < segundos:
        trozo = leer_hasta(puerto, muestreo)
        if trozo:
            datos += trozo
        instantaneas.append(
            {"t": round(time.monotonic() - inicio, 2), "lineas": estado_lineas(puerto)}
        )
        if progreso:
            progreso(time.monotonic() - inicio, segundos, len(datos))
    return {
        "segundos": round(time.monotonic() - inicio, 2),
        "datos": bytes(datos),
        "muestras_lineas": instantaneas,
    }


def sondear_config(
    puerto,
    config: Config,
    sondas=None,
    ventana: float = VENTANA_POR_DEFECTO,
    ventana_larga: float = 0.0,
) -> list:
    """Envia cada sonda en una configuracion y recoge la respuesta.

    ``ventana`` es lo que se escucha siempre.  Si ``ventana_larga`` es mayor, la
    espera se AMPLIA --solo-- cuando algo empieza a llegar: asi un caso
    silencioso no cuesta mas y una respuesta lenta no se corta a la mitad.
    """
    sondas = SONDAS if sondas is None else sondas
    resultados = []
    for nombre, carga, descripcion in sondas:
        try:
            puerto.reset_input_buffer()
        except Exception:
            pass
        try:
            puerto.write(carga)
            puerto.flush()
        except Exception as error:
            resultados.append(
                Resultado(
                    config=config.etiqueta,
                    sonda=nombre,
                    enviado_hex=volcado_hex(carga),
                    recibido_hex="",
                    texto="",
                    n_bytes=0,
                    eco=False,
                    descripcion=descripcion,
                    error=str(error),
                )
            )
            continue
        inicio = time.monotonic()
        ampliada = False
        if ventana_larga > ventana:
            recibido = leer_hasta_que_calle(puerto, ventana, ventana_larga)
            # Solo cuenta como ampliada si de verdad llego algo: si no, la
            # espera extra fue solo la granularidad del puerto.
            ampliada = bool(recibido)
        else:
            recibido = leer_hasta(puerto, ventana)
        espera = time.monotonic() - inicio
        # Un eco exacto de lo enviado NO es una respuesta del equipo: seria el
        # lazo del propio chip o un eco del instrumento.  Hay que distinguirlo
        # para no enganarnos.
        eco = bool(recibido) and recibido == bytes(carga)
        resultados.append(
            Resultado(
                config=config.etiqueta,
                sonda=nombre,
                enviado_hex=volcado_hex(carga),
                recibido_hex=volcado_hex(recibido),
                texto=volcado_legible(recibido),
                n_bytes=len(recibido),
                eco=eco,
                descripcion=descripcion,
                espera_s=round(espera, 3),
                ampliada=ampliada,
            )
        )
    return resultados


@dataclass
class Resultado:
    config: str
    sonda: str
    enviado_hex: str
    recibido_hex: str
    texto: str
    n_bytes: int
    eco: bool
    descripcion: str = ""
    error: str = ""
    espera_s: float = 0.0  # segundos que se escucho de verdad esta sonda
    ampliada: bool = False  # la escucha se amplio porque empezo a llegar algo


# ---------------------------------------------------------------------------
# ¿Respuesta de verdad, eco, o artefacto de recepcion?
# ---------------------------------------------------------------------------
def bits_de_etiqueta(etiqueta: str) -> int:
    """Bits de datos de una etiqueta tipo ``'9600 8N1'`` (0 si no se entiende)."""
    try:
        return int(str(etiqueta).split()[1][0])
    except Exception:
        return 0


def es_todo_a_uno(recibido_hex: str, bits: int) -> bool:
    """True si todos los bytes son "todos los bits de datos a 1".

    ``0xFF`` con 8 bits de datos, ``0x7F`` con 7.  Es la firma de un artefacto de
    recepcion -- la linea en reposo (alta) y el receptor creyendo ver un bit de
    arranque -- y NO contenido que venga del equipo.  Se ve en la corrida real:
    la MISMA linea devuelve FF u 7F segun como la tenga configurada NUESTRO
    puerto, que es algo que un instrumento no puede decidir.
    """
    if not recibido_hex:
        return False
    objetivo = 0x7F if bits == 7 else 0xFF
    try:
        return all(int(byte, 16) == objetivo for byte in str(recibido_hex).split())
    except ValueError:
        return False


def clasificar(resultados: list) -> dict:
    """Separa lo observado en reales / repetidos / artefactos / ecos.

    * **artefacto**: bytes "todos a uno" bajo nuestra propia configuracion.
    * **repetido**: la MISMA respuesta a sondas de contenido DISTINTO (>=3).
      Nada del equipo puede depender de lo que preguntamos si contesta igual a
      preguntas diferentes.
    * **eco**: retorno exacto de lo enviado (lazo del chip).
    """
    reales, ecos, artefactos = [], [], []
    for fila in resultados:
        if fila.error or not fila.n_bytes:
            continue
        if fila.eco:
            ecos.append(fila)
            continue
        if es_todo_a_uno(fila.recibido_hex, bits_de_etiqueta(fila.config)):
            artefactos.append(fila)
            continue
        reales.append(fila)

    por_valor = {}
    for fila in reales:
        por_valor.setdefault((fila.config, fila.recibido_hex), set()).add(fila.enviado_hex)
    sospechosos = {clave for clave, enviados in por_valor.items() if len(enviados) >= 3}
    return {
        "reales": [f for f in reales if (f.config, f.recibido_hex) not in sospechosos],
        "repetidos": [f for f in reales if (f.config, f.recibido_hex) in sospechosos],
        "artefactos": artefactos,
        "ecos": ecos,
    }


# ---------------------------------------------------------------------------
# Veredicto
# ---------------------------------------------------------------------------
def veredicto(resultados: list, bytes_pasivos: int = 0) -> str:
    """Interpretacion honesta de lo observado (sin optimismo).

    Distingue respuesta de verdad, eco y ARTEFACTO.  Lo ultimo importa: en la
    primera corrida real el banco anuncio "el equipo habla" con 88 lecturas que
    eran, casi con seguridad, ruido de nuestra propia transmision.
    """
    errores = [r for r in resultados if r.error]
    if errores and not resultados:
        return "ERROR DE ESCRITURA: %s" % errores[0].error
    partes = clasificar(resultados)
    reales, repetidos = partes["reales"], partes["repetidos"]
    artefactos, ecos = partes["artefactos"], partes["ecos"]
    if reales:
        detalle = "; ".join(
            "%s %s -> %s" % (r.config, r.sonda, r.recibido_hex) for r in reales[:5]
        )
        cola = ""
        if artefactos or repetidos:
            cola = ("  (OJO: se han descartado %d artefacto(s) y %d lectura(s) "
                    "repetidas a contenido distinto.)" % (len(artefactos), len(repetidos)))
        return "RESPUESTA: %d lectura(s) que NO son eco. El equipo habla. %s%s" % (
            len(reales),
            detalle,
            cola,
        )
    if artefactos or repetidos:
        return (
            "POSIBLE ARTEFACTO: %d lectura(s) que parecen respuesta pero NO lo son. "
            "%d traen el mismo byte (FF con 8 bits de datos, 7F con 7: eso es la "
            "linea en reposo, y cambia segun como configuremos NOSOTROS el puerto) "
            "y %d repiten la MISMA respuesta a preguntas de contenido distinto. "
            "Los dos sintomas apuntan a la propia transmision, no al equipo. "
            "Confirmalo con: --sondas control"
            % (len(artefactos) + len(repetidos), len(artefactos), len(repetidos))
        )
    if ecos:
        return (
            "SOLO ECO en %d sonda(s): no hay protocolo, es el retorno exacto de "
            "lo enviado (lazo del chip)." % len(ecos)
        )
    if bytes_pasivos:
        return (
            "SILENCIO al sondear, pero SI llegaron %d byte(s) de forma "
            "espontanea: revisar la escucha pasiva." % bytes_pasivos
        )
    return "SILENCIO TOTAL: ningun byte en ninguna configuracion ni con ninguna sonda."


# ---------------------------------------------------------------------------
# Barrido completo
# ---------------------------------------------------------------------------
def escanear(
    puerto: str = "",
    completo: bool = False,
    ventana: float = VENTANA_POR_DEFECTO,
    ventana_larga: float = 0.0,
    asentar: float = 0.0,
    escuchar_segundos: float = 0.0,
    abrir=None,
    configs=None,
    sondas=None,
    progreso=None,
    al_recibir=None,
    simulado: str = "",
) -> dict:
    """Barre configuraciones y sondas sobre ``puerto`` y devuelve un informe.

    ``abrir`` permite inyectar un abridor falso (pruebas sin hardware).
    """
    configs = configuraciones(completo) if configs is None else list(configs)
    abrir = _abrir_real if abrir is None else abrir

    info = {
        "cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "equipo": os.environ.get("COMPUTERNAME", "") or "",
        "puerto": puerto,
        "pyserial": getattr(serial, "__version__", "") if HAY_PYSERIAL else "",
        "simulado": simulado,
        "modo": "SIMULADO (%s) - datos de mentira, NO del instrumento" % simulado
        if simulado
        else "REAL (instrumento)",
        "inventario": [],
        "configuraciones": [c.etiqueta for c in configs],
        "ventana_s": ventana,
        "ventana_larga_s": ventana_larga,
        "asentar_s": asentar,
        "pasiva": None,
        "resultados": [],
        "error": "",
        "veredicto": "",
    }

    if not simulado:
        info["inventario"] = puertos_disponibles()

    if not configs:
        info["error"] = "Sin configuraciones que probar."
        info["veredicto"] = "NADA QUE PROBAR: la lista de configuraciones esta vacia."
        return info

    if not puerto:
        info["error"] = "Sin puerto que abrir."
        info["veredicto"] = "NO HAY PUERTO: conecta y enciende el espectrofotometro."
        return info

    try:
        conexion = _abrir_y_preparar(abrir, puerto, configs[0])
    except Exception as error:
        info["error"] = str(error)
        info["veredicto"] = "NO SE PUDO ABRIR EL PUERTO %s: %s" % (puerto, error)
        return info

    try:
        if asentar > 0:
            # El chip USB<->serie tarda en quedar listo, y si el equipo acaba de
            # salir de un escaneo o de imprimir puede no estar escuchando.  Sin
            # esta pausa la primera sonda cae al vacio y ensucia esa config.
            time.sleep(asentar)
        if escuchar_segundos > 0:
            info["pasiva"] = escuchar(conexion, escuchar_segundos, progreso=None)
            info["pasiva"]["datos_hex"] = volcado_hex(info["pasiva"]["datos"])
            info["pasiva"]["texto"] = volcado_legible(info["pasiva"]["datos"])
            info["pasiva"].pop("datos", None)

        total = len(configs)
        todos = []
        for indice, config in enumerate(configs, start=1):
            if indice > 1:
                # Reabrir por si el equipo necesita renegociar la velocidad.
                _cerrar(conexion)
                try:
                    conexion = _abrir_y_preparar(abrir, puerto, config)
                except Exception as error:
                    info["resultados"].append(
                        {
                            "config": config.etiqueta,
                            "sonda": "(apertura)",
                            "enviado_hex": "",
                            "recibido_hex": "",
                            "texto": "",
                            "n_bytes": 0,
                            "eco": False,
                            "descripcion": "",
                            "error": str(error),
                        }
                    )
                    continue
            if indice > 1 and asentar > 0:
                # Tambien tras reabrir: el puerto acaba de renegociar.
                time.sleep(asentar)
            resultados = sondear_config(
                conexion,
                config,
                sondas=sondas,
                ventana=ventana,
                ventana_larga=ventana_larga,
            )
            todos.extend(resultados)
            lineas = estado_lineas(conexion)
            for resultado in resultados:
                fila = asdict(resultado)
                fila["lineas"] = lineas
                info["resultados"].append(fila)
                if al_recibir and resultado.n_bytes > 0:
                    al_recibir(fila)
            if progreso:
                bytes_config = sum(r.n_bytes for r in resultados)
                mensaje = (
                    "sin respuesta"
                    if bytes_config == 0
                    else "%d byte(s) recibidos" % bytes_config
                )
                progreso(indice, total, config.etiqueta, mensaje)
    finally:
        _cerrar(conexion)

    info["bytes_recibidos"] = sum(fila["n_bytes"] for fila in info["resultados"])
    if info["pasiva"]:
        hex_pasivo = info["pasiva"].get("datos_hex", "")
        info["bytes_pasivos"] = len(hex_pasivo.split()) if hex_pasivo else 0
    else:
        info["bytes_pasivos"] = 0
    info["veredicto"] = veredicto(todos, info["bytes_pasivos"])
    return info


# ---------------------------------------------------------------------------
# Informe y guardado
# ---------------------------------------------------------------------------
def informe_texto(info: dict) -> str:
    """Informe legible (es el contenido del ``.txt`` que se guarda)."""
    lineas = []
    sep = "=" * 73
    lineas.append(sep)
    lineas.append("BANCO DE PRUEBAS SERIE - ESPECTOFOTOMETRO JENWAY 6705")
    lineas.append(sep)
    lineas.append("Fecha            : %s" % info.get("cuando", ""))
    lineas.append("Equipo           : %s" % info.get("equipo", ""))
    lineas.append("Puerto           : %s" % (info.get("puerto") or "(ninguno)"))
    lineas.append("pyserial         : %s" % (info.get("pyserial") or "(no instalado)"))
    lineas.append("Modo             : %s" % info.get("modo", ""))
    lineas.append("Configuraciones  : %d" % len(info.get("configuraciones", [])))
    base = info.get("ventana_s", 0.0)
    larga = info.get("ventana_larga_s", 0.0)
    if larga > base:
        lineas.append(
            "Ventana por sonda: %.2f s (ampliable a %.1f s si algo empieza a llegar)"
            % (base, larga)
        )
    else:
        lineas.append("Ventana por sonda: %.2f s" % base)
    if info.get("asentar_s"):
        lineas.append("Asentamiento     : %.2f s de pausa tras abrir el puerto" % info["asentar_s"])
    if info.get("error"):
        lineas.append("ERROR            : %s" % info["error"])
    lineas.append("")

    lineas.append("--- Puertos serie presentes ----------------------------------------")
    if info.get("inventario"):
        for dato in info["inventario"]:
            lineas.append(
                "  %-6s | %-22s | %-12s | %s"
                % (
                    dato.get("puerto", ""),
                    dato.get("descripcion", "")[:22],
                    dato.get("fabricante", "")[:12],
                    dato.get("vid_pid", ""),
                )
            )
    elif not info.get("simulado"):
        lineas.append("  (ninguno: el instrumento no esta conectado o esta apagado)")
    else:
        lineas.append("  (no se consulta: corrida simulada)")
    lineas.append("")

    pasiva = info.get("pasiva")
    if pasiva:
        lineas.append("--- Escucha pasiva (%.1f s, sin enviar nada) ------------------------" % pasiva["segundos"])
        lineas.append("  Bytes espontaneos: %d" % (len(pasiva.get("datos_hex", "").split()) if pasiva.get("datos_hex") else 0))
        lineas.append("  HEX : %s" % (pasiva.get("datos_hex") or "(nada)"))
        lineas.append("  Texto: %s" % (pasiva.get("texto") or "(nada)"))
        muestras = pasiva.get("muestras_lineas") or []
        if muestras:
            lineas.append("  Lineas (ultima muestra): %s" % _texto_lineas(muestras[-1]["lineas"]))
        lineas.append("")

    lineas.append("--- Barrido -------------------------------------------------------")
    por_config = {}
    for fila in info.get("resultados", []):
        por_config.setdefault(fila["config"], []).append(fila)
    for config, filas in por_config.items():
        lineas.append("[%s]  lineas: %s" % (config, _texto_lineas(filas[0].get("lineas", {}))))
        for fila in filas:
            marca = ""
            if fila.get("ampliada"):
                marca = "  <ESPERA AMPLIADA: %.1f s de escucha>" % fila.get("espera_s", 0.0)
            elif fila.get("n_bytes") and not fila.get("eco") and es_todo_a_uno(
                fila.get("recibido_hex", ""), bits_de_etiqueta(fila.get("config", ""))
            ):
                marca = "  <ARTEFACTO: byte todo-a-uno (FF/7F), no es contenido del equipo>"
            if fila.get("error"):
                marca = "  <ERROR: %s>" % fila["error"]
            elif fila.get("eco"):
                marca = "  <ECO: es lo enviado, no una respuesta>"
            lineas.append(
                "    %-5s TX %-16s RX (%d B) %s %s%s"
                % (
                    fila.get("sonda", ""),
                    fila.get("enviado_hex", "") or "-",
                    fila.get("n_bytes", 0),
                    fila.get("recibido_hex", "") or "-",
                    fila.get("texto", ""),
                    marca,
                )
            )
        lineas.append("")
    if not por_config:
        lineas.append("  (no se llego a sondear)")
        lineas.append("")

    lineas.append("--- VEREDICTO -----------------------------------------------------")
    for trozo in _envolver(info.get("veredicto", ""), 71):
        lineas.append(trozo)
    lineas.append("")
    lineas.append(
        "Nota: un 'eco' NO es una respuesta del equipo.  Si el veredicto es"
    )
    lineas.append(
        "SILENCIO, el instrumento no habla por este puerto (coherente con el"
    )
    lineas.append(
        "manual, que no documenta ningun protocolo de control remoto)."
    )
    return "\n".join(lineas) + "\n"


def _texto_lineas(lineas: dict) -> str:
    if not lineas:
        return "(sin datos)"
    return " ".join("%s=%s" % (k, v) for k, v in lineas.items())


def _envolver(texto: str, ancho: int) -> list:
    palabras, salida, actual = texto.split(), [], ""
    for palabra in palabras:
        if actual and len(actual) + 1 + len(palabra) > ancho:
            salida.append("  " + actual)
            actual = palabra
        else:
            actual = (actual + " " + palabra).strip()
    if actual:
        salida.append("  " + actual)
    return salida or [""]


def guardar(info: dict, carpeta: str) -> dict:
    """Escribe el informe en ``.txt`` y ``.json``. Devuelve las rutas."""
    os.makedirs(carpeta, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    sufijo = "_SIMULADO" if info.get("simulado") else ""
    base = os.path.join(carpeta, "escaneo_%s%s" % (sello, sufijo))
    ruta_json, ruta_txt = base + ".json", base + ".txt"
    with open(ruta_json, "w", encoding="utf-8") as manejador:
        json.dump(info, manejador, ensure_ascii=False, indent=2)
    with open(ruta_txt, "w", encoding="utf-8") as manejador:
        manejador.write(informe_texto(info))
    return {"base": base, "json": ruta_json, "txt": ruta_txt}