# -*- coding: utf-8 -*-
"""Pruebas de Fase 1 y Fase 2:
- Parser dual Serie/SD (parser_txt + adaptador_txt) con la captura real de DataWay (consoladataway.txt)
- Driver serie seguro Jenway6705Serial (7 reglas de oro contra bloqueo de UART)
- Registro virtual serie:// en reader.py y exportar.py
- Exportadores PDF vectorial (exportar_pdf) y JCAMP-DX 4.24 (exportar_jcamp)
- Integración en VentanaMaestro y PanelConexionSerie
"""

import os
import sys
import tempfile
import unittest

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MAESTRO not in sys.path:
    sys.path.insert(0, MAESTRO)

from jenway67 import adaptador_txt, exportar, parser_txt, reader  # noqa: E402
from jenway67.exportar_jcamp import exportar_jcamp_dx, generar_jcamp_dx  # noqa: E402
from jenway67.exportar_pdf import exportar_tarjeta_pdf, exportar_vista_pdf  # noqa: E402
from jenway67.models import Metodo, Muestra, Tarjeta  # noqa: E402
from jenway67.puerto_jenway import (  # noqa: E402
    BAUDRATE_6705,
    COMANDOS_PERMITIDOS,
    Jenway6705Serial,
    SimuladorJenway6705,
)


# Réplica exacta de c:\Users\tony_\OneDrive\Documentos\jenway\consoladataway.txt
CAPTURA_CONSOLA_DATAWAY = """\
========================================
MODO FOTOMETRíA
ID INSTRUMENTO:             67XX V1.64.5
ID INSTRUMENTO:             67XX V1.64.5
ID DE USUARIO:                   ALUMNOS
MéTODO:                            LOWRY
ID DE LOTE:             LOTE POR DEFECTO
LONGITUD DE ONDA:                  550.0
GUARDAR AUTOMáTICAMENTE:        ACTIVADO
úLTIMA CALIBRACIóN:    10:36:36 19/10/26
========================================
001 3.000ABS 0.0%T 10:36:36 19/10/26
========================================
MODO FOTOMETRíA
ID INSTRUMENTO:             67XX V1.64.5
ID INSTRUMENTO:             67XX V1.64.5
ID DE USUARIO:                   ALUMNOS
MéTODO:                            LOWRY
ID DE LOTE:             LOTE POR DEFECTO
LONGITUD DE ONDA:                  550.0
GUARDAR AUTOMáTICAMENTE:        ACTIVADO
úLTIMA CALIBRACIóN:    10:36:36 19/10/26
========================================
001 3.000ABS 0.0%T 10:36:36 19/10/26
========================================
MODO CINéTICA.....
MUESTRA OBTENIDA:      10:42:45 15/09/26
ID INSTRUMENTO:             67XX V1.64.5
NOMBRE DE USUARIO:               ALUMNOS
MéTODO:               MéTODO POR DEFECTO
ID DE LOTE:             LOTE POR DEFECTO
ESTáNDAR CAL. CONCENTRACIóN:        1.00
FACTOR DE CONCENTRACIóN:            1.00
DESVIACIóN DE CONCENTRACIóN:        0.00
LONGITUD DE ONDA:                400.0NM
TIEMPO DE EJECUCIóN:                  30
TIEMPO DE RETARDO:                     0
MODO DE MEDICIóN:             ABSORBANCE
SEGURIDAD DE MéTODO:            PERSONAL
ESCALA AUTOMáTICA:              ACTIVADO
MíNIMO EJE Y:                       -0.3
MáXIMO EJE Y:                        3.0
NúMERO DE ID DE MUESTRA:               1
úLTIMA CALIBRACIóN:    10:41:14 15/09/26
========================================
HORA ABS
0,-0.001
2,0.000
4,-0.001
6,-0.000
8,-0.001
10,-0.000
13,-0.001
15,-0.000
17,-0.000
19,0.000
21,0.000
23,0.000
25,0.000
27,0.000
29,-0.001
========================================
MODO CINéTICA.....
MUESTRA OBTENIDA:      10:42:45 15/09/26
ID INSTRUMENTO:             67XX V1.64.5
NOMBRE DE USUARIO:               ALUMNOS
MéTODO:               MéTODO POR DEFECTO
ID DE LOTE:             LOTE POR DEFECTO
ESTáNDAR CAL. CONCENTRACIóN:        1.00
FACTOR DE CONCENTRACIóN:            1.00
DESVIACIóN DE CONCENTRACIóN:        0.00
LONGITUD DE ONDA:                400.0NM
TIEMPO DE EJECUCIóN:                  30
TIEMPO DE RETARDO:                     0
MODO DE MEDICIóN:             ABSORBANCE
SEGURIDAD DE MéTODO:            PERSONAL
ESCALA AUTOMáTICA:              ACTIVADO
MíNIMO EJE Y:                       -0.3
MáXIMO EJE Y:                        3.0
NúMERO DE ID DE MUESTRA:               1
úLTIMA CALIBRACIóN:    10:41:14 15/09/26
========================================
HORA ABS
0,-0.001
2,0.000
4,-0.001
6,-0.000
8,-0.001
10,-0.000
13,-0.001
15,-0.000
17,-0.000
19,0.000
21,0.000
23,0.000
25,0.000
27,0.000
29,-0.001
"""


class TestParserDualSerieSD(unittest.TestCase):
    """Verifica el soporte dual (impresión serie de 40 columnas + archivos SD)."""

    def test_parsea_captura_consola_dataway_utf8(self):
        regs = parser_txt.parsear_bytes(CAPTURA_CONSOLA_DATAWAY.encode("utf-8"))
        self.assertEqual(len(regs), 4)

        self.assertEqual(regs[0].modo, "photometrics")
        self.assertEqual(regs[0].nombre_metodo, "LOWRY")
        self.assertEqual(regs[0].usuario, "ALUMNOS")
        self.assertAlmostEqual(regs[0].longitud_onda, 550.0)
        self.assertEqual(len(regs[0].cuerpo["filas"]), 1)
        self.assertEqual(regs[0].cuerpo["filas"][0]["id"], "001")
        self.assertEqual(regs[0].cuerpo["filas"][0]["abs"], "3.000")

        self.assertEqual(regs[1].modo, "photometrics")
        self.assertEqual(len(regs[1].cuerpo["filas"]), 1)

        self.assertEqual(regs[2].modo, "kinetics")
        self.assertEqual(regs[2].nombre_metodo, "MéTODO POR DEFECTO")
        self.assertAlmostEqual(regs[2].longitud_onda, 400.0)
        self.assertEqual(len(regs[2].cuerpo["serie"]), 15)
        self.assertEqual(regs[2].cuerpo["serie"][0], (0.0, -0.001))
        self.assertEqual(regs[2].cuerpo["serie"][-1], (29.0, -0.001))

        self.assertEqual(regs[3].modo, "kinetics")
        self.assertEqual(len(regs[3].cuerpo["serie"]), 15)

    def test_adaptador_parsear_stream_serie_puebla_wl_y_metadatos(self):
        bloques = adaptador_txt.parsear_stream_serie(CAPTURA_CONSOLA_DATAWAY)
        self.assertEqual(len(bloques), 4)

        reg0, modo0, res0, _etq0 = bloques[0]
        self.assertEqual(modo0, "photometrics")
        self.assertAlmostEqual(res0[0]["wl"], 550.0)
        self.assertEqual(res0[0]["metodo"], "LOWRY")
        self.assertEqual(res0[0]["usuario"], "ALUMNOS")

        reg2, modo2, res2, _etq2 = bloques[2]
        self.assertEqual(modo2, "kinetics")
        self.assertAlmostEqual(res2[0]["wl"], 400.0)
        self.assertEqual(res2[0]["metodo"], "MéTODO POR DEFECTO")
        self.assertEqual(len(res2[0]["serie"]), 15)

    def test_multilenguaje_cabeceras_6_idiomas(self):
        muestra_fr = (
            "========================================\r\n"
            "MODE PHOTOMETRIE\r\n"
            "NOM DE METHODE:              TEST_FR\r\n"
            "LONGUEUR D'ONDE:             600.0NM\r\n"
            "OPERATEUR:                      JEAN\r\n"
            "========================================\r\n"
            "001 1.234ABS 5.8%T 12:00:00 19/10/26\r\n"
            "========================================\r\n"
        )
        regs = parser_txt.parsear_texto(muestra_fr)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].modo, "photometrics")
        self.assertEqual(regs[0].nombre_metodo, "TEST_FR")
        self.assertAlmostEqual(regs[0].longitud_onda, 600.0)
        self.assertEqual(regs[0].usuario, "JEAN")
        self.assertEqual(regs[0].cuerpo["filas"][0]["abs"], "1.234")


class TestSeguridadHardwarePuertoJenway(unittest.TestCase):
    """Verifica las 7 reglas de oro para no bloquear jamás la UART del Jenway 6705."""

    def test_whitelist_estricta_solo_asterisco_y_almohadilla(self):
        self.assertEqual(COMANDOS_PERMITIDOS, frozenset({b"*", b"#"}))
        self.assertEqual(BAUDRATE_6705, 57600)

    def test_bloquea_cualquier_comando_fuera_de_whitelist(self):
        drv = Jenway6705Serial(dormir=lambda _s: None)
        for prohibido in (b"*IDN?\r", b"D\r", b"*\r", b"#\n", b"\x05", b"", b"**"):
            with self.subTest(comando=prohibido):
                with self.assertRaises(ValueError):
                    drv._validar_comando(prohibido)

        sim = SimuladorJenway6705()
        for prohibido in (b"*IDN?\r", b"D\r", b"*\r", b"#\n", b"\x05"):
            with self.subTest(sim_comando=prohibido):
                with self.assertRaises(ValueError):
                    sim.write(prohibido)

    def test_simulador_rechaza_baudios_incorrectos_o_control_de_flujo(self):
        with self.assertRaises(ValueError):
            SimuladorJenway6705(baudrate=9600)
        with self.assertRaises(ValueError):
            SimuladorJenway6705(baudrate=57600, rtscts=True)
        with self.assertRaises(ValueError):
            SimuladorJenway6705(baudrate=57600, xonxoff=True)

    def test_handshake_conectar_y_solicitar_lectura_pause_and_look(self):
        reloj = [0.0]
        pausas = []

        def _reloj():
            return reloj[0]

        def _dormir(s):
            pausas.append(s)
            reloj[0] += float(s)

        drv = Jenway6705Serial(reloj=_reloj, dormir=_dormir)
        try:
            ok, msg = drv.conectar("SIMULADOR")
            self.assertTrue(ok, msg)
            self.assertEqual(drv.identificacion, "67XX")
            # Regla 3: la primera pausa tras abrir el puerto debe ser de 100 ms (0.100 s)
            self.assertAlmostEqual(pausas[0], 0.100)

            # Primera lectura '#' -> Fotométrico LOWRY
            r1 = drv.solicitar_lectura()
            self.assertTrue(r1.tiene_datos)
            self.assertEqual(len(r1.registros), 1)
            reg1, modo1, res1, _ = r1.registros[0]
            self.assertEqual(modo1, "photometrics")
            self.assertEqual(reg1.nombre_metodo, "LOWRY")
            self.assertAlmostEqual(res1[0]["abs"], 0.842)

            # Segunda lectura '#' -> Cinética
            r2 = drv.solicitar_lectura()
            self.assertEqual(len(r2.registros), 1)
            reg2, modo2, res2, _ = r2.registros[0]
            self.assertEqual(modo2, "kinetics")
            self.assertEqual(len(res2[0]["serie"]), 15)

            # Tercera lectura '#' -> Espectro
            r3 = drv.solicitar_lectura()
            self.assertEqual(len(r3.registros), 1)
            reg3, modo3, res3, _ = r3.registros[0]
            self.assertEqual(modo3, "spectrum")
            self.assertEqual(len(res3[0]["puntos"]), 11)
        finally:
            drv.desconectar()

    def test_captura_impresion_espontanea_boton_fisico_print(self):
        reloj = [0.0]
        drv = Jenway6705Serial(
            reloj=lambda: reloj[0],
            dormir=lambda s: reloj.__setitem__(0, reloj[0] + float(s)),
        )
        try:
            ok, _ = drv.conectar("SIMULADOR")
            self.assertTrue(ok)
            self.assertIsNone(drv.leer_impresion_espontanea())

            # Simulamos que el usuario pulsa el botón físico PRINT en el 6705
            drv._ser.inyectar_impresion_panel()
            imp = drv.leer_impresion_espontanea()
            self.assertIsNotNone(imp)
            self.assertTrue(imp.tiene_datos)
            self.assertEqual(len(imp.registros), 1)
        finally:
            drv.desconectar()


class TestRegistroVirtualYExportadores(unittest.TestCase):
    """Verifica el registro virtual serie:// y los exportadores PDF / JCAMP-DX."""

    def tearDown(self):
        reader.limpiar_virtuales()

    def test_registro_virtual_funciona_con_reader_y_exportar_y_pdf_y_jcamp(self):
        bloques = adaptador_txt.parsear_stream_serie(CAPTURA_CONSOLA_DATAWAY)
        reg_kin, modo_kin, res_kin, etqs_kin = bloques[2]  # Cinética

        loc_v = reader.registrar_virtual("serie://TEST_KIN_001", modo_kin, res_kin[0])
        tarjeta = Tarjeta(
            carpeta="(Sesión en vivo)",
            metodos=[
                Metodo(
                    id=1,
                    modo=modo_kin,
                    usuario=reg_kin.usuario or "ALUMNOS",
                    nombre=reg_kin.nombre_metodo or "Cinética",
                    fecha=reg_kin.fecha or "15/09/26",
                    filename=loc_v,
                    bloqueado=False,
                    muestras=[Muestra(indice=1, nombre="#001", fecha="15/09/26", loc=loc_v)],
                )
            ],
        )

        modo_dec, dic_dec = reader.decodificar_archivo(tarjeta, loc_v)
        self.assertEqual(modo_dec, "kinetics")
        self.assertIs(dic_dec, res_kin[0])

        with tempfile.TemporaryDirectory() as tmp:
            # 1. Exportar CSV desde lectura virtual
            rutas_csv = exportar.exportar_carpeta(tarjeta, tmp)
            self.assertGreaterEqual(len(rutas_csv), 1)
            self.assertTrue(os.path.isfile(rutas_csv[0]))

            # 2. Exportar PDF de vista
            ruta_pdf1 = os.path.join(tmp, "vista.pdf")
            exportar_vista_pdf(
                ruta_pdf=ruta_pdf1,
                modo=modo_kin,
                resultados=res_kin,
                etiquetas=etqs_kin,
                titulo="Prueba Cinética",
            )
            self.assertTrue(os.path.isfile(ruta_pdf1))
            with open(ruta_pdf1, "rb") as f:
                self.assertTrue(f.read(5).startswith(b"%PDF-"))

            # 3. Exportar PDF consolidado de tarjeta virtual
            ruta_pdf2 = os.path.join(tmp, "tarjeta.pdf")
            n_pags = exportar_tarjeta_pdf(tarjeta, ruta_pdf2)
            self.assertEqual(n_pags, 1)
            self.assertTrue(os.path.isfile(ruta_pdf2))

            # 4. Exportar JCAMP-DX 4.24 (.jdx)
            ruta_jdx = os.path.join(tmp, "cinetica.jdx")
            n_pts = exportar_jcamp_dx(
                ruta=ruta_jdx,
                modo=modo_kin,
                resultado=res_kin[0],
                titulo="Cinética 400nm",
                usuario="ALUMNOS",
            )
            self.assertEqual(n_pts, 15)
            self.assertTrue(os.path.isfile(ruta_jdx))
            texto_jdx = generar_jcamp_dx(modo_kin, res_kin[0], titulo="Cinética 400nm")
            self.assertIn("##JCAMP-DX= 4.24", texto_jdx)
            self.assertIn("##SPECTROMETER/DATA SYSTEM= Jenway 6705", texto_jdx)
            self.assertIn("##XYDATA= (X,Y)", texto_jdx)
            self.assertIn("##END=", texto_jdx)


class TestIntegracionVentanaSerie(unittest.TestCase):
    """Verifica la integración del panel de conexión serie en VentanaMaestro."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        reader.limpiar_virtuales()

    def test_conectar_simulador_y_recibir_lectura_en_arbol(self):
        from ui.ventana import VentanaMaestro

        v = VentanaMaestro()
        try:
            self.assertIsNotNone(v.panel_serie)
            self.assertIsNotNone(v.visor_consola)

            # Seleccionamos SIMULADOR y conectamos
            ok = v.panel_serie.conectar("SIMULADOR")
            self.assertTrue(ok)
            self.assertTrue(v.panel_serie.driver.conectado)

            # Capturamos una lectura '#' en vivo
            lectura = v.panel_serie.capturar_lectura()
            self.assertIsNotNone(lectura)
            self.assertTrue(lectura.tiene_datos)
            self.assertIsNotNone(v.tarjeta)
            self.assertEqual(len(v.tarjeta.metodos), 1)
            self.assertIn("MODO FOTOMETR", v.visor_consola.texto().upper())

            # Importamos la captura completa consoladataway.txt (4 registros: 2 foto + 2 cinética)
            n = v.importar_stream_serie(CAPTURA_CONSOLA_DATAWAY, origen="consoladataway.txt")
            self.assertEqual(n, 4)
            # LOWRY [RS-232] agrupa las 3 lecturas fotométricas y MéTODO POR DEFECTO [RS-232] las 2 cinéticas
            self.assertEqual(len(v.tarjeta.metodos), 2)
            total_muestras = sum(len(m.muestras) for m in v.tarjeta.metodos)
            self.assertEqual(total_muestras, 5)
        finally:
            v.close()

    def test_fotometria_continuacion_sin_cabecera_grafica_todas_las_barras(self):
        from ui.ventana import VentanaMaestro

        v = VentanaMaestro()
        try:
            ticket_001 = (
                "========================================\r\n"
                "PHOTOMETRICS MODE\r\n"
                "INSTRUMENT ID:              67XX V1.64.5\r\n"
                "USER ID:                      SUPERVISOR\r\n"
                "METHOD:                   DEFAULT METHOD\r\n"
                "BATCH ID:                  DEFAULT BATCH\r\n"
                "WAVELENGTH:                        400.0\r\n"
                "AUTO SAVE:                           OFF\r\n"
                "LAST CALIBRATED:       12:18:12 19/10/26\r\n"
                "========================================\r\n"
                "001 -0.012ABS 102.8%T 12:18:12 19/10/26\r\n"
            )
            # El 6705 envía las siguientes lecturas del mismo lote SIN cabecera '===='
            ticket_002 = "002 3.000ABS 0.0%T 12:18:55 19/10/26\r\n"

            n1 = v.importar_stream_serie(ticket_001, origen="COM3")
            self.assertEqual(n1, 1)
            self.assertEqual(len(v.panel._resultados), 1)

            n2 = v.importar_stream_serie(ticket_002, origen="COM3")
            self.assertEqual(n2, 1)
            # Deben pertenecer al mismo método DEFAULT METHOD [RS-232] y graficarse las 2 barras juntas
            self.assertEqual(len(v.tarjeta.metodos), 1)
            self.assertEqual(len(v.tarjeta.metodos[0].muestras), 2)
            self.assertEqual(len(v.panel._resultados), 2)
            self.assertAlmostEqual(v.panel._resultados[0]["abs"], -0.012)
            self.assertAlmostEqual(v.panel._resultados[1]["abs"], 3.000)
            self.assertAlmostEqual(v.panel._resultados[1]["wl"], 400.0)
            self.assertEqual(len(v.modelo_datos.filas()), 2)
        finally:
            v.close()

    def test_cuantificacion_serie_con_cabecera_modo_fotometria_y_continuacion(self):
        from ui.ventana import VentanaMaestro

        v = VentanaMaestro()
        try:
            # Ticket exacto capturado del Jenway 6705 V1.64.5 en español por RS-232:
            # el firmware imprime "MODO FOTOMETRíA....." aunque tenga estándares STD 1..5 y muestras en PPM.
            ticket_quant_1 = (
                "========================================\r\n"
                "MODO FOTOMETRíA.....\r\n"
                "ID INSTRUMENTO:             67XX V1.64.5\r\n"
                "NOMBRE DE USUARIO:               ALUMNOS\r\n"
                "MéTODO:               MéTODO POR DEFECTO\r\n"
                "ID DE LOTE:             LOTE POR DEFECTO\r\n"
                "LONGITUD DE ONDA:                584.0NM\r\n"
                "NúMERO DE ESTáND. USADOS:              5\r\n"
                "STD 1:    0.00      RESULTADO 1:    0.00\r\n"
                "STD 2:    1.00      RESULTADO 2:    0.00\r\n"
                "STD 3:    2.00      RESULTADO 3:    0.00\r\n"
                "STD 4:    3.00      RESULTADO 4:    0.00\r\n"
                "STD 5:    4.00      RESULTADO 5:    0.00\r\n"
                "AJUSTE DE CURVA:           INTERPOLACIóN\r\n"
                "SEGURIDAD DE MéTODO:            PERSONAL\r\n"
                "ESCALA AUTOMáTICA:              ACTIVADO\r\n"
                "MíNIMO EJE Y:                       -0.3\r\n"
                "MáXIMO EJE Y:                        3.0\r\n"
                "úLTIMA CALIBRACIóN:    12:50:57 19/10/26\r\n"
                "========================================\r\n"
                "001  3.000ABS    0.00PPM 12:51:23\r\n"
            )
            ticket_quant_2 = "002  1.500ABS    2.00PPM 12:52:00\r\n"

            n1 = v.importar_stream_serie(ticket_quant_1, origen="COM3")
            self.assertEqual(n1, 1)
            self.assertEqual(len(v.tarjeta.metodos), 1)
            self.assertEqual(v.tarjeta.metodos[0].modo, "quantitation")
            self.assertEqual(v.panel._modo, "quantitation")
            self.assertEqual(len(v.panel._resultados), 1)
            self.assertEqual(len(v.panel._resultados[0]["estandares"]), 5)
            self.assertAlmostEqual(v.panel._resultados[0]["abs_muestra"], 3.000)
            self.assertAlmostEqual(v.panel._resultados[0]["conc_muestra"], 0.00)
            self.assertEqual(v.panel._resultados[0]["unidades"], "PPM")

            # Segunda lectura sin cabecera: hereda estándares y se grafica sobre la misma curva
            n2 = v.importar_stream_serie(ticket_quant_2, origen="COM3")
            self.assertEqual(n2, 1)
            self.assertEqual(len(v.tarjeta.metodos), 1)
            self.assertEqual(len(v.tarjeta.metodos[0].muestras), 2)
            self.assertEqual(len(v.panel._resultados), 2)
            self.assertEqual(len(v.panel._resultados[1]["estandares"]), 5)
            self.assertAlmostEqual(v.panel._resultados[1]["abs_muestra"], 1.500)
            self.assertAlmostEqual(v.panel._resultados[1]["conc_muestra"], 2.00)
            # 5 estándares + 2 muestras en la tabla de datos
            self.assertEqual(len(v.modelo_datos.filas()), 7)
        finally:
            v.close()


class TestFase3YSpectragryph(unittest.TestCase):
    """Pruebas de cálculo de FWHM, integración de banda (AUC), umbral de picos y cadenas en lote."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        reader.limpiar_virtuales()

    def test_fwhm_gaussiano_e_integracion_banda(self):
        import math
        import numpy as np
        from jenway67 import analisis as an

        # Pico gaussiano centrado en 500 nm con sigma = 10 nm
        wl = np.linspace(400.0, 600.0, 2001)
        sigma = 10.0
        gauss = np.exp(-0.5 * ((wl - 500.0) / sigma) ** 2)
        puntos = [(float(w), float(100.0 * 10 ** (-a)), float(a)) for w, a in zip(wl, gauss)]

        fwhm_teorico = 2.0 * math.sqrt(2.0 * math.log(2.0)) * sigma
        fwhm_calc = an.fwhm_pico(wl, gauss, 1000)
        self.assertIsNotNone(fwhm_calc)
        self.assertAlmostEqual(fwhm_calc, fwhm_teorico, places=2)

        pks = an.picos(puntos, prominencia=1e-5)
        self.assertEqual(len(pks), 1)
        self.assertIsNotNone(pks[0]["fwhm"])
        self.assertAlmostEqual(pks[0]["fwhm"], fwhm_teorico, places=2)

        # Integración de banda con base inclinada: el área neta debe aislar el pico
        base_lineal = 0.1 + 0.002 * (wl - 400.0)
        puntos_con_base = [
            (float(w), 50.0, float(g + b)) for w, g, b in zip(wl, gauss, base_lineal)
        ]
        info_pura = an.integrar_banda(puntos, 450.0, 550.0)
        info_base = an.integrar_banda(puntos_con_base, 450.0, 550.0)
        self.assertAlmostEqual(info_base["area_neta"], info_pura["area_neta"], places=4)
        self.assertGreater(info_base["area_bruta"], info_base["area_neta"])
        self.assertAlmostEqual(info_base["max_wl"], 500.0, places=0)

    def test_controles_fwhm_prominencia_banda_y_lote_en_ventana(self):
        import numpy as np
        from ui.ventana import VentanaMaestro

        v = VentanaMaestro()
        try:
            # Espectro con pico agudo en 500 nm para superar prominencia de 1 paso
            wl = np.linspace(400.0, 600.0, 41)
            a1 = np.exp(-0.5 * ((wl - 500.0) / 8.0) ** 2) * 0.9
            a2 = np.exp(-0.5 * ((wl - 500.0) / 8.0) ** 2) * 1.8
            r1 = {"modo": "spectrum", "n": 41, "puntos": [(float(w), 50.0, float(a)) for w, a in zip(wl, a1)]}
            r2 = {"modo": "spectrum", "n": 41, "puntos": [(float(w), 50.0, float(a)) for w, a in zip(wl, a2)]}
            loc1 = reader.registrar_virtual("serie://ESP_1", "spectrum", r1)
            loc2 = reader.registrar_virtual("serie://ESP_2", "spectrum", r2)
            v.tarjeta = Tarjeta(
                carpeta="(Test)",
                metodos=[
                    Metodo(
                        id=1,
                        modo="spectrum",
                        usuario="TEST",
                        nombre="Barrido UV",
                        fecha="19/10/26",
                        filename=loc1,
                        bloqueado=False,
                        muestras=[
                            Muestra(indice=1, nombre="M1", fecha="19/10/26", loc=loc1),
                            Muestra(indice=2, nombre="M2", fecha="19/10/26", loc=loc2),
                        ],
                    )
                ],
            )
            v._poblar_arbol()
            v.seleccionar_metodo(0)

            # Activar etiqueta FWHM en el gráfico
            v.panel.chk_fwhm.setChecked(True)
            textos = [t.get_text() for t in v.panel.ax.texts]
            self.assertTrue(any("FWHM" in t for t in textos), textos)

            # Integrar banda desde el panel de procesado
            v.panel_proc.txt_banda_min.setText("460")
            v.panel_proc.txt_banda_max.setText("540")
            v.panel_proc.btn_integrar_banda.click()
            self.assertIsNotNone(v.panel._banda)
            self.assertIn("Área neta", v.panel_proc.lbl_banda.text())

            # Limpiar banda
            v.panel_proc.btn_limpiar_banda.click()
            self.assertIsNone(v.panel._banda)

            # Aplicar cadena en lote a todas las muestras del método
            v._cadena_de(0).agregar("normalizar", modo="max")
            v.panel_proc._refrescar_cadena()
            v.panel_proc.btn_aplicar_todas.click()
            self.assertEqual(len(v._cadena_de(1)), 1)
            self.assertEqual(v._cadena_de(1).pasos[0]["clave"], "normalizar")
        finally:
            v.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

