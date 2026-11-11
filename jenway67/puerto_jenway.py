# -*- coding: utf-8 -*-
"""Driver de comunicación serie segura en vivo para el espectrofotómetro Jenway 6705.

Ingeniería inversa verificada a partir de los binarios originales de Jenway DataWay v0.21
(``CommBase.dll``, ``Comms.dll``, ``Jenway_67xx.dll``, ``DataWay v0.21.exe``) y de las
trazas reales de API Monitor (``data2completo.txt`` y ``consoladataway.txt``).

CONTRATO DE SEGURIDAD DE HARDWARE (7 REGLAS DE ORO ANTI-BLOQUEO)
----------------------------------------------------------------
1. Configuración física fija e inmutable: ``57600 8N1`` (57600 baudios, 8 bits de
   datos, sin paridad, 1 bit de parada). Prohibido barrer velocidades o paridades.
2. Líneas de control estables desde la apertura: ``DTR = True``, ``RTS = True``,
   sin control de flujo (``xonxoff=False``, ``rtscts=False``, ``dsrdtr=False``) y
   jamás activar condición de ``BREAK``.
3. Pausa obligatoria de asentamiento post-apertura: ``100 ms`` (``Sleep(100)`` en
   ``_67xx::Connect`` ``IL_003F``) antes de transmitir cualquier byte.
4. Lista blanca estricta de 2 únicos comandos de 1 byte SIN ``\\r`` ni ``\\n``
   (``txTerminator = null`` en ``CommLine``):
   - ``b"*"`` (``0x2A``): Handshake de conexión -> el 6705 responde ``"67XX \\r\\n"``.
   - ``b"#"`` (``0x23``): Solicitud de lectura/impresión -> el 6705 envía el ticket
     formateado de 40 columnas terminado en ``========================================\\r\\n``.
   Cualquier otro byte está bloqueado por código.
5. Drenaje completo ``PauseAndLook``: una vez iniciada una recepción, se lee hasta
   que el buffer deje de crecer durante al menos ``500 ms`` tras recibir el cierre
   del ticket. Jamás se cierra el puerto en mitad de una transmisión.
6. Sesión persistente + exclusión mutua (``threading.Lock``): el puerto se mantiene
   abierto durante toda la sesión para no conmutar ``DTR``/``RTS`` y no se permite
   solapar comandos.
7. Cierre limpio: espera a que finalice cualquier lectura activa, purga colas y
   cierra el descriptor sin alterar las líneas de estado.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .adaptador_txt import parsear_stream_serie
from .parser_txt import Registro, _decodificar

try:
    import serial
    from serial.tools import list_ports as _list_ports

    HAY_PYSERIAL = True
except Exception:  # pragma: no cover
    serial = None
    _list_ports = None
    HAY_PYSERIAL = False


# ---------------------------------------------------------------------------
# Constantes de hardware inmutables (Contrato de Seguridad)
# ---------------------------------------------------------------------------
BAUDRATE_6705: int = 57600
BYTESIZE_6705: int = 8
PARITY_6705: str = "N"
STOPBITS_6705: int = 1

CMD_CONECTAR: bytes = b"*"   # 0x2A (1 byte, sin CR/LF)
CMD_LECTURA: bytes = b"#"    # 0x23 (1 byte, sin CR/LF)
COMANDOS_PERMITIDOS = frozenset({CMD_CONECTAR, CMD_LECTURA})

PAUSA_POST_APERTURA_S: float = 0.100     # _67xx::Connect IL_003F: Thread.Sleep(100)
PAUSA_POST_LECTURA_S: float = 0.200      # _67xx::Reading IL_001E: Thread.Sleep(200)
PASO_SONDEO_S: float = 0.100             # DLLClass::CheckComPort: Thread.Sleep(100)
SILENCIO_HANDSHAKE_S: float = 0.200      # _67xx::Connect IL_00B2: Thread.Sleep(200)
SILENCIO_LECTURA_S: float = 0.500        # PauseAndLook: >= 2 ciclos sin nuevos bytes
TIMEOUT_HANDSHAKE_S: float = 3.0         # _67xx::Connect IL_0092: 3 segundos
TIMEOUT_PRIMER_BYTE_S: float = 4.0       # Espera inicial tras '#' antes del primer byte
TIMEOUT_MAX_TRANSMISION_S: float = 45.0  # Margen para espectros largos a 57600 bps

PUERTO_SIMULADOR = "SIMULADOR"


@dataclass
class LecturaSerie:
    """Resultado empaquetado de una lectura recibida por RS-232."""

    texto_crudo: str
    bytes_recibidos: int
    duracion_s: float
    registros: List[Tuple[Registro, str, List[Dict], List[str]]] = field(default_factory=list)

    @property
    def tiene_datos(self) -> bool:
        return len(self.registros) > 0


# ---------------------------------------------------------------------------
# Simulador seguro del Jenway 6705 (para pruebas sin equipo conectado)
# ---------------------------------------------------------------------------
TICKETS_SIMULADOS: Tuple[bytes, ...] = (
    (
        b"========================================\r\n"
        b"MODO FOTOMETR\xedA\r\n"
        b"ID INSTRUMENTO:             67XX V1.64.5\r\n"
        b"ID DE USUARIO:                   ALUMNOS\r\n"
        b"M\xe9TODO:                            LOWRY\r\n"
        b"ID DE LOTE:             LOTE POR DEFECTO\r\n"
        b"LONGITUD DE ONDA:                  550.0\r\n"
        b"GUARDAR AUTOM\xe1TICAMENTE:        ACTIVADO\r\n"
        b"\xfaLTIMA CALIBRACI\xf3N:    10:36:36 19/10/26\r\n"
        b"========================================\r\n"
        b"001 0.842ABS 14.4%T 10:36:36 19/10/26\r\n"
        b"========================================\r\n"
    ),
    (
        b"========================================\r\n"
        b"MODO CIN\xe9TICA.....\r\n"
        b"MUESTRA OBTENIDA:      10:42:45 15/09/26\r\n"
        b"ID INSTRUMENTO:             67XX V1.64.5\r\n"
        b"NOMBRE DE USUARIO:               ALUMNOS\r\n"
        b"M\xe9TODO:               M\xe9TODO POR DEFECTO\r\n"
        b"ID DE LOTE:             LOTE POR DEFECTO\r\n"
        b"EST\xe1NDAR CAL. CONCENTRACI\xf3N:        1.00\r\n"
        b"FACTOR DE CONCENTRACI\xf3N:            1.00\r\n"
        b"DESVIACI\xf3N DE CONCENTRACI\xf3N:        0.00\r\n"
        b"LONGITUD DE ONDA:                400.0NM\r\n"
        b"TIEMPO DE EJECUCI\xf3N:                  30\r\n"
        b"TIEMPO DE RETARDO:                     0\r\n"
        b"MODO DE MEDICI\xf3N:             ABSORBANCE\r\n"
        b"SEGURIDAD DE M\xe9TODO:            PERSONAL\r\n"
        b"ESCALA AUTOM\xe1TICA:              ACTIVADO\r\n"
        b"M\xedNIMO EJE Y:                       -0.3\r\n"
        b"M\xe1XIMO EJE Y:                        3.0\r\n"
        b"N\xfaMERO DE ID DE MUESTRA:               1\r\n"
        b"\xfaLTIMA CALIBRACI\xf3N:    10:41:14 15/09/26\r\n"
        b"========================================\r\n"
        b"HORA ABS\r\n"
        b"0,0.120\r\n"
        b"2,0.185\r\n"
        b"4,0.248\r\n"
        b"6,0.305\r\n"
        b"8,0.358\r\n"
        b"10,0.405\r\n"
        b"13,0.468\r\n"
        b"15,0.504\r\n"
        b"17,0.536\r\n"
        b"19,0.564\r\n"
        b"21,0.589\r\n"
        b"23,0.610\r\n"
        b"25,0.628\r\n"
        b"27,0.643\r\n"
        b"29,0.655\r\n"
        b"========================================\r\n"
    ),
    (
        b"========================================\r\n"
        b"MODO ESPECTRO.....\r\n"
        b"ID INSTRUMENTO:             67XX V1.64.5\r\n"
        b"NOMBRE DE USUARIO:               ALUMNOS\r\n"
        b"M\xe9TODO:                    BARRIDO UV-VIS\r\n"
        b"ID DE LOTE:             LOTE POR DEFECTO\r\n"
        b"WRANGO DE LONGITUD DE ONDA:400.0NM - 500.0NM\r\n"
        b"INTERVALO DE GR\xe1FICO:             10.0NM\r\n"
        b"MODO DE MEDICI\xf3N:             ABSORBANCE\r\n"
        b"========================================\r\n"
        b"LONGITUD DE ONDA,ABSORBANCIA\r\n"
        b"400.0,0.152\r\n"
        b"410.0,0.240\r\n"
        b"420.0,0.415\r\n"
        b"430.0,0.680\r\n"
        b"440.0,0.920\r\n"
        b"450.0,1.045\r\n"
        b"460.0,0.890\r\n"
        b"470.0,0.610\r\n"
        b"480.0,0.340\r\n"
        b"490.0,0.180\r\n"
        b"500.0,0.095\r\n"
        b"========================================\r\n"
    ),
)


class SimuladorJenway6705:
    """Emulador exacto del hardware Jenway 6705 para validación sin equipo físico.

    Verifica además que quien lo abre use ``57600 8N1``, ``DTR=True``, ``RTS=True``
    y solo envíe ``b"*"`` o ``b"#"``.
    """

    def __init__(
        self,
        baudrate: int = BAUDRATE_6705,
        bytesize: int = BYTESIZE_6705,
        parity: str = PARITY_6705,
        stopbits: int = STOPBITS_6705,
        rtscts: bool = False,
        xonxoff: bool = False,
        dsrdtr: bool = False,
        tickets: Sequence[bytes] = TICKETS_SIMULADOS,
    ):
        if baudrate != BAUDRATE_6705 or bytesize != BYTESIZE_6705 or parity != PARITY_6705 or stopbits != STOPBITS_6705:
            raise ValueError(
                f"Configuración peligrosa rechazada por simulador 6705: "
                f"{baudrate} {bytesize}{parity}{stopbits} (requiere 57600 8N1)"
            )
        if rtscts or xonxoff or dsrdtr:
            raise ValueError("El Jenway 6705 requiere control de flujo desactivado (Handshake.none)")
        self.baudrate = baudrate
        self.dtr = True
        self.rts = True
        self.break_condition = False
        self.is_open = True
        self._rx = bytearray()
        self.historial_tx: List[bytes] = []
        self._tickets = tuple(tickets)
        self._indice_ticket = 0

    @property
    def in_waiting(self) -> int:
        return len(self._rx)

    def reset_input_buffer(self) -> None:
        self._rx.clear()

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise OSError("Puerto cerrado")
        payload = bytes(data)
        self.historial_tx.append(payload)
        if payload not in COMANDOS_PERMITIDOS:
            raise ValueError(
                f"VIOLACIÓN DE SEGURIDAD: se intentó enviar {payload!r} al Jenway 6705. "
                f"Solo se permiten b'*' y b'#'."
            )
        if payload == CMD_CONECTAR:
            self._rx.extend(b"67XX \r\n")
        elif payload == CMD_LECTURA and self._tickets:
            ticket = self._tickets[self._indice_ticket % len(self._tickets)]
            self._indice_ticket += 1
            self._rx.extend(ticket)
        return len(payload)

    def inyectar_impresion_panel(self, datos: Optional[bytes] = None) -> None:
        """Simula que el usuario pulsó la tecla física PRINT en el espectrofotómetro."""
        if datos is None:
            datos = self._tickets[self._indice_ticket % len(self._tickets)]
            self._indice_ticket += 1
        self._rx.extend(datos)

    def read(self, size: int = 1) -> bytes:
        if not self.is_open:
            raise OSError("Puerto cerrado")
        n = min(max(int(size), 1), len(self._rx))
        trozo = bytes(self._rx[:n])
        del self._rx[:n]
        return trozo

    def close(self) -> None:
        self.is_open = False


# ---------------------------------------------------------------------------
# Enumeración de puertos serie
# ---------------------------------------------------------------------------
def listar_puertos_serie(incluir_simulador: bool = True) -> List[Dict[str, str]]:
    """Lista los puertos COM presentes en el sistema (priorizando FTDI 0403:6001)."""
    puertos: List[Dict[str, str]] = []
    if HAY_PYSERIAL and _list_ports is not None:
        try:
            items = sorted(_list_ports.comports(), key=lambda x: x.device or "")
        except Exception:
            items = []
        for info in items:
            vid = getattr(info, "vid", None)
            pid = getattr(info, "pid", None)
            vid_pid = f"{vid:04X}:{pid:04X}" if (vid is not None and pid is not None) else ""
            es_ftdi = (
                vid == 0x0403
                or "FTDI" in (getattr(info, "manufacturer", "") or "").upper()
                or "USB SERIAL" in (getattr(info, "description", "") or "").upper()
            )
            puertos.append({
                "puerto": info.device,
                "descripcion": getattr(info, "description", "") or info.device,
                "fabricante": getattr(info, "manufacturer", "") or "",
                "vid_pid": vid_pid,
                "es_ftdi": "1" if es_ftdi else "",
            })
        # Poner primero los FTDI (el Jenway 6705 lleva un FT232R 0403:6001)
        puertos.sort(key=lambda d: (0 if d["es_ftdi"] else 1, d["puerto"]))

    if incluir_simulador:
        puertos.append({
            "puerto": PUERTO_SIMULADOR,
            "descripcion": "Simulador virtual Jenway 6705 (sin hardware)",
            "fabricante": "Interno",
            "vid_pid": "SIM:6705",
            "es_ftdi": "",
        })
    return puertos


# ---------------------------------------------------------------------------
# Driver seguro Jenway6705Serial
# ---------------------------------------------------------------------------
def _abridor_por_defecto(puerto: str):
    """Abre el puerto físico con las 7 reglas de seguridad o el simulador."""
    if puerto.upper().startswith(PUERTO_SIMULADOR):
        return SimuladorJenway6705()
    if not HAY_PYSERIAL or serial is None:
        raise RuntimeError("pyserial no está instalado en este entorno Python.")
    # Configurar parámetros ANTES de abrir para evitar glitches de baudios o DTR/RTS
    ser = serial.Serial()
    ser.port = puerto
    ser.baudrate = BAUDRATE_6705
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = 0.05
    ser.write_timeout = 1.0
    ser.xonxoff = False
    ser.rtscts = False
    ser.dsrdtr = False
    ser.dtr = True
    ser.rts = True
    ser.open()
    try:
        ser.break_condition = False
    except Exception:
        pass
    return ser


class Jenway6705Serial:
    """Controlador seguro de sesión serie para el Jenway 6705.

    Implementa exactamente la secuencia de ``Jenway_67xx.dll`` y ``CommBase.dll``:
    mantiene el puerto abierto durante la sesión, protege todas las operaciones
    con un ``Lock`` reentrante y bloquea cualquier byte fuera de ``{b'*', b'#'}``.
    """

    def __init__(
        self,
        abridor: Optional[Callable[[str], object]] = None,
        reloj: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self._abridor = abridor or _abridor_por_defecto
        self._reloj = reloj
        self._dormir = dormir
        self._lock = threading.Lock()
        self._ser = None
        self.puerto: str = ""
        self.identificacion: str = ""
        self.conectado: bool = False

    # ------------------------------------------------- primitivas blindadas
    def _validar_comando(self, comando: bytes) -> None:
        if not isinstance(comando, bytes) or comando not in COMANDOS_PERMITIDOS:
            raise ValueError(
                f"Comando bloqueado por seguridad de hardware: {comando!r}. "
                f"El Jenway 6705 solo admite { sorted(COMANDOS_PERMITIDOS) }."
            )

    def _leer_disponible_no_bloqueante(self) -> bytes:
        if self._ser is None:
            return b""
        esperando = getattr(self._ser, "in_waiting", 0) or 0
        if esperando > 0:
            return self._ser.read(esperando) or b""
        return b""

    def _drenar_pause_and_look(
        self,
        timeout_inicial_s: float,
        silencio_fin_s: float,
        esperar_ticket_completo: bool = False,
        timeout_max_s: float = TIMEOUT_MAX_TRANSMISION_S,
    ) -> bytes:
        """Réplica exacta de ``PauseAndLook`` + ``CheckComPort`` de ``DataWay``.

        1. Espera hasta ``timeout_inicial_s`` la llegada del primer byte.
        2. Una vez que empiezan a entrar bytes, continúa leyendo cada ``100 ms``
           hasta que el buffer acumule ``silencio_fin_s`` sin recibir ni un byte
           nuevo (y, si ``esperar_ticket_completo=True``, da margen adicional
           mientras el ticket aún no haya cerrado su segundo separador ``====``).
        """
        inicio = self._reloj()
        buffer = bytearray()

        # Fase A: esperar el primer byte
        while (self._reloj() - inicio) < timeout_inicial_s:
            trozo = self._leer_disponible_no_bloqueante()
            if trozo:
                buffer.extend(trozo)
                break
            self._dormir(PASO_SONDEO_S)

        if not buffer:
            return b""

        # Fase B: drenar hasta silencio sostenido (nunca cortar en mitad del envío)
        ultimo_ingreso = self._reloj()
        while (self._reloj() - inicio) < timeout_max_s:
            self._dormir(PASO_SONDEO_S)
            trozo = self._leer_disponible_no_bloqueante()
            if trozo:
                buffer.extend(trozo)
                ultimo_ingreso = self._reloj()
                continue

            silencio = self._reloj() - ultimo_ingreso
            if esperar_ticket_completo:
                # Si todavía no han llegado al menos 2 bloques de "====" (o una fila
                # fotométrica de continuación terminada en salto de línea), damos margen.
                n_seps = buffer.count(b"====")
                upper_buf = bytes(buffer).upper()
                fila_foto_completa = (
                    b"ABS" in upper_buf and b"%T" in upper_buf and buffer.endswith(b"\n")
                )
                umbral = (
                    silencio_fin_s
                    if (n_seps >= 2 or fila_foto_completa)
                    else max(silencio_fin_s, 1.2)
                )
            else:
                umbral = silencio_fin_s

            if silencio >= umbral:
                break

        return bytes(buffer)

    # ---------------------------------------------------------- API pública
    def conectar(self, puerto: str, timeout_s: float = TIMEOUT_HANDSHAKE_S) -> Tuple[bool, str]:
        """Abre ``puerto`` a ``57600 8N1`` y verifica el handshake ``b'*'`` -> ``67XX``.

        Si el puerto responde con ``67XX`` (o con un ticket válido del 6705),
        deja el puerto abierto para toda la sesión y devuelve ``(True, mensaje)``.
        Si no responde, drena limpiamente y cierra el puerto.
        """
        puerto = (puerto or "").strip()
        if not puerto:
            return False, "Selecciona un puerto serie (p. ej. COM4 o SIMULADOR)."

        self.desconectar()

        with self._lock:
            try:
                self._ser = self._abridor(puerto)
            except Exception as error:
                self._ser = None
                return False, f"No se pudo abrir {puerto}: {error}"

            try:
                # Regla 3: pausa obligatoria de 100 ms tras abrir el puerto
                self._dormir(PAUSA_POST_APERTURA_S)
                try:
                    self._ser.reset_input_buffer()
                    self._ser.reset_output_buffer()
                except Exception:
                    pass

                # Regla 4: enviar únicamente 1 byte '*' (0x2A) sin \r ni \n
                self._validar_comando(CMD_CONECTAR)
                self._ser.write(CMD_CONECTAR)
                self._ser.flush()

                # Regla 5: esperar respuesta y drenar hasta silencio
                crudo = self._drenar_pause_and_look(
                    timeout_inicial_s=timeout_s,
                    silencio_fin_s=SILENCIO_HANDSHAKE_S,
                    esperar_ticket_completo=False,
                )
                texto = _decodificar(crudo).strip()

                if "67XX" in texto.upper() or "====" in texto:
                    self.puerto = puerto
                    self.identificacion = texto.splitlines()[0].strip() if texto else "67XX"
                    self.conectado = True
                    return True, f"Conectado a {puerto} ({self.identificacion}) a 57600 8N1"

                # No respondió como 67XX: cerrar limpiamente
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                if texto:
                    return False, f"Respuesta inesperada en {puerto}: {texto[:40]!r}"
                return False, (
                    f"Sin respuesta en {puerto} (57600 8N1). Verifica que el "
                    f"Jenway 6705 esté encendido y en un modo de medición."
                )
            except Exception as error:
                try:
                    if self._ser is not None:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                return False, f"Error al conectar con {puerto}: {error}"

    def solicitar_lectura(
        self,
        timeout_inicial_s: float = TIMEOUT_PRIMER_BYTE_S,
        silencio_fin_s: float = SILENCIO_LECTURA_S,
    ) -> LecturaSerie:
        """Envía ``b'#'`` (1 byte) y drena el ticket impreso por el Jenway 6705."""
        if not self.conectado or self._ser is None:
            raise RuntimeError("El espectrofotómetro no está conectado.")

        with self._lock:
            t0 = self._reloj()
            # Si había bytes residuales (p. ej. un saludo previo "67XX"), leerlos antes
            residual = self._leer_disponible_no_bloqueante()
            if residual and b"====" not in residual:
                residual = b""

            # Regla 4: enviar únicamente 1 byte '#' (0x23) sin \r ni \n
            self._validar_comando(CMD_LECTURA)
            self._ser.write(CMD_LECTURA)
            self._ser.flush()

            # _67xx::Reading espera 200 ms tras '#' antes del bucle PauseAndLook
            self._dormir(PAUSA_POST_LECTURA_S)

            crudo = residual + self._drenar_pause_and_look(
                timeout_inicial_s=timeout_inicial_s,
                silencio_fin_s=silencio_fin_s,
                esperar_ticket_completo=True,
            )
            duracion = self._reloj() - t0

        texto = _decodificar(crudo)
        registros = parsear_stream_serie(texto)
        return LecturaSerie(
            texto_crudo=texto,
            bytes_recibidos=len(crudo),
            duracion_s=duracion,
            registros=registros,
        )

    def leer_impresion_espontanea(
        self,
        silencio_fin_s: float = SILENCIO_LECTURA_S,
    ) -> Optional[LecturaSerie]:
        """Comprueba sin bloquear si el usuario pulsó PRINT en el panel del 6705.

        Si detecta bytes entrantes en el puerto, adquiere el candado y drena el
        ticket completo usando ``PauseAndLook`` para no truncarlo.
        """
        if not self.conectado or self._ser is None:
            return None
        if not self._lock.acquire(blocking=False):
            return None
        try:
            esperando = getattr(self._ser, "in_waiting", 0) or 0
            if esperando <= 0:
                return None
            t0 = self._reloj()
            crudo = self._drenar_pause_and_look(
                timeout_inicial_s=0.2,
                silencio_fin_s=silencio_fin_s,
                esperar_ticket_completo=True,
            )
            duracion = self._reloj() - t0
            if not crudo:
                return None
            texto = _decodificar(crudo)
            registros = parsear_stream_serie(texto)
            if not registros and texto.strip().upper() == "67XX":
                return None
            return LecturaSerie(
                texto_crudo=texto,
                bytes_recibidos=len(crudo),
                duracion_s=duracion,
                registros=registros,
            )
        except Exception:
            return None
        finally:
            self._lock.release()

    def desconectar(self) -> None:
        """Cierra el puerto serie de forma limpia respetando cualquier lectura en curso."""
        with self._lock:
            ser = self._ser
            self._ser = None
            self.conectado = False
            self.puerto = ""
            self.identificacion = ""
            if ser is not None:
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except Exception:
                    pass
                try:
                    ser.close()
                except Exception:
                    pass
