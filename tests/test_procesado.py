# -*- coding: utf-8 -*-
"""Pruebas del procesado espectral (Fase 3).

Sin dependencias nuevas: scipy se usa SOLO como oraculo de referencia para
comprobar que Savitzky-Golay coincide con `scipy.signal.savgol_filter`.
"""
import os
import sys
import unittest

import numpy as np

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from jenway67 import procesado as pr  # noqa: E402

try:
    from scipy.signal import savgol_filter as _scipy_savgol

    HAY_SCIPY = True
except Exception:  # pragma: no cover
    HAY_SCIPY = False


def espectro_sintetico(n=1001, wl0=400.0, paso=0.1):
    """Espectro con linea base inclinada + pico gaussiano centrado en 450 nm."""
    wl = wl0 + paso * np.arange(n, dtype=float)
    base = 0.05 + 0.0005 * (wl - wl0)
    pico = 0.8 * np.exp(-((wl - 450.0) ** 2) / (2 * 3.0 ** 2))
    return wl, base + pico


def recorta_bordes(valores, mitad):
    """Solo el interior: en los bordes cada metodo usa su propio criterio."""
    return np.asarray(valores, dtype=float)[mitad: len(valores) - mitad]


class TestSavitzkyGolay(unittest.TestCase):
    def test_coeficientes_clasicos(self):
        """Ventana 5, orden 2 -> (-3, 12, 17, 12, -3)/35."""
        esperado = np.array([-3.0, 12.0, 17.0, 12.0, -3.0]) / 35.0
        np.testing.assert_allclose(pr.coef_savgol(5, 2), esperado, atol=1e-12)

    def test_coeficientes_suman_uno(self):
        for ventana in (5, 7, 9, 11):
            np.testing.assert_allclose(pr.coef_savgol(ventana, 2).sum(), 1.0, atol=1e-12)

    def test_coeficientes_de_derivada_suman_cero(self):
        for ventana in (5, 7, 9):
            np.testing.assert_allclose(pr.coef_savgol(ventana, 2, derivada=1).sum(),
                                       0.0, atol=1e-12)

    def test_reproduce_una_recta(self):
        x = np.arange(101.0)
        y = 3.0 + 0.7 * x
        salida = pr.savgol(y, ventana=9, orden=1)
        np.testing.assert_allclose(recorta_bordes(salida, 4), recorta_bordes(y, 4),
                                   atol=1e-9)

    def test_reproduce_una_parabola(self):
        x = np.arange(101.0)
        y = 2.0 - 0.5 * x + 0.03 * x ** 2
        salida = pr.savgol(y, ventana=9, orden=2)
        np.testing.assert_allclose(recorta_bordes(salida, 4), recorta_bordes(y, 4),
                                   atol=1e-9)

    def test_disminuye_el_ruido(self):
        generador = np.random.default_rng(1234)
        y = np.full(501, 1.0) + generador.normal(0, 0.01, 501)
        salida = pr.savgol(y, ventana=11, orden=2)
        self.assertLess(np.std(salida), np.std(y))

    def test_derivada_de_una_parabola(self):
        """dy/dx = 2x con y = x^2, a traves del registro de operaciones."""
        x = np.arange(101.0)
        _wl, derivada = pr.aplicar("derivar", x, x ** 2, orden=1, ventana=9, polinomio=2)
        np.testing.assert_allclose(recorta_bordes(derivada, 4), recorta_bordes(2 * x, 4),
                                   atol=1e-8)

    def test_la_derivada_respeta_el_espaciado_de_lambda(self):
        """Con paso 0,1 nm la derivada debe ir en Abs/nm, no en Abs/punto."""
        wl = 400.0 + 0.1 * np.arange(501, dtype=float)
        y = (wl - 400.0) ** 2
        _wl2, derivada = pr.aplicar("derivar", wl, y, orden=1, ventana=9, polinomio=2)
        np.testing.assert_allclose(recorta_bordes(derivada, 4),
                                   recorta_bordes(2 * (wl - 400.0), 4), atol=1e-6)

    def test_validaciones(self):
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(20.0), ventana=8)          # par
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(20.0), ventana=1)          # menor que 3
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(20.0), ventana=5, orden=5)  # ventana <= orden
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(20.0), ventana=7, orden=1, derivada=2)

    def test_modo_de_borde_invalido(self):
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(20.0), ventana=5, modo="inventado")

    def test_ventana_demasiado_grande(self):
        with self.assertRaises(ValueError):
            pr.savgol(np.arange(4.0), ventana=9)

    def test_serie_muy_corta_se_devuelve_tal_cual(self):
        np.testing.assert_allclose(pr.savgol(np.array([1.0, 2.0])), [1.0, 2.0])


class TestSavgolContraScipy(unittest.TestCase):
    """scipy solo como oraculo: nuestro numpy debe dar lo mismo en el interior."""

    @unittest.skipUnless(HAY_SCIPY, "scipy no disponible (solo se usa como oraculo)")
    def test_coincide_en_el_interior(self):
        _wl, y = espectro_sintetico()
        for ventana, orden in ((5, 2), (7, 2), (9, 3), (11, 2), (15, 4)):
            for derivada in (0, 1, 2):
                if derivada > orden:
                    continue
                with self.subTest(ventana=ventana, orden=orden, derivada=derivada):
                    mio = pr.savgol(y, ventana=ventana, orden=orden, derivada=derivada)
                    referencia = _scipy_savgol(y, ventana, orden, deriv=derivada,
                                               delta=1.0, mode="interp")
                    mitad = ventana // 2
                    np.testing.assert_allclose(
                        mio[mitad: len(y) - mitad],
                        referencia[mitad: len(y) - mitad],
                        atol=1e-9, rtol=0,
                    )


class TestSuavizadosSimples(unittest.TestCase):
    def test_media_movil_conserva_una_constante(self):
        y = np.full(101, 2.5)
        np.testing.assert_allclose(pr.media_movil(y, ventana=7), y, atol=1e-12)

    def test_media_movil_conserva_una_recta_en_el_interior(self):
        y = 1.0 + 0.02 * np.arange(101.0)
        np.testing.assert_allclose(recorta_bordes(pr.media_movil(y, ventana=7), 3),
                                   recorta_bordes(y, 3), atol=1e-12)

    def test_mediana_movil_quita_un_pico_aislado(self):
        y = np.full(101, 1.0)
        y[50] = 99.0
        salida = pr.mediana_movil(y, ventana=5)
        self.assertAlmostEqual(salida[50], 1.0, places=9)
        np.testing.assert_allclose(salida, np.full(101, 1.0), atol=1e-12)

    def test_mediana_movil_conserva_una_constante(self):
        y = np.full(51, -0.3)
        np.testing.assert_allclose(pr.mediana_movil(y, ventana=5), y, atol=1e-12)

    def test_despike_quita_el_pico_aislado(self):
        y = np.full(201, 0.5)
        y[100] = 3.0
        salida = pr.despike(y, ventana=5, umbral=3.0)
        self.assertAlmostEqual(salida[100], 0.5, places=9)

    def test_despike_no_toca_una_senal_suave(self):
        _wl, y = espectro_sintetico()
        np.testing.assert_allclose(pr.despike(y, ventana=5, umbral=3.0), y, atol=1e-12)

    def test_despike_sobre_una_senal_ruidosa_solo_toca_lo_evidente(self):
        generador = np.random.default_rng(7)
        y = np.full(401, 0.4) + generador.normal(0, 0.005, 401)
        con_picos = y.copy()
        con_picos[100] += 1.0
        con_picos[300] -= 1.0
        salida = pr.despike(con_picos, ventana=5, umbral=3.0)
        self.assertNotAlmostEqual(salida[100], con_picos[100], places=3)
        self.assertNotAlmostEqual(salida[300], con_picos[300], places=3)
        # El resto del espectro debe quedar practicamente igual.
        self.assertLess(np.mean(np.abs(salida - con_picos)), 0.01)

    def test_despike_validacion(self):
        with self.assertRaises(ValueError):
            pr.despike(np.arange(20.0), ventana=4)


class TestLineaBase(unittest.TestCase):
    def test_offset_minimo(self):
        y = np.array([0.2, 0.5, 0.9, 0.4])
        np.testing.assert_allclose(pr.restar_offset(y, "minimo"), y - 0.2, atol=1e-12)

    def test_offset_media_y_mediana(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        np.testing.assert_allclose(pr.restar_offset(y, "media"), y - 2.5, atol=1e-12)
        np.testing.assert_allclose(pr.restar_offset(y, "mediana"), y - 2.5, atol=1e-12)

    def test_offset_valor(self):
        y = np.array([1.0, 2.0])
        np.testing.assert_allclose(pr.restar_offset(y, "valor", valor=0.75), y - 0.75,
                                   atol=1e-12)

    def test_offset_metodo_invalido(self):
        with self.assertRaises(ValueError):
            pr.restar_offset(np.arange(5.0), "inventado")

    def test_lineal_deja_cero_en_las_anclas(self):
        wl, y = espectro_sintetico()
        corregido = pr.corregir_lineal(wl, y, 400.0, 500.0)
        self.assertAlmostEqual(float(np.interp(400.0, wl, corregido)), 0.0, places=9)
        self.assertAlmostEqual(float(np.interp(500.0, wl, corregido)), 0.0, places=9)
        # El pico sigue ahi (no se lo lleva la recta).
        self.assertGreater(float(np.interp(450.0, wl, corregido)), 0.5)

    def test_lineal_con_anclas_iguales_falla(self):
        wl, y = espectro_sintetico()
        with self.assertRaises(ValueError):
            pr.corregir_lineal(wl, y, 450.0, 450.0)

    def test_polinomica_deja_cero_en_las_anclas(self):
        wl = 400.0 + 0.1 * np.arange(1001, dtype=float)
        base = 0.1 + 0.002 * (wl - 400.0) ** 2 / 100.0
        pico = 0.5 * np.exp(-((wl - 450.0) ** 2) / (2 * 2.0 ** 2))
        y = base + pico
        anclas = [400.0, 420.0, 480.0, 500.0]
        corregido = pr.corregir_polinomica(wl, y, anclas, orden=2)
        for ancla in anclas:
            self.assertLess(abs(float(np.interp(ancla, wl, corregido))), 0.02)

    def test_polinomica_con_pocas_anclas_falla(self):
        wl, y = espectro_sintetico()
        with self.assertRaises(ValueError):
            pr.corregir_polinomica(wl, y, [450.0], orden=2)
        with self.assertRaises(ValueError):
            pr.corregir_polinomica(wl, y, [440.0, 460.0], orden=2)

    def test_snip_no_toca_una_constante(self):
        y = np.full(101, 0.42)
        np.testing.assert_allclose(pr.corregir_snip(None, y, 40), np.zeros(101), atol=1e-9)

    def test_snip_apenas_erosiona_una_recta(self):
        """SNIP tiene un sesgo conocido (minima erosión); se acota, no se ignora."""
        wl = 400.0 + 0.1 * np.arange(1001, dtype=float)
        y = 0.2 + 0.002 * (wl - 400.0)
        corregido = pr.corregir_snip(wl, y, 40)
        self.assertLess(float(np.max(np.abs(corregido))), 0.02)

    def test_snip_recupera_un_pico_estrecho_sobre_la_linea_base(self):
        wl = 400.0 + 0.1 * np.arange(1001, dtype=float)
        base = 0.1 + 0.002 * (wl - 400.0)
        pico = 0.7 * np.exp(-((wl - 450.0) ** 2) / (2 * 1.5 ** 2))
        corregido = pr.corregir_snip(wl, base + pico, 40)
        # Lejos del pico la correccion debe ser ~0.
        self.assertLess(abs(float(np.interp(420.0, wl, corregido))), 0.02)
        self.assertLess(abs(float(np.interp(480.0, wl, corregido))), 0.02)
        # Y el pico debe sobrevivir casi entero.
        self.assertAlmostEqual(float(np.interp(450.0, wl, corregido)), 0.7, delta=0.07)

    def test_snip_tolera_absorbancias_negativas(self):
        wl = 400.0 + 0.1 * np.arange(301, dtype=float)
        y = -0.2 + 0.001 * (wl - 400.0)
        salida = pr.snip(y, 20)
        self.assertTrue(np.all(np.isfinite(salida)))
        self.assertLess(float(np.max(np.abs(salida - y))), 0.05)


class TestNormalizacion(unittest.TestCase):
    def setUp(self):
        self.wl, self.y = espectro_sintetico()

    def test_max(self):
        salida = pr.normalizar(self.y, "max")
        self.assertAlmostEqual(float(np.max(salida)), 1.0, places=12)

    def test_minmax(self):
        salida = pr.normalizar(self.y, "minmax")
        self.assertAlmostEqual(float(np.min(salida)), 0.0, places=12)
        self.assertAlmostEqual(float(np.max(salida)), 1.0, places=12)

    def test_l2(self):
        salida = pr.normalizar(self.y, "l2")
        self.assertAlmostEqual(float(np.linalg.norm(salida)), 1.0, places=12)

    def test_area(self):
        salida = pr.normalizar(self.y, "area", wl=self.wl)
        area = float(np.trapezoid(salida, self.wl) if hasattr(np, "trapezoid")
                     else np.trapz(salida, self.wl))
        self.assertAlmostEqual(area, 1.0, places=9)

    def test_snv(self):
        salida = pr.normalizar(self.y, "snv")
        self.assertAlmostEqual(float(np.mean(salida)), 0.0, places=12)
        self.assertAlmostEqual(float(np.std(salida)), 1.0, places=12)

    def test_ninguna_es_copia(self):
        salida = pr.normalizar(self.y, "ninguna")
        np.testing.assert_allclose(salida, self.y, atol=1e-15)
        self.assertIsNot(salida, self.y)

    def test_en_wl(self):
        salida = pr.normalizar(self.y, "en_wl", wl=self.wl, wl_ref=430.0)
        self.assertAlmostEqual(float(np.interp(430.0, self.wl, salida)), 1.0, places=9)

    def test_en_wl_sin_referencia_falla(self):
        with self.assertRaises(ValueError):
            pr.normalizar(self.y, "en_wl", wl=self.wl)

    def test_area_sin_wl_falla(self):
        with self.assertRaises(ValueError):
            pr.normalizar(self.y, "area")

    def test_modo_invalido(self):
        with self.assertRaises(ValueError):
            pr.normalizar(self.y, "inventado")

    def test_espectro_plano_da_ceros(self):
        np.testing.assert_allclose(pr.normalizar(np.full(10, 0.5), "minmax"),
                                   np.zeros(10), atol=1e-12)

    def test_espectro_de_ceros_no_revienta(self):
        np.testing.assert_allclose(pr.normalizar(np.zeros(10), "max"),
                                   np.zeros(10), atol=1e-12)


class TestSeleccionEInterpolacion(unittest.TestCase):
    def setUp(self):
        self.wl, self.y = espectro_sintetico()

    def test_recortar(self):
        wl2, y2 = pr.recortar(self.wl, self.y, 420.0, 480.0)
        self.assertAlmostEqual(float(wl2[0]), 420.0, places=9)
        self.assertAlmostEqual(float(wl2[-1]), 480.0, places=9)
        self.assertEqual(wl2.size, y2.size)
        self.assertLess(wl2.size, self.wl.size)

    def test_recortar_sin_limites_devuelve_todo(self):
        wl2, y2 = pr.recortar(self.wl, self.y)
        self.assertEqual(wl2.size, self.wl.size)

    def test_interpolar_es_exacto_en_una_recta(self):
        wl = np.arange(10.0)
        y = 2.0 * wl + 1.0
        destino = np.array([2.5, 4.5, 6.0])
        np.testing.assert_allclose(pr.interpolar(wl, y, destino), 2.0 * destino + 1.0,
                                   atol=1e-12)

    def test_interpolar_fuera_da_nan(self):
        wl = np.arange(10.0)
        y = wl.copy()
        salida = pr.interpolar(wl, y, np.array([-5.0, 5.0, 99.0]), fuera="nan")
        self.assertTrue(np.isnan(salida[0]))
        self.assertTrue(np.isnan(salida[2]))
        self.assertFalse(np.isnan(salida[1]))

    def test_interpolar_fuera_usa_el_borde(self):
        wl = np.arange(10.0)
        y = wl.copy()
        salida = pr.interpolar(wl, y, np.array([-5.0, 99.0]), fuera="borde")
        np.testing.assert_allclose(salida, [0.0, 9.0], atol=1e-12)

    def test_interpolar_fuera_invalido(self):
        with self.assertRaises(ValueError):
            pr.interpolar(np.arange(5.0), np.arange(5.0), np.array([1.0]), fuera="loquesea")

    def test_rejilla_comun_interseccion(self):
        rejilla = pr.rejilla_comun([np.arange(400.0, 501.0), np.arange(450.0, 601.0)])
        self.assertAlmostEqual(float(rejilla[0]), 450.0, places=9)
        self.assertAlmostEqual(float(rejilla[-1]), 500.0, places=9)

    def test_rejilla_comun_union(self):
        rejilla = pr.rejilla_comun([np.arange(400.0, 501.0), np.arange(450.0, 601.0)],
                                   usar="union")
        self.assertAlmostEqual(float(rejilla[0]), 400.0, places=9)
        self.assertAlmostEqual(float(rejilla[-1]), 600.0, places=9)

    def test_rejilla_comun_toma_el_paso_mas_fino(self):
        fina = 400.0 + 0.1 * np.arange(1001, dtype=float)
        gruesa = np.arange(400.0, 501.0)
        rejilla = pr.rejilla_comun([gruesa, fina])
        paso = float(np.min(np.diff(rejilla)))
        self.assertAlmostEqual(paso, 0.1, places=9)

    def test_rejilla_comun_sin_solape(self):
        self.assertEqual(pr.rejilla_comun([np.arange(400.0, 411.0),
                                           np.arange(500.0, 511.0)]).size, 0)


class TestOperacionesEntreEspectros(unittest.TestCase):
    def setUp(self):
        self.wl, self.y = espectro_sintetico()

    def test_resta_de_iguales_da_cero(self):
        _wl, resultado = pr.operar(self.wl, self.y, self.wl, self.y, "resta")
        np.testing.assert_allclose(resultado, np.zeros(resultado.size), atol=1e-12)

    def test_cociente_de_iguales_da_uno(self):
        _wl, resultado = pr.operar(self.wl, self.y, self.wl, self.y, "cociente")
        np.testing.assert_allclose(resultado, np.ones(resultado.size), atol=1e-12)

    def test_media(self):
        _wl, resultado = pr.operar(self.wl, self.y, self.wl, 2 * self.y, "media")
        np.testing.assert_allclose(resultado, 1.5 * self.y, atol=1e-12)

    def test_suma_y_producto(self):
        _wl, suma = pr.operar(self.wl, self.y, self.wl, self.y, "suma")
        np.testing.assert_allclose(suma, 2 * self.y, atol=1e-12)
        _wl, producto = pr.operar(self.wl, self.y, self.wl, self.y, "producto")
        np.testing.assert_allclose(producto, self.y ** 2, atol=1e-12)

    def test_rejillas_distintas(self):
        """Un metodo de 1 nm y otro de 0,1 nm deben poder operarse.

        Con una senal lineal la interpolacion es exacta, asi que la resta tiene
        que dar cero clavado.
        """
        fina_wl = 400.0 + 0.1 * np.arange(1001, dtype=float)
        fina_y = 0.1 + 0.002 * (fina_wl - 400.0)
        gruesa_wl = np.arange(420.0, 481.0)
        gruesa_y = 0.1 + 0.002 * (gruesa_wl - 400.0)
        wl, resultado = pr.operar(fina_wl, fina_y, gruesa_wl, gruesa_y, "resta")
        np.testing.assert_allclose(resultado, np.zeros(resultado.size), atol=1e-12)
        self.assertAlmostEqual(float(wl[0]), 420.0, places=9)
        self.assertAlmostEqual(float(wl[-1]), 480.0, places=9)

    def test_rejillas_distintas_con_pico_el_error_esta_acotado(self):
        """Con un pico, remuestrear a 1 nm introduce un error pequeno y medible."""
        fina_wl, fina_y = espectro_sintetico()
        gruesa_wl = np.arange(420.0, 481.0)
        gruesa_y = np.interp(gruesa_wl, fina_wl, fina_y)
        _wl, resultado = pr.operar(fina_wl, fina_y, gruesa_wl, gruesa_y, "resta")
        self.assertLess(float(np.max(np.abs(resultado))), 0.02)
        self.assertGreater(float(np.max(np.abs(resultado))), 0.0)

    def test_sin_solape_falla(self):
        with self.assertRaises(ValueError):
            pr.operar(np.arange(400.0, 411.0), np.ones(11),
                      np.arange(500.0, 511.0), np.ones(11), "resta")

    def test_cociente_por_cero_da_nan_sin_reventar(self):
        _wl, resultado = pr.operar(self.wl, self.y, self.wl, np.zeros_like(self.y),
                                   "cociente")
        self.assertTrue(np.all(np.isnan(resultado)))

    def test_operacion_invalida(self):
        with self.assertRaises(ValueError):
            pr.operar(self.wl, self.y, self.wl, self.y, "inventada")


class TestFormatoDelProyecto(unittest.TestCase):
    def test_ida_y_vuelta(self):
        wl, y = espectro_sintetico(n=201)
        puntos = pr.a_puntos(wl, y)
        self.assertEqual(len(puntos), 201)
        wl2, y2 = pr.desde_puntos(puntos)
        np.testing.assert_allclose(wl2, wl, atol=1e-9)
        np.testing.assert_allclose(y2, y, atol=1e-12)

    def test_transmitancia_recalculada(self):
        puntos = pr.a_puntos(np.array([500.0]), np.array([1.0]))
        _wl, transmitancia, absorbancia = puntos[0]
        self.assertAlmostEqual(transmitancia, 10.0, places=9)
        self.assertAlmostEqual(absorbancia, 1.0, places=12)
        # La identidad del instrumento se mantiene.
        self.assertAlmostEqual(-np.log10(transmitancia / 100.0), absorbancia, places=12)

    def test_a_puntos_con_absorbancia_saturada(self):
        """Con absorbancia altisima la transmitancia se va a ~0 (no da error)."""
        puntos = pr.a_puntos(np.array([500.0]), np.array([50.0]))
        self.assertLess(puntos[0][1], 1e-30)
        self.assertTrue(np.isfinite(puntos[0][1]))


class TestRegistro(unittest.TestCase):
    def test_todas_las_operaciones_tienen_metadatos(self):
        self.assertTrue(pr.OPERACIONES)
        for clave, operacion in pr.OPERACIONES.items():
            with self.subTest(clave=clave):
                self.assertEqual(clave, operacion.clave)
                self.assertTrue(operacion.etiqueta)
                self.assertTrue(operacion.grupo)
                self.assertTrue(callable(operacion.fn))

    def test_grupos_y_operaciones_de(self):
        grupos = pr.grupos()
        self.assertIn("Suavizado", grupos)
        self.assertIn("Linea base", grupos)
        self.assertIn("Normalizacion", grupos)
        self.assertIn("Derivadas", grupos)
        self.assertIn("Seleccion", grupos)
        total = sum(len(pr.operaciones_de(g)) for g in grupos)
        self.assertEqual(total, len(pr.OPERACIONES))

    def test_todas_corren_con_sus_defectos_y_conservan_longitud(self):
        wl, y = espectro_sintetico(n=301)
        for clave in pr.OPERACIONES:
            with self.subTest(clave=clave):
                wl2, y2 = pr.aplicar(clave, wl, y)
                self.assertEqual(wl2.size, y2.size)
                self.assertEqual(wl2.size, wl.size)

    def test_los_defectos_respetan_el_tipo_declarado(self):
        for operacion in pr.OPERACIONES.values():
            for parametro in operacion.parametros:
                with self.subTest(clave=operacion.clave, parametro=parametro.nombre):
                    if parametro.tipo == "int":
                        self.assertIsInstance(parametro.defecto, int)
                    elif parametro.tipo == "float":
                        self.assertIsInstance(parametro.defecto, float)
                    elif parametro.tipo == "lista":
                        self.assertIn(parametro.defecto, parametro.opciones)

    def test_aplicar_ignora_parametros_desconocidos(self):
        wl, y = espectro_sintetico(n=101)
        wl2, y2 = pr.aplicar("suavizar_savgol", wl, y, inventado=5)
        self.assertEqual(y2.size, y.size)

    def test_aplicar_clave_desconocida(self):
        with self.assertRaises(ValueError):
            pr.aplicar("no_existe", np.arange(5.0), np.arange(5.0))

    def test_parsear_anclas(self):
        self.assertEqual(pr.parsear_anclas("400, 450;500"), [400.0, 450.0, 500.0])
        self.assertEqual(pr.parsear_anclas([400, 450]), [400.0, 450.0])

    def test_parsear_anclas_invalidas(self):
        with self.assertRaises(ValueError):
            pr.parsear_anclas("400, cuatrocientos")
        with self.assertRaises(ValueError):
            pr.parsear_anclas("")


class TestCadena(unittest.TestCase):
    def setUp(self):
        self.wl, self.y = espectro_sintetico(n=301)

    def test_cadena_vacia_devuelve_lo_mismo(self):
        wl2, y2 = pr.Cadena().aplicar(self.wl, self.y)
        np.testing.assert_allclose(y2, self.y, atol=1e-15)

    def test_aplicar_igual_que_una_a_una(self):
        cadena = pr.Cadena()
        cadena.agregar("suavizar_savgol", ventana=9, orden=2)
        cadena.agregar("linea_snip", iteraciones=20)
        cadena.agregar("normalizar", modo="max")
        _wl_a, esperado = pr.aplicar("suavizar_savgol", self.wl, self.y, ventana=9, orden=2)
        _wl_a, esperado = pr.aplicar("linea_snip", self.wl, esperado, iteraciones=20)
        _wl_a, esperado = pr.aplicar("normalizar", self.wl, esperado, modo="max")
        _wl_b, obtenido = cadena.aplicar(self.wl, self.y)
        np.testing.assert_allclose(obtenido, esperado, atol=1e-12)

    def test_no_modifica_la_entrada(self):
        original = self.y.copy()
        cadena = pr.Cadena()
        cadena.agregar("normalizar", modo="max")
        cadena.agregar("derivar", orden=1, ventana=9, polinomio=2)
        cadena.aplicar(self.wl, self.y)
        np.testing.assert_allclose(self.y, original, atol=1e-15)

    def test_deshacer(self):
        cadena = pr.Cadena().agregar("normalizar", modo="max")
        self.assertTrue(cadena.deshacer())
        self.assertEqual(len(cadena), 0)
        self.assertFalse(cadena.deshacer())

    def test_quitar_y_limpiar(self):
        cadena = pr.Cadena().agregar("normalizar", modo="max").agregar("linea_snip")
        cadena.quitar(0)
        self.assertEqual(len(cadena), 1)
        self.assertEqual(cadena.pasos[0]["clave"], "linea_snip")
        cadena.limpiar()
        self.assertEqual(len(cadena), 0)

    def test_copia_es_independiente(self):
        original = pr.Cadena().agregar("normalizar", modo="max")
        copia = original.copia()
        copia.agregar("linea_snip")
        copia.pasos[0]["parametros"]["modo"] = "l2"
        self.assertEqual(len(original), 1)
        self.assertEqual(original.pasos[0]["parametros"]["modo"], "max")

    def test_descripcion(self):
        cadena = pr.Cadena()
        self.assertEqual(cadena.descripcion(), "(sin procesar)")
        cadena.agregar("suavizar_savgol", ventana=11, orden=2)
        cadena.agregar("normalizar", modo="max")
        texto = cadena.descripcion()
        self.assertIn("Savitzky-Golay", texto)
        self.assertIn("ventana=11", texto)
        self.assertIn("->", texto)
        self.assertEqual(len(cadena.etiquetas()), 2)

    def test_agregar_operacion_desconocida(self):
        with self.assertRaises(ValueError):
            pr.Cadena().agregar("no_existe")

    def test_procesar_un_espectro_real(self):
        """Con datos REALES del equipo (7101 puntos): la cadena no revienta."""
        from jenway67.reader import decodificar_archivo, leer_carpeta

        carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tarjeta")
        tarjeta = leer_carpeta(carpeta)
        if not tarjeta.metodos:
            self.skipTest("sin tarjeta de ejemplo")
        # 323BE947.JWB = espectro real de 190-900 nm a 0,1 nm
        _modo, r = decodificar_archivo(tarjeta, "323BE947.JWB")
        wl, y = pr.desde_puntos(r["puntos"])
        self.assertEqual(wl.size, 7101)
        cadena = pr.Cadena()
        cadena.agregar("despike")
        cadena.agregar("suavizar_savgol", ventana=11, orden=2)
        cadena.agregar("linea_snip", iteraciones=30)
        cadena.agregar("normalizar", modo="max")
        wl2, y2 = cadena.aplicar(wl, y)
        self.assertEqual(wl2.size, wl.size)
        self.assertTrue(np.all(np.isfinite(y2)))
        self.assertAlmostEqual(float(np.max(y2)), 1.0, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
