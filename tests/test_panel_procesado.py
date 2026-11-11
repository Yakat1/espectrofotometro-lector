# -*- coding: utf-8 -*-
"""Pruebas del panel de procesado (Fase 3) y de su integración en la ventana.

Se ejecuta en plataforma offscreen (sin ventanas visibles).
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

MAESTRO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAESTRO)

from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,  # noqa: E402
                               QLineEdit, QSpinBox)

_app = QApplication.instance() or QApplication(sys.argv[:1])

from jenway67 import procesado as pr                          # noqa: E402
from jenway67.reader import decodificar_archivo               # noqa: E402
from ui.panel_procesado import (PanelProcesado, crear_widget,  # noqa: E402
                                escribir_widget, leer_widget)
from ui.ventana import VentanaMaestro                          # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
TARJETA = os.path.join(RAIZ, "data", "tarjeta")


# ==========================================================================
# Controles generados a partir del registro
# ==========================================================================
class TestControles(unittest.TestCase):
    def test_entero_da_spinbox(self):
        parametro = pr.Parametro("ventana", "Ventana", "int", 9, 3, 199)
        widget = crear_widget(parametro)
        self.assertIsInstance(widget, QSpinBox)
        self.assertEqual(widget.value(), 9)
        self.assertEqual(widget.minimum(), 3)
        self.assertEqual(widget.maximum(), 199)
        self.assertEqual(leer_widget(widget, parametro), 9)

    def test_flotante_da_spinbox_doble(self):
        parametro = pr.Parametro("umbral", "Umbral", "float", 3.0, 0.5, 20.0)
        widget = crear_widget(parametro)
        self.assertIsInstance(widget, QDoubleSpinBox)
        self.assertAlmostEqual(widget.value(), 3.0)
        self.assertAlmostEqual(leer_widget(widget, parametro), 3.0)

    def test_lista_da_combo_con_el_defecto_elegido(self):
        parametro = pr.Parametro("modo", "Modo", "lista", "max", None, None,
                                 ("max", "l2", "area"))
        widget = crear_widget(parametro)
        self.assertIsInstance(widget, QComboBox)
        self.assertEqual(widget.currentText(), "max")
        self.assertEqual(leer_widget(widget, parametro), "max")
        widget.setCurrentText("l2")
        self.assertEqual(leer_widget(widget, parametro), "l2")

    def test_lista_con_defecto_que_no_esta_en_las_opciones(self):
        parametro = pr.Parametro("modo", "Modo", "lista", "inventado", None, None,
                                 ("a", "b"))
        widget = crear_widget(parametro)
        self.assertEqual(widget.currentIndex(), 0)

    def test_texto_da_lineedit(self):
        parametro = pr.Parametro("anclas", "Anclas", "texto", "400, 450")
        widget = crear_widget(parametro)
        self.assertIsInstance(widget, QLineEdit)
        self.assertEqual(leer_widget(widget, parametro), "400, 450")

    def test_opcional_vacio_es_none(self):
        parametro = pr.Parametro("wl_min", "Desde", "opcional_float", None)
        widget = crear_widget(parametro)
        self.assertIsNone(leer_widget(widget, parametro))

    def test_opcional_acepta_numero_y_coma_decimal(self):
        parametro = pr.Parametro("wl_min", "Desde", "opcional_float", None)
        widget = crear_widget(parametro)
        escribir_widget(widget, parametro, 420.0)
        self.assertEqual(leer_widget(widget, parametro), 420.0)
        widget.setText("430,5")
        self.assertEqual(leer_widget(widget, parametro), 430.5)

    def test_opcional_con_texto_basura_avisa(self):
        parametro = pr.Parametro("wl_min", "Desde", "opcional_float", None)
        widget = crear_widget(parametro)
        widget.setText("cuatrocientos")
        with self.assertRaises(ValueError):
            leer_widget(widget, parametro)


# ==========================================================================
# Panel
# ==========================================================================
class TestPanel(unittest.TestCase):
    def setUp(self):
        self.panel = PanelProcesado()
        self.senales, self.mensajes = [], []
        self.panel.cambio.connect(lambda: self.senales.append("cambio"))
        self.panel.mensaje.connect(self.mensajes.append)

    def _elegir(self, grupo, etiqueta):
        self.panel.combo_grupo.setCurrentText(grupo)
        indice = self.panel.combo_operacion.findText(etiqueta)
        self.assertGreaterEqual(indice, 0, "no aparece la operación %r" % etiqueta)
        self.panel.combo_operacion.setCurrentIndex(indice)

    def test_los_grupos_salen_del_registro(self):
        en_panel = [self.panel.combo_grupo.itemText(i)
                    for i in range(self.panel.combo_grupo.count())]
        self.assertEqual(en_panel, pr.grupos())

    def test_las_operaciones_salen_del_grupo_elegido(self):
        self.panel.combo_grupo.setCurrentText("Suavizado")
        en_panel = [self.panel.combo_operacion.itemText(i)
                    for i in range(self.panel.combo_operacion.count())]
        esperadas = [o.etiqueta for o in pr.operaciones_de("Suavizado")]
        self.assertEqual(en_panel, esperadas)

    def test_cada_operacion_del_registro_es_elegible_con_sus_controles(self):
        """Ninguna operación se queda sin controles: todas se pueden aplicar."""
        for grupo in pr.grupos():
            for operacion in pr.operaciones_de(grupo):
                with self.subTest(operacion=operacion.clave):
                    self._elegir(grupo, operacion.etiqueta)
                    self.assertEqual(self.panel.operacion_actual().clave, operacion.clave)
                    valores = self.panel.parametros_actuales()
                    self.assertEqual(set(valores), {p.nombre for p in operacion.parametros})
                    self.panel.cadena().limpiar()
                    self.panel._aplicar()
                    self.assertEqual(len(self.panel.cadena()), 1, "no se aplicó")
                    self.panel.cadena().limpiar()

    def test_aplicar_avisa_y_emite_cambio(self):
        self._elegir("Suavizado", "Suavizado Savitzky-Golay")
        self.panel._aplicar()
        self.assertEqual(len(self.panel.cadena()), 1)
        self.assertEqual(self.senales, ["cambio"])
        self.assertTrue(any("Savitzky" in m for m in self.mensajes))

    def test_la_lista_y_el_resumen_reflejan_la_cadena(self):
        self._elegir("Suavizado", "Suavizado Savitzky-Golay")
        self.panel._aplicar()
        self._elegir("Normalizacion", "Normalizar")
        self.panel._aplicar()
        self.assertEqual(self.panel.lista_pasos.count(), 2)
        self.assertIn("1.", self.panel.lista_pasos.item(0).text())
        self.assertIn("Savitzky-Golay", self.panel.resumen())
        self.assertEqual(self.panel.lista_pasos.count(), len(self.panel.cadena()))

    def test_deshacer_quita_el_ultimo(self):
        self._elegir("Suavizado", "Media movil")
        self.panel._aplicar()
        self.panel._deshacer()
        self.assertEqual(len(self.panel.cadena()), 0)
        self.assertIn("deshecho", " ".join(self.mensajes).lower())

    def test_deshacer_sin_nada_avisa(self):
        self.panel._deshacer()
        self.assertTrue(any("nada que deshacer" in m.lower() for m in self.mensajes))
        self.assertEqual(self.senales, [])

    def test_quitar_un_paso_concreto(self):
        self._elegir("Suavizado", "Media movil")
        self.panel._aplicar()
        self._elegir("Linea base", "Linea base SNIP")
        self.panel._aplicar()
        self.panel.lista_pasos.setCurrentRow(0)
        self.panel._quitar()
        self.assertEqual(len(self.panel.cadena()), 1)
        self.assertEqual(self.panel.cadena().pasos[0]["clave"], "linea_snip")

    def test_quitar_sin_seleccion_avisa(self):
        self._elegir("Suavizado", "Media movil")
        self.panel._aplicar()
        self.panel._quitar()
        self.assertTrue(any("elige un paso" in m.lower() for m in self.mensajes))
        self.assertEqual(len(self.panel.cadena()), 1)

    def test_limpiar_y_volver_a_limpiar(self):
        self._elegir("Suavizado", "Media movil")
        self.panel._aplicar()
        self.panel._limpiar()
        self.assertEqual(len(self.panel.cadena()), 0)
        self.assertEqual(self.panel.resumen(), "(sin procesar)")
        self.panel._limpiar()
        self.assertTrue(any("ya está vacía" in m for m in self.mensajes))

    def test_poner_cadena_ajena(self):
        ajena = pr.Cadena().agregar("normalizar", modo="l2")
        self.panel.poner_cadena(ajena)
        self.assertIs(self.panel.cadena(), ajena)
        self.assertEqual(self.panel.lista_pasos.count(), 1)
        self.panel.poner_cadena(None)
        self.assertEqual(self.panel.lista_pasos.count(), 0)

    def test_un_parametro_invalido_no_rompe_ni_añade_paso(self):
        self._elegir("Seleccion", "Recortar rango (nm)")
        self.panel._widgets["wl_min"].setText("cuatrocientos")
        self.panel._aplicar()
        self.assertEqual(len(self.panel.cadena()), 0)
        self.assertEqual(self.senales, [])
        self.assertTrue(any("no es un número" in m for m in self.mensajes))

    def test_operar_emite_la_operacion_elegida(self):
        recibido = []
        self.panel.operar.connect(recibido.append)
        self.panel.combo_entre.setCurrentText("cociente")
        self.panel.btn_operar.click()
        self.assertEqual(recibido, ["cociente"])

    def test_los_botones_de_cadena_empiezan_desactivados(self):
        self.assertFalse(self.panel.btn_deshacer.isEnabled())
        self.assertTrue(self.panel.btn_aplicar.isEnabled())


# ==========================================================================
# Integración con la ventana
# ==========================================================================
class TestIntegracionConLaVentana(unittest.TestCase):
    def setUp(self):
        self.w = VentanaMaestro(tema="dark")
        self.w.cargar_carpeta(TARJETA)

    def _indice_de_modo(self, modo, minimo_muestras=1):
        for i in range(len(self.w.items_de_metodos())):
            metodo = self.w.metodo_en_fila(i)
            if metodo and metodo.modo == modo and len(metodo.muestras) >= minimo_muestras:
                return i
        self.skipTest("la tarjeta no tiene método %s con %d muestra(s)"
                      % (modo, minimo_muestras))

    def _abrir_espectro(self):
        indice = self._indice_de_modo("spectrum")
        self.assertTrue(self.w.seleccionar_metodo(indice))

    def _asegurar_dos_filas(self):
        """Deja DOS filas seleccionadas (duplica la primera si la tarjeta solo
        trae una muestra de espectro, para poder ejercitar la operación)."""
        if not self.w._muestras_actuales:
            self.skipTest("sin muestras")
        if len(self.w._muestras_actuales) < 2:
            etiqueta, loc = self.w._muestras_actuales[0]
            self.w._muestras_actuales.append(("%s (copia)" % etiqueta, loc))
            self.w.lista_muestras.addItem("%s (copia)" % etiqueta)
        self.w.lista_muestras.clearSelection()
        for fila in range(2):
            self.w.lista_muestras.item(fila).setSelected(True)
        self.assertEqual(len(self.w._filas_seleccionadas()), 2)

    def _columna_de_absorbancia(self):
        modelo = self.w.modelo_datos
        cabecera = list(modelo.cabecera())
        for columna, titulo in enumerate(cabecera):
            if "abs" in str(titulo).lower():
                return columna
        self.fail("no encuentro la columna de absorbancia en %s" % cabecera)

    def test_el_panel_arranca_desactivado(self):
        # Sin tarjeta cargada no hay nada que procesar.  (Ojo: en setUp se carga
        # la tarjeta, que ya deja seleccionado el primer método.)
        ventana = VentanaMaestro(tema="dark")
        self.assertFalse(ventana.panel_proc.isEnabled())

    def test_seleccionar_un_espectro_activa_el_panel(self):
        self._abrir_espectro()
        self.assertTrue(self.w.panel_proc.isEnabled())

    def test_una_cinetica_activa_el_panel(self):
        indice = self._indice_de_modo("kinetics")
        self.w.seleccionar_metodo(indice)
        self.assertTrue(self.w.panel_proc.isEnabled())
        self.assertEqual(self.w.panel_proc._eje, "s")

    def test_el_panel_edita_la_misma_cadena_que_la_muestra(self):
        """Sin esto el panel no serviría de nada aunque parezca que funciona."""
        self._abrir_espectro()
        fila = self.w._filas_seleccionadas()[0]
        self.assertIs(self.w.panel_proc.cadena(), self.w._cadena_de(fila))

    def test_sin_cadena_el_espectro_no_se_toca(self):
        self._abrir_espectro()
        indice = self.w._filas_seleccionadas()[0]
        etiqueta, loc = self.w._muestras_actuales[indice]
        _modo, r = decodificar_archivo(self.w.tarjeta, loc, self.w.metodo_actual.modo)
        mismo, etiqueta_igual = self.w._aplicar_cadena(indice, "spectrum", r, etiqueta)
        self.assertIs(mismo, r)
        self.assertEqual(etiqueta_igual, etiqueta)

    def test_con_cadena_cambian_los_puntos_y_el_original_no_se_toca(self):
        self._abrir_espectro()
        indice = self.w._filas_seleccionadas()[0]
        etiqueta, loc = self.w._muestras_actuales[indice]
        _modo, r = decodificar_archivo(self.w.tarjeta, loc, self.w.metodo_actual.modo)
        maximo_original = max(p[2] for p in r["puntos"])
        self.w._cadena_de(indice).agregar("normalizar", modo="max")
        procesado, etiqueta_procesada = self.w._aplicar_cadena(indice, "spectrum", r, etiqueta)
        self.assertIn("procesado", etiqueta_procesada)
        self.assertEqual(procesado["n"], r["n"])
        self.assertAlmostEqual(max(p[2] for p in procesado["puntos"]), 1.0, places=6)
        # El resultado es un dict nuevo: el original sigue intacto.
        self.assertIsNot(procesado, r)
        self.assertAlmostEqual(max(p[2] for p in r["puntos"]), maximo_original, places=12)

    def test_una_cadena_se_aplica_a_una_cinetica(self):
        indice = self._indice_de_modo("kinetics")
        self.w.seleccionar_metodo(indice)
        fila = self.w._filas_seleccionadas()[0]
        etiqueta, loc = self.w._muestras_actuales[fila]
        _modo, r = decodificar_archivo(self.w.tarjeta, loc, self.w.metodo_actual.modo)
        self.w._cadena_de(fila).agregar("linea_offset", metodo="minimo")
        procesado, etiqueta_procesada = self.w._aplicar_cadena(fila, "kinetics", r, etiqueta)
        self.assertIn("procesado", etiqueta_procesada)
        self.assertIsNot(procesado, r)
        # Quitar el desplazamiento lleva el mínimo de la cinética a 0.
        minimo = min(s[2] for s in procesado["serie"])
        self.assertAlmostEqual(minimo, 0.0, places=6)

    def test_cambiar_la_cadena_redibuja_con_datos_procesados(self):
        """Prueba de fondo: tras cambiar la cadena, la tabla que se ve lleva los
        números YA procesados (no los crudos)."""
        self._abrir_espectro()
        columna = self._columna_de_absorbancia()
        modelo = self.w.modelo_datos
        maximo_antes = max(float(fila[columna]) for fila in modelo.filas())
        self.w._cadena_de(self.w._filas_seleccionadas()[0]).agregar("normalizar", modo="max")
        self.w._reprocesar()
        maximo_despues = max(float(fila[columna]) for fila in modelo.filas())
        self.assertAlmostEqual(maximo_despues, 1.0, places=6)
        self.assertNotAlmostEqual(maximo_antes, 1.0, places=3)

    def test_operar_las_dos_muestras_de_un_espectro(self):
        self._abrir_espectro()
        self._asegurar_dos_filas()
        self.w._operar_seleccionadas("resta")
        self.assertIn("A - B", self.w.statusBar().currentMessage())
        # A, B y la traza derivada: se dibujan 3 series.
        indice = self.w.tabs.indexOf(self.w.grupo_datos)
        self.assertIn("de 3", self.w.tabs.tabText(indice))

    def test_operar_exige_exactamente_dos(self):
        self._abrir_espectro()
        self.w.lista_muestras.clearSelection()
        self.w.lista_muestras.item(0).setSelected(True)
        self.w._operar_seleccionadas("resta")
        self.assertIn("EXACTAMENTE 2", self.w.statusBar().currentMessage())

    def test_operar_en_un_modo_sin_espectros_avisa(self):
        indice = self._indice_de_modo("kinetics")
        self.w.seleccionar_metodo(indice)
        self._asegurar_dos_filas()
        self.w._operar_seleccionadas("resta")
        self.assertIn("solo vale para espectros", self.w.statusBar().currentMessage())


class TestSacarLaVista(unittest.TestCase):
    """Copiar/exportar lo que se ve, con el procesado ya aplicado."""

    def setUp(self):
        self.w = VentanaMaestro(tema="dark")
        self.w.cargar_carpeta(TARJETA)

    def _abrir_espectro(self):
        for i in range(len(self.w.items_de_metodos())):
            metodo = self.w.metodo_en_fila(i)
            if metodo and metodo.modo == "spectrum":
                self.w.seleccionar_metodo(i)
                return
        self.skipTest("la tarjeta no tiene espectros")

    def _columna_de_absorbancia(self):
        for columna, titulo in enumerate(self.w.modelo_datos.cabecera()):
            if "abs" in str(titulo).lower():
                return columna
        self.fail("no encuentro la columna de absorbancia")

    def _menus(self):
        """Los menús de la barra, vía ``findChildren``.

        OJO: NO usar ``QAction.menu()``.  En PySide6 esa llamada crea un
        envoltorio NUEVO del mismo QMenu y, al descartarse, el objeto C++ se da
        por liberado: la siguiente llamada revienta con "Internal C++ object
        already deleted" y puede dejar el menú inservible de verdad.
        """
        from PySide6.QtWidgets import QMenu

        return self.w.menuBar().findChildren(QMenu)

    def test_hay_un_solo_menu_ver(self):
        titulos = [menu.title().replace("&", "") for menu in self._menus()]
        self.assertEqual(titulos.count("Ver"), 1, titulos)

    def test_el_interruptor_del_panel_esta_en_el_menu_ver(self):
        textos = [accion.text() for accion in self.w.menu_ver.actions()]
        self.assertTrue(any("Procesado" in t for t in textos), textos)

    def test_exportar_la_vista_lleva_los_numeros_procesados(self):
        import tempfile

        self._abrir_espectro()
        columna = self._columna_de_absorbancia()
        self.w._cadena_de(self.w._filas_seleccionadas()[0]).agregar("normalizar", modo="max")
        self.w._reprocesar()
        with tempfile.TemporaryDirectory() as carpeta:
            destino = os.path.join(carpeta, "vista.csv")
            escritas = self.w._escribir_vista_csv(destino)
            with open(destino, encoding="utf-8-sig") as manejador:
                lineas = manejador.read().splitlines()
        self.assertGreater(escritas, 100)
        self.assertEqual(escritas, len(lineas) - 1)
        self.assertIn("Abs", lineas[0])
        valores = []
        for linea in lineas[1:]:
            try:
                valores.append(float(linea.split(";")[columna]))
            except (ValueError, IndexError):
                continue
        self.assertTrue(valores)
        self.assertAlmostEqual(max(valores), 1.0, places=6)

    def test_copiar_la_tabla_al_portapapeles(self):
        self._abrir_espectro()
        self.w._copiar_tabla()
        lineas = QApplication.clipboard().text().splitlines()
        self.assertGreater(len(lineas), 100)
        self.assertIn("\t", lineas[0])
        self.assertIn("Copiadas", self.w.statusBar().currentMessage())

    def test_sin_datos_avisa_y_no_abre_dialogo(self):
        # Ventana sin tarjeta: sale ANTES de pedir el nombre del archivo.
        ventana = VentanaMaestro(tema="dark")
        ventana._exportar_vista_csv()
        self.assertIn("No hay nada que exportar", ventana.statusBar().currentMessage())
        ventana._copiar_tabla()
        self.assertIn("No hay nada que copiar", ventana.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main(verbosity=2)
