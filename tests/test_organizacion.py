# -*- coding: utf-8 -*-
"""Pruebas de la Fase 2 (organización y gestión de datos).

Cubre: modelo de tabla virtualizado (sin tope de filas y con orden numérico),
adaptador de reportes .TXT, árbol de métodos por modo con búsqueda y filtro por
usuario, arrastrar/soltar y apertura de archivos sueltos.

Se ejecuta en plataforma offscreen (sin ventanas visibles).
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtCore import QMimeData, QUrl, Qt               # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67.adaptador_txt import cargar_reporte            # noqa: E402
from jenway67.exportar import filas_para                     # noqa: E402
from jenway67.informe import _analisis_por_modo              # noqa: E402
from jenway67.reader import leer_carpeta                     # noqa: E402
from ui.modelo_tabla import ModeloTablaDatos, clave_orden    # noqa: E402
from ui.ventana import VentanaMaestro, _normaliza            # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
TARJETA = os.path.join(RAIZ, "data", "tarjeta")
JWB = os.path.join(RAIZ, "data", "jwb")
REPORTES = os.path.join(RAIZ, "data", "reportes")


# --------------------------------------------------------------------------
# modelo de tabla
# --------------------------------------------------------------------------

class TestModeloTabla(unittest.TestCase):
    def setUp(self):
        self.m = ModeloTablaDatos()

    def test_sin_tope_de_filas(self):
        self.m.set_datos(["A", "B"], [[i, i * 2] for i in range(40000)])
        self.assertEqual(self.m.rowCount(), 40000)
        self.assertEqual(self.m.columnCount(), 2)

    def test_cabecera_y_datos(self):
        self.m.set_datos(["Longitud", "Abs"], [[190.0, 0.5], [190.1, 0.6]])
        self.assertEqual(self.m.cabecera(), ["Longitud", "Abs"])
        self.assertEqual(self.m.headerData(1, Qt.Orientation.Horizontal), "Abs")
        idx = self.m.index(1, 1)
        self.assertEqual(self.m.data(idx), "0.6")

    def test_indice_invalido(self):
        self.m.set_datos(["A"], [["1"]])
        self.assertIsNone(self.m.data(self.m.index(99, 0)))
        self.assertIsNone(self.m.data(self.m.index(0, 9)))

    def test_orden_numerico_no_lexicografico(self):
        self.m.set_datos(["V"], [["10"], ["2"], ["1"], ["-3"]])
        self.m.sort(0, Qt.SortOrder.AscendingOrder)
        self.assertEqual([f[0] for f in self.m.filas()], ["-3", "1", "2", "10"])
        self.m.sort(0, Qt.SortOrder.DescendingOrder)
        self.assertEqual([f[0] for f in self.m.filas()], ["10", "2", "1", "-3"])

    def test_orden_deja_el_texto_al_final(self):
        self.m.set_datos(["V"], [["Saturado(>3.0)"], ["0.5"], ["-0.2"]])
        self.m.sort(0, Qt.SortOrder.AscendingOrder)
        self.assertEqual([f[0] for f in self.m.filas()], ["-0.2", "0.5", "Saturado(>3.0)"])

    def test_columna_no_ordenable_no_revienta(self):
        self.m.set_datos(["A"], [["1"]])
        self.m.sort(-1)                     # columna inválida: no hace nada
        self.assertEqual(self.m.rowCount(), 1)

    def test_alineacion_derecha_en_columnas_numericas(self):
        self.m.set_datos(["Nombre", "Abs"], [["a", "0.5"], ["b", "0.6"]])
        self.assertTrue(self.m.es_numerica(1))
        self.assertFalse(self.m.es_numerica(0))
        self.assertIsNotNone(self.m.data(self.m.index(0, 1), Qt.ItemDataRole.TextAlignmentRole))
        self.assertIsNone(self.m.data(self.m.index(0, 0), Qt.ItemDataRole.TextAlignmentRole))

    def test_clave_orden(self):
        self.assertEqual(clave_orden("10")[0], 0)
        self.assertEqual(clave_orden(" 1,5 ")[1], 1.5)
        self.assertEqual(clave_orden("abc")[0], 1)


class TestNormaliza(unittest.TestCase):
    def test_quita_tildes_y_mayusculas(self):
        self.assertEqual(_normaliza("Método por Defecto"), "metodo por defecto")
        self.assertEqual(_normaliza("CINÉTICA"), "cinetica")
        self.assertEqual(_normaliza(None), "")


# --------------------------------------------------------------------------
# adaptador de reportes .TXT
# --------------------------------------------------------------------------

class TestAdaptadorReporte(unittest.TestCase):
    def test_modo_de_cada_reporte(self):
        esperado = {"1_LEC.TXT": "photometrics", "2D.TXT": "kinetics",
                    "3A.TXT": "spectrum", "4A.TXT": "multi",
                    "5A.TXT": "quantitation"}
        for nombre, modo in esperado.items():
            obtenido = cargar_reporte(os.path.join(REPORTES, nombre))[0]
            self.assertEqual(obtenido, modo, f"{nombre} debería ser {modo}")

    def test_espectro_reconstruye_el_porcentaje_de_transmitancia(self):
        modo, res, _etq, _aviso = cargar_reporte(os.path.join(REPORTES, "3A.TXT"))
        self.assertEqual(modo, "spectrum")
        self.assertTrue(res[0]["puntos"])
        wl, t, a = res[0]["puntos"][0]
        self.assertAlmostEqual(t, 100.0 * 10.0 ** (-a), places=6)
        self.assertIsInstance(wl, float)

    def test_cinetica_conserva_los_tiempos(self):
        _modo, res, _etq, _aviso = cargar_reporte(os.path.join(REPORTES, "2D.TXT"))
        r = res[0]
        self.assertTrue(r["serie"])
        self.assertEqual(len(r["serie"][0]), 3)          # (índice, %T, Abs)
        self.assertEqual(len(r["tiempos"]), len(r["serie"]))

    def test_multi_incluye_las_cuatro_celdas_y_los_calculos(self):
        _modo, res, _etq, _aviso = cargar_reporte(os.path.join(REPORTES, "4A.TXT"))
        r = res[0]
        self.assertEqual(len(r["celdas"]), 4)
        self.assertTrue(all(c["etiqueta"] for c in r["celdas"]))

    def test_cuantificacion_tiene_estandares(self):
        modo, res, _etq, _aviso = cargar_reporte(os.path.join(REPORTES, "5A.TXT"))
        self.assertEqual(modo, "quantitation")
        self.assertTrue(res[0]["estandares"])
        self.assertGreater(len(res[0]["estandares"][0]), 1)

    def test_reporte_multi_modo_avisa(self):
        modo, res, _etq, aviso = cargar_reporte(os.path.join(REPORTES, "INTRODUZ.TXT"))
        self.assertEqual(modo, "photometrics")           # se muestra el primer modo
        self.assertTrue(res)
        self.assertIn("3 modos", aviso)

    def test_archivo_que_no_es_reporte(self):
        modo, res, etq, aviso = cargar_reporte(os.path.join(TARJETA, "SUMMARYS.JWX"))
        self.assertEqual(res, [])
        self.assertTrue(aviso)

    def test_forma_compatible_con_el_resto_de_la_app(self):
        """Lo adaptado debe poder pasar por las funciones que consumen .JWB."""
        for nombre in ("3A.TXT", "4A.TXT", "5A.TXT", "2D.TXT"):
            modo, res, _etq, _aviso = cargar_reporte(os.path.join(REPORTES, nombre))
            cab, filas = filas_para(modo, res[0])
            self.assertTrue(cab and filas, f"{nombre}: filas_para no devolvió datos")
            analisis = _analisis_por_modo(modo, [(None, modo, r) for r in res])
            self.assertIn("n_muestras", analisis, f"{nombre}: sin análisis agregado")


# --------------------------------------------------------------------------
# árbol de métodos, búsqueda y filtro por usuario
# --------------------------------------------------------------------------

class TestArbolMetodos(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(carpeta=TARJETA, tema="dark")

    def test_agrupa_por_modo_con_conteo(self):
        arbol = self.w.arbol_metodos
        titulos = [arbol.topLevelItem(i).text(0) for i in range(arbol.topLevelItemCount())]
        self.assertEqual(titulos, ["Espectro (2)", "Cinética (4)", "Multi-longitud (2)",
                                  "Cuantificación (5)", "Fotometría (5)"])
        total = sum(arbol.topLevelItem(i).childCount() for i in range(arbol.topLevelItemCount()))
        self.assertEqual(total, len(self.w.tarjeta.metodos))

    def test_carpetas_agrupan_pero_no_se_seleccionan(self):
        carpeta = self.w.arbol_metodos.topLevelItem(0)
        self.assertFalse(bool(carpeta.flags() & Qt.ItemFlag.ItemIsSelectable))
        self.assertTrue(bool(carpeta.child(0).flags() & Qt.ItemFlag.ItemIsSelectable))
        self.assertTrue(carpeta.isExpanded())

    def test_busqueda_filtra_por_nombre(self):
        self.w.busqueda.setText("test1")
        items = self.w.items_de_metodos()
        self.assertTrue(items)
        for it in items:
            self.assertIn("Test1", it.data(0, Qt.ItemDataRole.UserRole).nombre)

    def test_busqueda_ignora_tildes_y_mayusculas(self):
        self.w.busqueda.setText("CINETICA")            # sin tilde y en mayúsculas
        items = self.w.items_de_metodos()
        self.assertTrue(items)
        for it in items:
            self.assertEqual(it.data(0, Qt.ItemDataRole.UserRole).modo, "kinetics")

    def test_busqueda_por_usuario_y_por_fecha(self):
        self.w.busqueda.setText("alumnos")
        self.assertEqual(len(self.w.items_de_metodos()), 16)
        self.w.busqueda.setText("15/9/26")
        self.assertTrue(self.w.items_de_metodos())

    def test_sin_coincidencias_limpia_la_vista(self):
        self.w.busqueda.setText("zzz-no-existe")
        self.assertEqual(self.w.items_de_metodos(), [])
        self.assertIsNone(self.w.metodo_actual)
        self.assertEqual(self.w.panel._resultados, [])
        self.assertEqual(self.w.modelo_datos.rowCount(), 0)

    def test_filtro_por_usuario(self):
        conteos = {}
        for m in self.w.tarjeta.metodos:
            conteos[m.usuario] = conteos.get(m.usuario, 0) + 1
        self.assertIn("Alumnos", conteos)
        self.assertIn("Supervisor", conteos)
        for usuario, n in conteos.items():
            idx = next(i for i in range(self.w.combo_usuario.count())
                       if self.w.combo_usuario.itemData(i) == usuario)
            self.w.combo_usuario.setCurrentIndex(idx)
            items = self.w.items_de_metodos()
            self.assertEqual(len(items), n, f"usuario {usuario}")
            self.assertEqual({it.data(0, Qt.ItemDataRole.UserRole).usuario for it in items},
                             {usuario})

    def test_usuario_del_jwu_sin_metodos(self):
        idx = next(i for i in range(self.w.combo_usuario.count())
                   if self.w.combo_usuario.itemData(i) == "Generic")
        self.w.combo_usuario.setCurrentIndex(idx)
        self.assertEqual(self.w.items_de_metodos(), [])

    def test_busqueda_y_usuario_se_combinan(self):
        idx = next(i for i in range(self.w.combo_usuario.count())
                   if self.w.combo_usuario.itemData(i) == "Supervisor")
        self.w.combo_usuario.setCurrentIndex(idx)
        total_usuario = len(self.w.items_de_metodos())
        self.assertGreater(total_usuario, 0)
        self.w.busqueda.setText("espectro")            # por modo
        items = self.w.items_de_metodos()
        self.assertLessEqual(len(items), total_usuario)
        for it in items:
            m = it.data(0, Qt.ItemDataRole.UserRole)
            self.assertEqual(m.usuario, "Supervisor")
            self.assertEqual(m.modo, "spectrum")
        # un texto que no case con ese usuario deja la vista vacía
        self.w.busqueda.setText("test1")
        for it in self.w.items_de_metodos():
            self.assertEqual(it.data(0, Qt.ItemDataRole.UserRole).usuario, "Supervisor")

    def test_seleccionar_metodo_navega(self):
        self.assertTrue(self.w.seleccionar_metodo(0))
        self.assertIsNotNone(self.w.metodo_actual)
        self.assertFalse(self.w.seleccionar_metodo(999))


# --------------------------------------------------------------------------
# tabla virtualizada en la ventana + archivos sueltos y arrastrar/soltar
# --------------------------------------------------------------------------

class TestVentanaFase2(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(carpeta=TARJETA, tema="dark")

    def test_tabla_sin_tope_de_1500_filas(self):
        largos = []
        for i in range(len(self.w.items_de_metodos())):
            m = self.w.metodo_en_fila(i)
            if m.modo == "spectrum":
                self.w.seleccionar_metodo(i)
                largos.append(self.w.modelo_datos.rowCount())
        self.assertTrue(largos, "debe haber métodos de espectro")
        self.assertEqual(max(largos), 7101)          # 190-900 nm -> 7101 puntos
        self.assertGreater(max(largos), 1500)        # ya no hay tope de 1500 filas

    def test_abrir_jwb_suelto_detecta_el_modo(self):
        self.w.abrir_jwb(os.path.join(JWB, "323BE947_spectrum.JWB"))
        self.assertTrue(self.w.panel._resultados)
        self.assertEqual(len(self.w.panel._series), 1)
        self.assertIsNone(self.w.metodo_actual)        # es un documento suelto
        self.assertIn("modo detectado: espectro",
                      _normaliza(self.w.statusBar().currentMessage()))
        self.assertEqual(self.w.modelo_datos.rowCount(), 7101)

    def test_abrir_jwb_multi_suelto(self):
        self.w.abrir_jwb(os.path.join(JWB, "323BEA26_multi.JWB"))
        self.assertIn("multi", _normaliza(self.w.statusBar().currentMessage()))

    def test_abrir_reporte_txt(self):
        self.w.abrir_reporte(os.path.join(REPORTES, "3A.TXT"))
        self.assertTrue(self.w.modelo_datos.rowCount() > 0)
        self.assertTrue(self.w.panel._resultados)
        self.assertEqual(self.w.tabla_analisis.item(0, 0).text(), "n_muestras")

    def test_abrir_reporte_multi_modo_no_revienta(self):
        self.w.abrir_reporte(os.path.join(REPORTES, "INTRODUZ.TXT"))
        self.assertTrue(self.w.modelo_datos.rowCount() > 0)
        self.assertIn("3 modos", self.w.statusBar().currentMessage())

    def test_abrir_reporte_sin_datos(self):
        antes = self.w.modelo_datos.rowCount()
        self.w.abrir_reporte(os.path.join(TARJETA, "SUMMARYS.JWX"))
        # no destruye la vista actual y avisa por la barra de estado (sin modal)
        self.assertEqual(self.w.modelo_datos.rowCount(), antes)
        self.assertIn("SUMMARYS.JWX", self.w.statusBar().currentMessage())

    def test_soltar_una_carpeta_carga_la_tarjeta(self):
        self.w._abrir_rutas([TARJETA])
        self.assertIsNotNone(self.w.tarjeta)
        self.assertEqual(len(self.w.items_de_metodos()), len(self.w.tarjeta.metodos))

    def test_soltar_un_archivo_lo_abre(self):
        self.w._abrir_rutas([os.path.join(JWB, "323BEA26_multi.JWB")])
        self.assertTrue(self.w.panel._resultados)
        self.assertTrue(self.w.modelo_datos.rowCount() > 0)

    def test_soltar_indice_carga_su_carpeta(self):
        self.w._abrir_rutas([os.path.join(TARJETA, "SUMMARYS.JWX")])
        self.assertTrue(self.w.items_de_metodos())

    def test_soltar_extension_no_soportada(self):
        raro = os.path.join(RAIZ, "data", "jwb", "__init__.py")
        self.w._abrir_rutas([raro])
        self.assertIn("no soportada", self.w.statusBar().currentMessage().lower())

    def test_acepta_arrastre(self):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(TARJETA)])
        self.assertTrue(self.w._acepta_arrastre(mime))
        self.assertFalse(self.w._acepta_arrastre(QMimeData()))
        self.assertFalse(self.w._acepta_arrastre(None))

    def test_soltar_varios_archivos_abre_el_primero(self):
        self.w._abrir_rutas([os.path.join(JWB, "323BEA26_multi.JWB"),
                             os.path.join(JWB, "323BE947_spectrum.JWB")])
        self.assertEqual(len(self.w.panel._resultados), 1)
        self.assertIn("sólo se abre el primero", self.w.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main(verbosity=2)