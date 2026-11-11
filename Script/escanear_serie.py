#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Banco de pruebas serie del espectrofotometro Jenway 6705 (linea de comandos).

Hace que el instrumento hable: abre el puerto, barre configuraciones clasicas
de laboratorio, envia sondas BENIGNAS y registra todo byte de ida y vuelta.
No ordena borrar, formatear ni reiniciar nada.

EJEMPLOS
--------
  py -3.12 Script\\escanear_serie.py --listar
        Solo enseña que puertos serie hay (util para el problema de drivers).

  py -3.12 Script\\escanear_serie.py --puerto COM3 --escuchar 20
        Escucha pasiva 20 s SIN enviar nada: pulsa PRINT en el equipo o mete
        la tarjeta mientras corre, a ver si emite algo por su cuenta.

  py -3.12 Script\\escanear_serie.py --puerto COM3
        Escaneo rapido: 15 configuraciones x 11 sondas (~1 min).

  py -3.12 Script\\escanear_serie.py --puerto COM3 --completo
        Barrido exhaustivo: ~132 configuraciones.

  py -3.12 Script\\escanear_serie.py --puerto COM3 --ventana-larga 2m
        Los tiempos aceptan unidad: 0.4 (segundos), 90s, 1m30s, 2min, 500ms.
        --ventana es lo que se escucha siempre; --ventana-larga es hasta donde
        se amplia SOLO si algo empieza a llegar (una consulta contesta en
        milisegundos; un volcado de espectro puede tardar minuto y medio).

  py -3.12 Script\\escanear_serie.py --simular idn
        Autoprueba del banco sin instrumento (RESPUESTA falsa, para verificar
        que la herramienta funciona).  Los logs se marcan como SIMULADO.

Los informes se guardan en maestro/_escaneo_serie/ (txt + json).
"""

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from jenway67 import escaner_serie as es  # noqa: E402
from jenway67.puerto_jenway import Jenway6705Serial  # noqa: E402

SALIDA_POR_DEFECTO = os.path.join(RAIZ, "_escaneo_serie")


def _cabecera():
    print("=" * 73)
    print("BANCO DE PRUEBAS SERIE - JENWAY 6705")
    print("=" * 73)
    print("pyserial : %s" % (es.HAY_PYSERIAL and getattr(es.serial, "__version__", "si") or "NO INSTALADO"))
    print("")


def _listar():
    inventario = es.puertos_disponibles()
    print("Puertos serie presentes: %d" % len(inventario))
    for dato in inventario:
        print(
            "  %-6s | %-24s | %-14s | %s"
            % (
                dato["puerto"],
                dato["descripcion"][:24],
                dato["fabricante"][:14],
                dato["vid_pid"],
            )
        )
    if not inventario:
        print("")
        print("No hay ningun puerto serie presente.")
        print("  - Conecta y ENCIENDE el espectrofotometro (el puerto lo crea el")
        print("    chip FTDI al alimentarse el equipo).")
        print("  - Si aparece en el Administrador de dispositivos pero con error,")
        print("    es el driver FTDI (VID_0403:PID_6001).")
    return inventario


def _tiempo(texto):
    """Convierte "0.4" / "90s" / "1m30s" / "500ms" en segundos, con error claro."""
    try:
        return es.parsear_tiempo(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))


def _ejecutar_protocolo_seguro_6705(puerto, pedir_lectura=False, escuchar=0.0):
    """Ejecuta únicamente el protocolo oficial DataWay v0.21 (57600 8N1, '*' y '#')."""
    print("MODO SEGURO JENWAY 6705 (DataWay v0.21: 57600 8N1, DTR/RTS=ON, solo '*' y '#')")
    print("  Nota: El barrido multi-baudio y de sondas abiertas está desactivado por")
    print("        defecto porque bloquea la UART del Jenway 6705 durante ~10 minutos.")
    print("")
    drv = Jenway6705Serial()
    try:
        ok, msg = drv.conectar(puerto)
        if ok:
            print("  [OK] Handshake '*' -> %s (%s)" % (drv.identificacion, msg))
        else:
            print("  [--] %s" % msg)
            return 1

        if pedir_lectura:
            print("  [..] Solicitando lectura con '#' (PauseAndLook activo)...")
            res = drv.solicitar_lectura()
            print("  [RX] %d bytes en %.2f s (%d registros detectados)" % (
                res.bytes_recibidos, res.duracion_s, len(res.registros),
            ))
            if res.texto_crudo:
                print("-" * 73)
                print(res.texto_crudo.strip())
                print("-" * 73)

        if escuchar > 0:
            import time
            print("  [..] Escuchando pulsaciones físicas de PRINT durante %.0f s..." % escuchar)
            t0 = time.monotonic()
            while (time.monotonic() - t0) < escuchar:
                imp = drv.leer_impresion_espontanea()
                if imp is not None:
                    print("  [PRINT] %d bytes (%d registros):" % (
                        imp.bytes_recibidos, len(imp.registros),
                    ))
                    print(imp.texto_crudo.strip())
                time.sleep(0.1)
    finally:
        drv.desconectar()
    return 0


def main(argv=None):
    analizador = argparse.ArgumentParser(
        description="Comunicación serie segura para el Jenway 6705 (57600 8N1).",
    )
    analizador.add_argument("--puerto", default="", help="puerto a usar (p. ej. COM3 o SIMULADOR)")
    analizador.add_argument("--listar", action="store_true", help="solo listar puertos y salir")
    analizador.add_argument(
        "--pedir-lectura",
        action="store_true",
        help="tras identificar con '*', envía '#' para solicitar una lectura al 6705",
    )
    analizador.add_argument(
        "--forzar-barrido",
        action="store_true",
        help="PELIGRO: ejecuta el barrido antiguo multi-baudio/sondas abiertas "
        "(puede bloquear el Jenway 6705 durante 10 minutos)",
    )
    analizador.add_argument("--completo", action="store_true", help="barrido exhaustivo (~132 configuraciones)")
    analizador.add_argument(
        "--flujo",
        default="no",
        choices=["no", "rtscts", "xonxoff", "dsrdtr"],
        help="control de flujo del puerto (por defecto ninguno)",
    )
    analizador.add_argument(
        "--sondas",
        default="rapidas",
        choices=["rapidas", "ampliadas", "control"],
        help="consultas a enviar: rapidas (11), ampliadas (+20 de otros protocolos) "
        "o control (6, para distinguir una respuesta de un artefacto)",
    )
    analizador.add_argument(
        "--permitir-estado",
        action="store_true",
        help="añade las sondas que CAMBIAN estado (XMODEM, *CLS, AT); por defecto no se envían",
    )
    analizador.add_argument(
        "--barrido-bytes",
        action="store_true",
        help="añade el barrido exhaustivo de 1 byte, 0x00-0xFF (+256 sondas)",
    )
    analizador.add_argument(
        "--ventana",
        type=_tiempo,
        default=es.VENTANA_POR_DEFECTO,
        help="escucha por sonda; acepta unidad: 0.4, 90s, 1m30s (por defecto 0.4 s)",
    )
    analizador.add_argument(
        "--ventana-larga",
        type=_tiempo,
        default=es.VENTANA_LARGA_POR_DEFECTO,
        help="si algo empieza a llegar, seguir escuchando hasta esta espera "
        "(por defecto 90s = 1m30s; 0 lo desactiva)",
    )
    analizador.add_argument(
        "--asentar",
        type=_tiempo,
        default=es.ASENTAMIENTO_POR_DEFECTO,
        help="pausa tras abrir el puerto antes de la primera sonda "
        "(por defecto 1.5 s; 0 lo desactiva)",
    )
    analizador.add_argument("--escuchar", type=float, default=0.0, help="escucha pasiva N segundos")
    analizador.add_argument("--sin-sondas", action="store_true", help="solo escucha pasiva, no envia nada")
    analizador.add_argument("--salida", default=SALIDA_POR_DEFECTO, help="carpeta de informes")
    analizador.add_argument(
        "--simular",
        default="",
        choices=["", "silencio", "eco", "idn"],
        help="autoprueba del banco sin instrumento (datos FALSOS)",
    )
    argumentos = analizador.parse_args(argv)

    _cabecera()

    if argumentos.listar and not argumentos.simular:
        _listar()
        return 0

    if argumentos.puerto.upper() == "SIMULADOR" and not argumentos.simular:
        return _ejecutar_protocolo_seguro_6705(
            "SIMULADOR",
            pedir_lectura=argumentos.pedir_lectura,
            escuchar=argumentos.escuchar,
        )

    inventario = [] if argumentos.simular else _listar()
    puerto = es.elegir_puerto(inventario, argumentos.puerto)

    if argumentos.simular:
        puerto = argumentos.simular.upper() + ":SIMULADO"
        print("MODO SIMULADO ('%s'): los datos NO vienen del instrumento." % argumentos.simular)
    elif not puerto:
        print("")
        print("No hay puerto que abrir. Nada que sondear.")
        print("Conecta y enciende el equipo (o usa --puerto SIMULADOR) y vuelve a ejecutar:")
        print("  py -3.12 Script\\escanear_serie.py --puerto SIMULADOR --pedir-lectura")
        return 2

    # Protección del hardware real: salvo que se pida --simular, --sin-sondas o
    # explícitamente --forzar-barrido, usamos el driver seguro Jenway6705Serial.
    if not argumentos.simular and not argumentos.sin_sondas and not argumentos.forzar_barrido:
        if not es.HAY_PYSERIAL:
            print("pyserial no esta instalado:  py -3.12 -m pip install pyserial")
            return 3
        return _ejecutar_protocolo_seguro_6705(
            puerto,
            pedir_lectura=argumentos.pedir_lectura,
            escuchar=argumentos.escuchar,
        )

    print("")
    print("Puerto   : %s" % puerto)
    sondas_a_enviar = ([] if argumentos.sin_sondas
                       else es.juego_de_sondas(argumentos.sondas,
                                               permitir_estado=argumentos.permitir_estado,
                                               barrido_bytes=argumentos.barrido_bytes))
    if argumentos.sin_sondas:
        print("Sondas   : ninguna (solo escucha pasiva)")
    else:
        print("Sondas   : %d — juego '%s'%s%s" % (
            len(sondas_a_enviar), argumentos.sondas,
            " + estado" if argumentos.permitir_estado else "",
            " + barrido de 1 byte" if argumentos.barrido_bytes else ""))
        if argumentos.permitir_estado:
            print("           (el juego 'estado' incluye XMODEM, *CLS y AT: cambian")
            print("            algo o arrancan un modo de transferencia)")
    configs = es.configuraciones(argumentos.completo, flujo=argumentos.flujo)
    print("Configs  : %d%s" % (len(configs), " (exhaustivo)" if argumentos.completo else " (clasicas)"))
    print("Flujo    : %s" % argumentos.flujo)
    cola = ""
    if argumentos.ventana_larga > argumentos.ventana:
        cola = " (ampliable a %.0f s si algo empieza a llegar)" % argumentos.ventana_larga
    print("Ventana  : %.2f s por sonda%s" % (argumentos.ventana, cola))
    if argumentos.asentar:
        print("Asentar  : %.2f s de pausa tras abrir el puerto" % argumentos.asentar)
    if sondas_a_enviar:
        estimado = (
            len(sondas_a_enviar) * argumentos.ventana * len(configs)
            + argumentos.asentar * len(configs)
        ) / 60.0
        cuando = "%.0f min" % estimado if estimado >= 1 else "%.0f s" % (estimado * 60)
        print("Estimado : ~%s (los casos silenciosos cuestan solo la ventana"
              " corta; una respuesta lenta se espera entera)" % cuando)
    if argumentos.escuchar:
        print("Escucha  : %.0f s pasivos antes de sondear" % argumentos.escuchar)
    print("")

    if not es.HAY_PYSERIAL and not argumentos.simular:
        print("pyserial no esta instalado:  py -3.12 -m pip install pyserial")
        return 3

    if argumentos.simular:
        def abrir(_puerto, _config):
            return es.PuertoSimulado(argumentos.simular)
    else:
        abrir = None

    def progreso(indice, total, etiqueta, mensaje):
        print("  [%2d/%2d] %-12s %s" % (indice, total, etiqueta, mensaje), flush=True)

    def al_recibir(fila):
        print(
            "         >> %s · %s  RX (%d B en %.2f s)  %s   %s"
            % (
                fila["config"],
                fila["sonda"],
                fila["n_bytes"],
                fila.get("espera_s", 0.0),
                fila["recibido_hex"] or "-",
                fila["texto"],
            ),
            flush=True,
        )

    if argumentos.sin_sondas:
        configs_a_probar = configs[:1]
    else:
        configs_a_probar = configs

    print("Barriendo...")
    info = es.escanear(
        puerto=puerto,
        completo=argumentos.completo,
        ventana=argumentos.ventana,
        ventana_larga=argumentos.ventana_larga,
        asentar=argumentos.asentar,
        escuchar_segundos=argumentos.escuchar,
        abrir=abrir,
        configs=configs_a_probar,
        sondas=sondas_a_enviar,
        progreso=progreso,
        al_recibir=al_recibir,
        simulado=argumentos.simular,
    )

    print("")
    print("=" * 73)
    print("VEREDICTO")
    print("=" * 73)
    print(info["veredicto"])
    print("")

    rutas = es.guardar(info, argumentos.salida)
    print("Informe : %s" % rutas["txt"])
    print("Datos   : %s" % rutas["json"])
    return 0 if not info.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
