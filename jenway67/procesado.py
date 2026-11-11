# -*- coding: utf-8 -*-
"""Procesado espectral del Programa Maestro Mimetico — Jenway 6705.

Opera sobre espectros ``(wl, absorbancia)`` y ofrece:

* **Suavizado**: Savitzky-Golay, media movil, mediana movil y "despike".
* **Linea base**: SNIP (el algoritmo clasico de recorte iterativo de picos),
  offset, recta por dos longitudes de onda y polinomio por puntos de ancla.
* **Normalizacion**: maximo, min-max, area, norma L2, valor en una lambda, SNV.
* **Derivadas**: 1.a y 2.a con Savitzky-Golay (mucho mejor que ``np.gradient``
  en espectros con ruido).
* **Seleccion**: recorte de rango.
* **Operaciones entre espectros**: resta, suma, media, cociente y producto,
  interpolando a una rejilla comun.

PRINCIPIOS
----------
1. **Sin dependencias nuevas**: los filtros estan escritos en numpy.  scipy NO se
   importa aqui (pesa mucho al empaquetar); en las pruebas se usa *solo* como
   oraculo de referencia para comprobar que Savitzky-Golay coincide con
   ``scipy.signal.savgol_filter``.
2. **No destructivo**: ninguna funcion modifica la entrada.  El original y lo
   procesado conviven, y :class:`Cadena` permite deshacer.
3. **Registro de operaciones**: cada operacion declara sus parametros
   (:class:`Parametro`), de modo que la interfaz puede construir sus controles
   sola y no hay dos listas de operaciones que se puedan desincronizar.

Coordenadas: las mismas que el resto del proyecto, ``E = absorbancia`` y
``%T = 100 * 10**-E``.  Al procesar se recalcula ``%T`` para que la identidad
``A = -log10(T/100)`` se mantenga.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:  # import absoluto (uso normal del paquete)
    from jenway67.analisis import espectro_series as _espectro_series
except ImportError:  # pragma: no cover - import relativo (paquete congelado)
    from .analisis import espectro_series as _espectro_series

# numpy 2.0 renombro trapz -> trapezoid.
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)

#: Modos de relleno de borde admitidos -> modo de ``np.pad``.
MODOS_BORDE = {
    "reflect": "reflect",      # espejo sin repetir el borde (por defecto)
    "symmetric": "symmetric",  # espejo repitiendo el borde
    "nearest": "edge",         # repite el ultimo valor
    "edge": "edge",
    "wrap": "wrap",            # circular
    "constante": "constant",   # rellena con ceros
}


# ==========================================================================
# Utilidades internas
# ==========================================================================
def _vector(y) -> np.ndarray:
    return np.asarray(y, dtype=float)


def _validar(ventana, orden=None, derivada=0) -> int:
    """Comprueba ventana/orden y devuelve la ventana como entero impar."""
    try:
        ventana = int(ventana)
    except (TypeError, ValueError):
        raise ValueError("La ventana debe ser un numero entero.")
    if ventana % 2 == 0:
        raise ValueError("La ventana debe ser IMPAR (p. ej. 5, 7, 9, 11).")
    if ventana < 3:
        raise ValueError("La ventana debe ser al menos 3.")
    if orden is not None:
        orden = int(orden)
        if orden < 0:
            raise ValueError("El orden del polinomio no puede ser negativo.")
        if ventana <= orden:
            raise ValueError(
                "La ventana (%d) debe ser mayor que el orden del polinomio (%d)."
                % (ventana, orden)
            )
        if derivada > orden:
            raise ValueError(
                "El orden del polinomio (%d) debe ser >= el orden de la derivada (%d)."
                % (orden, derivada)
            )
    return ventana


def _ventanas(y: np.ndarray, ventana: int, modo: str) -> np.ndarray:
    """Matriz (n, ventana) con la ventana centrada en cada punto."""
    if modo not in MODOS_BORDE:
        raise ValueError(
            "Modo de borde '%s' no valido. Opciones: %s"
            % (modo, ", ".join(sorted(MODOS_BORDE)))
        )
    n = y.size
    mitad = ventana // 2
    if mitad >= n:
        raise ValueError(
            "La ventana (%d) es demasiado grande para %d puntos." % (ventana, n)
        )
    relleno = np.pad(y, mitad, mode=MODOS_BORDE[modo])
    return np.lib.stride_tricks.sliding_window_view(relleno, ventana)


def _espaciado(wl) -> float:
    """Paso medio entre longitudes de onda (1.0 si no se puede calcular)."""
    if wl is None:
        return 1.0
    wl = np.asarray(wl, dtype=float)
    if wl.size < 2:
        return 1.0
    d = np.diff(wl)
    d = d[np.isfinite(d) & (d != 0)]
    if d.size == 0:
        return 1.0
    return float(np.mean(np.abs(d)))


# ==========================================================================
# Suavizado
# ==========================================================================
def coef_savgol(ventana: int = 9, orden: int = 2, derivada: int = 0,
                dx: float = 1.0) -> np.ndarray:
    """Coeficientes de Savitzky-Golay (fila de la pseudoinversa de Vandermonde).

    Para ``ventana=5, orden=2`` devuelve ``(-3, 12, 17, 12, -3) / 35``.
    """
    ventana = _validar(ventana, orden, derivada)
    mitad = ventana // 2
    x = np.arange(-mitad, mitad + 1, dtype=float)
    vandermonde = np.vander(x, int(orden) + 1, increasing=True)
    pseudoinversa = np.linalg.pinv(vandermonde)
    # La fila 'derivada' da los coeficientes; hay que multiplicar por d! y
    # dividir por dx**d para que la derivada sea respecto a las unidades de x.
    coef = pseudoinversa[int(derivada)] * float(math.factorial(int(derivada)))
    return coef / (float(dx) ** int(derivada))


def savgol(y, ventana: int = 9, orden: int = 2, derivada: int = 0,
           modo: str = "reflect", dx: float = 1.0) -> np.ndarray:
    """Filtro Savitzky-Golay (o su derivada d-esima)."""
    datos = _vector(y)
    ventana = _validar(ventana, orden, derivada)
    if datos.size < 3:
        return datos.copy()
    coef = coef_savgol(ventana, orden, derivada, dx)
    return _ventanas(datos, ventana, modo) @ coef


def media_movil(y, ventana: int = 5, modo: str = "reflect") -> np.ndarray:
    """Media movil centrada."""
    datos = _vector(y)
    ventana = _validar(ventana)
    if datos.size < 3:
        return datos.copy()
    return _ventanas(datos, ventana, modo).mean(axis=1)


def mediana_movil(y, ventana: int = 5, modo: str = "reflect") -> np.ndarray:
    """Mediana movil centrada (robusta frente a picos espurios)."""
    datos = _vector(y)
    ventana = _validar(ventana)
    if datos.size < 3:
        return datos.copy()
    return np.median(_ventanas(datos, ventana, modo), axis=1)


def despike(y, ventana: int = 5, umbral: float = 3.0) -> np.ndarray:
    """Elimina picos aislados (puntos que se disparan) sustituyendolos por la
    mediana movil local.

    El criterio es robusto: la escala de ruido se estima con la desviacion
    absoluta mediana (MAD) de las diferencias consecutivas, no con la desviacion
    tipica, para que un unico pico gigante no infle el umbral y se salve a si
    mismo.  En una senal sin ruido la escala robusta sale 0 y no habria criterio;
    en ese caso se marca el punto (o puntos) que mas se apartan.
    """
    datos = _vector(y)
    ventana = _validar(ventana)
    if datos.size < 3:
        return datos.copy()
    mediana = mediana_movil(datos, ventana, modo="nearest")
    desviaciones = np.abs(datos - mediana)
    diferencias = np.diff(datos)
    if diferencias.size == 0:
        return datos.copy()
    escala = 1.4826 * float(np.median(np.abs(diferencias - np.median(diferencias))))
    estricto = False
    if not np.isfinite(escala) or escala <= 0:
        maximo = float(np.max(desviaciones)) if desviaciones.size else 0.0
        if maximo <= 0:
            return datos.copy()
        # Senal sin ruido apreciable: solo se marcan los puntos mas desviados.
        escala = maximo / float(umbral)
        estricto = True
    limite = float(umbral) * escala
    marca = desviaciones >= limite if estricto else desviaciones > limite
    # Un pico espurio es un punto AISLADO.  Si el vecino tambien esta marcado no
    # es un pico: es la curvatura de la propia senal (medido: en un espectro
    # suave sin ruido los unicos puntos que superan el umbral salen en pares
    # adyacentes, y todos son curvatura legitima).
    con_vecino = np.zeros(marca.size, dtype=bool)
    if marca.size > 1:
        con_vecino[1:] |= marca[:-1]
        con_vecino[:-1] |= marca[1:]
    aislado = marca & ~con_vecino
    return np.where(aislado, mediana, datos)


# ==========================================================================
# Linea base
# ==========================================================================
def restar_offset(y, metodo: str = "minimo", valor: float = 0.0) -> np.ndarray:
    """Resta un desplazamiento constante.

    ``metodo``: ``minimo``, ``media``, ``mediana`` o ``valor`` (usa ``valor``).
    """
    datos = _vector(y)
    if datos.size == 0:
        return datos.copy()
    metodo = (metodo or "minimo").lower()
    finitos = datos[np.isfinite(datos)]
    if finitos.size == 0:
        return datos.copy()
    if metodo == "minimo":
        referencia = float(np.min(finitos))
    elif metodo == "media":
        referencia = float(np.mean(finitos))
    elif metodo == "mediana":
        referencia = float(np.median(finitos))
    elif metodo == "valor":
        referencia = float(valor)
    else:
        raise ValueError(
            "Metodo de offset '%s' no valido (minimo, media, mediana, valor)." % metodo
        )
    return datos - referencia


def recta_por_dos_puntos(wl, y, wl_a: float, wl_b: float) -> np.ndarray:
    """Recta (evaluada en todo ``wl``) que pasa por los puntos wl_a y wl_b."""
    datos, longitudes = _vector(y), np.asarray(wl, dtype=float)
    if longitudes.size != datos.size:
        raise ValueError("wl e y deben tener la misma longitud.")
    if float(wl_a) == float(wl_b):
        raise ValueError("Las dos longitudes de onda de la recta deben ser distintas.")
    ya = float(np.interp(wl_a, longitudes, datos))
    yb = float(np.interp(wl_b, longitudes, datos))
    pendiente = (yb - ya) / (float(wl_b) - float(wl_a))
    return ya + pendiente * (longitudes - float(wl_a))


def corregir_lineal(wl, y, wl_a: float, wl_b: float) -> np.ndarray:
    """Resta la recta que une los puntos (wl_a, A_a) y (wl_b, A_b)."""
    return _vector(y) - recta_por_dos_puntos(wl, y, wl_a, wl_b)


def polinomio_por_anclas(wl, y, anclas: Sequence[float],
                         orden: int = 2) -> np.ndarray:
    """Polinomio (evaluado en todo ``wl``) ajustado a los puntos de ancla."""
    datos, longitudes = _vector(y), np.asarray(wl, dtype=float)
    anclas = [float(a) for a in anclas]
    if len(anclas) < 2:
        raise ValueError("Hacen falta al menos 2 longitudes de onda de ancla.")
    orden = int(orden)
    if orden < 1:
        raise ValueError("El orden del polinomio de linea base debe ser >= 1.")
    if len(anclas) < orden + 1:
        raise ValueError(
            "Un polinomio de orden %d necesita al menos %d anclas (hay %d)."
            % (orden, orden + 1, len(anclas))
        )
    valores = [float(np.interp(a, longitudes, datos)) for a in anclas]
    coef = np.polyfit(np.asarray(anclas, dtype=float), np.asarray(valores),
                      orden)
    return np.polyval(coef, longitudes)


def corregir_polinomica(wl, y, anclas: Sequence[float],
                        orden: int = 2) -> np.ndarray:
    """Resta la linea base polinomica definida por los puntos de ancla."""
    return _vector(y) - polinomio_por_anclas(wl, y, anclas, orden)


def snip(y, iteraciones: int = 40) -> np.ndarray:
    """Linea base por SNIP (recorte iterativo de picos, Ryan et al. 1988).

    Devuelve **la linea base estimada** (no la correccion).  Como SNIP exige
    valores positivos, el espectro se desplaza si tiene absorbancias negativas
    y el desplazamiento se deshace al final.
    """
    datos = _vector(y)
    iteraciones = int(iteraciones)
    if datos.size < 3 or iteraciones < 1:
        return datos.copy()
    desplazamiento = min(0.0, float(np.min(datos)))
    z = datos - desplazamiento
    # Transformada log-log que hace lineal la contribucion de los picos.
    z = np.log(np.log(np.sqrt(z + 1.0) + 1.0) + 1.0)
    n = z.size
    for paso in range(1, min(iteraciones, n // 2) + 1):
        if n - 2 * paso <= 0:
            break
        vecinos = 0.5 * (z[: n - 2 * paso] + z[2 * paso:])
        z[paso: n - paso] = np.minimum(z[paso: n - paso], vecinos)
    # Transformada inversa.
    base = (np.exp(np.exp(z) - 1.0) - 1.0) ** 2 - 1.0
    return base + desplazamiento


def corregir_snip(wl, y, iteraciones: int = 40) -> np.ndarray:
    """Resta la linea base SNIP.  ``wl`` se acepta por uniformidad de la API."""
    return _vector(y) - snip(y, iteraciones)


# ==========================================================================
# Normalizacion
# ==========================================================================
MODOS_NORMALIZACION = ("max", "minmax", "area", "l2", "en_wl", "snv", "ninguna")


def normalizar(y, modo: str = "max", wl=None, wl_ref: Optional[float] = None) -> np.ndarray:
    """Normaliza el espectro segun ``modo``.

    ``max`` (maximo -> 1), ``minmax`` (-> [0,1]), ``area`` (integral -> 1),
    ``l2`` (norma euclidea -> 1), ``en_wl`` (valor en ``wl_ref`` -> 1),
    ``snv`` ((y-media)/desviacion), ``ninguna`` (copia sin tocar).
    """
    datos = _vector(y)
    modo = (modo or "max").lower()
    if modo not in MODOS_NORMALIZACION:
        raise ValueError(
            "Modo de normalizacion '%s' no valido. Opciones: %s"
            % (modo, ", ".join(MODOS_NORMALIZACION))
        )
    if modo in ("ninguna",) or datos.size == 0:
        return datos.copy()
    if modo == "max":
        divisor = float(np.max(datos))
    elif modo == "minmax":
        minimo, maximo = float(np.min(datos)), float(np.max(datos))
        rango = maximo - minimo
        # Con un espectro plano devolvemos ceros (no se puede estirar).
        if not np.isfinite(rango) or rango == 0:
            return np.zeros_like(datos)
        return (datos - minimo) / rango
    elif modo == "area":
        if wl is None:
            raise ValueError("La normalizacion por area necesita las longitudes de onda.")
        divisor = float(_trapz(datos, np.asarray(wl, dtype=float)))
    elif modo == "l2":
        divisor = float(np.linalg.norm(datos))
    elif modo == "en_wl":
        if wl is None or wl_ref is None:
            raise ValueError("La normalizacion en_wl necesita wl y wl_ref.")
        divisor = float(np.interp(wl_ref, np.asarray(wl, dtype=float), datos))
    else:  # snv
        desviacion = float(np.std(datos))
        if not np.isfinite(desviacion) or desviacion == 0:
            return np.zeros_like(datos)
        return (datos - float(np.mean(datos))) / desviacion
    if not np.isfinite(divisor) or divisor == 0:
        # Espectro todo a cero o saturado: no hay nada que normalizar.
        return datos.copy()
    return datos / divisor


# ==========================================================================
# Seleccion e interpolacion
# ==========================================================================
def recortar(wl, y, wl_min: Optional[float] = None,
             wl_max: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Recorta al rango [wl_min, wl_max] (inclusive)."""
    datos, longitudes = _vector(y), np.asarray(wl, dtype=float)
    mascara = np.ones(longitudes.size, dtype=bool)
    if wl_min is not None:
        mascara &= longitudes >= float(wl_min)
    if wl_max is not None:
        mascara &= longitudes <= float(wl_max)
    return longitudes[mascara], datos[mascara]


def interpolar(wl, y, wl_destino, fuera: str = "nan") -> np.ndarray:
    """Interpola ``y`` sobre ``wl_destino``.

    ``fuera``: ``nan`` deja NaN donde no hay datos; ``borde`` usa el valor
    del extremo mas cercano.
    """
    datos, longitudes = _vector(y), np.asarray(wl, dtype=float)
    destino = np.asarray(wl_destino, dtype=float)
    if longitudes.size < 2 or destino.size == 0:
        return np.full(destino.size, np.nan)
    valores = np.interp(destino, longitudes, datos)
    if fuera == "borde":
        return valores
    if fuera != "nan":
        raise ValueError("Parametro fuera debe ser 'nan' o 'borde'.")
    fuera_de_rango = (destino < longitudes.min()) | (destino > longitudes.max())
    valores = valores.astype(float, copy=True)
    valores[fuera_de_rango] = np.nan
    return valores


def rejilla_comun(lista_wl: Sequence, usar: str = "interseccion") -> np.ndarray:
    """Rejilla de longitudes de onda comun a varias series.

    ``interseccion`` (por defecto) usa el rango que TODAS cubren; ``union``
    usa el rango total.  En ambos casos se toma como paso el mas fino de las
    series de entrada.
    """
    listas = [np.asarray(w, dtype=float) for w in lista_wl if np.asarray(w).size]
    if not listas:
        return np.array([])
    if usar == "interseccion":
        minimo = max(float(w.min()) for w in listas)
        maximo = min(float(w.max()) for w in listas)
    elif usar == "union":
        minimo = min(float(w.min()) for w in listas)
        maximo = max(float(w.max()) for w in listas)
    else:
        raise ValueError("usar debe ser 'interseccion' o 'union'.")
    if maximo <= minimo:
        return np.array([])
    pasos = [_espaciado(w) for w in listas]
    paso = min(p for p in pasos if p > 0) if any(p > 0 for p in pasos) else 1.0
    cantidad = int(round((maximo - minimo) / paso)) + 1
    if cantidad < 2:
        return np.array([])
    return np.linspace(minimo, minimo + paso * (cantidad - 1), cantidad)


# ==========================================================================
# Operaciones entre espectros
# ==========================================================================
OPERACIONES_ENTRE = ("resta", "suma", "media", "cociente", "producto")


def operar(wl_a, y_a, wl_b, y_b, tipo: str = "resta",
           fuera: str = "nan") -> Tuple[np.ndarray, np.ndarray]:
    """Opera dos espectros sobre una rejilla comun (interseccion).

    ``tipo``: ``resta`` (A-B), ``suma``, ``media``, ``cociente`` (A/B),
    ``producto``.  Interpola el segundo espectro sobre los puntos del primero
    dentro del rango comun, asi que las dos trazas pueden venir de metodos con
    pasos distintos (p. ej. 400-500 nm a 1 nm y 190-900 nm a 0,1 nm).
    """
    tipo = (tipo or "resta").lower()
    if tipo not in OPERACIONES_ENTRE:
        raise ValueError(
            "Operacion '%s' no valida. Opciones: %s" % (tipo, ", ".join(OPERACIONES_ENTRE))
        )
    longitudes_a, datos_a = _vector(wl_a), _vector(y_a)
    longitudes_b, datos_b = _vector(wl_b), _vector(y_b)
    minimo = max(float(longitudes_a.min()), float(longitudes_b.min()))
    maximo = min(float(longitudes_a.max()), float(longitudes_b.max()))
    if maximo <= minimo:
        raise ValueError(
            "Los dos espectros no se solapan en longitud de onda: no hay rejilla comun."
        )
    rejilla = longitudes_a[(longitudes_a >= minimo) & (longitudes_a <= maximo)]
    if rejilla.size < 2:
        rejilla = longitudes_b[(longitudes_b >= minimo) & (longitudes_b <= maximo)]
    if rejilla.size < 2:
        raise ValueError("El solape es demasiado estrecho para operar.")
    primero = interpolar(longitudes_a, datos_a, rejilla, fuera)
    segundo = interpolar(longitudes_b, datos_b, rejilla, fuera)
    if tipo == "resta":
        resultado = primero - segundo
    elif tipo == "suma":
        resultado = primero + segundo
    elif tipo == "media":
        resultado = 0.5 * (primero + segundo)
    elif tipo == "producto":
        resultado = primero * segundo
    else:  # cociente
        with np.errstate(divide="ignore", invalid="ignore"):
            resultado = np.where(segundo != 0, primero / np.where(segundo == 0, 1.0, segundo),
                                 np.nan)
    return rejilla, resultado


# ==========================================================================
# Adaptadores al formato del proyecto: puntos = (wl, %T, Abs)
# ==========================================================================
def desde_puntos(puntos: Sequence[Tuple]) -> Tuple[np.ndarray, np.ndarray]:
    """(wl, Abs) finitos de una lista de puntos del proyecto."""
    return _espectro_series(puntos)


def a_puntos(wl, y) -> List[Tuple[float, float, float]]:
    """Convierte (wl, Abs) a puntos del proyecto, recalculando %T.

    Se mantiene la identidad del instrumento ``%T = 100 * 10**-A``; donde %T
    desborda (absorbancia muy alta) se escribe 0.
    """
    longitudes, datos = _vector(wl), _vector(y)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        transmitancia = 100.0 * np.power(10.0, -datos)
    transmitancia = np.where(np.isfinite(transmitancia), transmitancia, 0.0)
    return [
        (float(longitudes[i]), float(transmitancia[i]), float(datos[i]))
        for i in range(min(longitudes.size, datos.size))
    ]


# ==========================================================================
# Registro de operaciones (la GUI se construye a partir de aqui)
# ==========================================================================
@dataclass(frozen=True)
class Parametro:
    """Descripcion de un parametro de operacion (para construir controles)."""

    nombre: str
    etiqueta: str
    tipo: str = "float"          # int | float | opcional_float | lista | texto
    defecto: object = 0.0
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    opciones: tuple = ()
    ayuda: str = ""


@dataclass(frozen=True)
class Operacion:
    """Una operacion de procesado con sus parametros declarados."""

    clave: str
    etiqueta: str
    grupo: str
    fn: object
    parametros: tuple = ()
    ayuda: str = ""

    def valores_por_defecto(self) -> Dict:
        return {p.nombre: p.defecto for p in self.parametros}


# --- funciones de las operaciones (firma comun: (wl, y, **params)) ---------
def _op_savgol(wl, y, ventana=9, orden=2, modo="reflect"):
    return wl, savgol(y, ventana=ventana, orden=orden, modo=modo)


def _op_media(wl, y, ventana=5, modo="reflect"):
    return wl, media_movil(y, ventana=ventana, modo=modo)


def _op_mediana(wl, y, ventana=5, modo="reflect"):
    return wl, mediana_movil(y, ventana=ventana, modo=modo)


def _op_despike(wl, y, ventana=5, umbral=3.0):
    return wl, despike(y, ventana=ventana, umbral=umbral)


def _op_snip(wl, y, iteraciones=40):
    return wl, corregir_snip(wl, y, iteraciones=iteraciones)


def _op_offset(wl, y, metodo="minimo", valor=0.0):
    return wl, restar_offset(y, metodo=metodo, valor=valor)


def _op_lineal(wl, y, wl_a=400.0, wl_b=500.0):
    return wl, corregir_lineal(wl, y, wl_a, wl_b)


def _op_polinomica(wl, y, anclas="400, 450, 500", orden=2):
    return wl, corregir_polinomica(wl, y, parsear_anclas(anclas), orden=orden)


def _op_normalizar(wl, y, modo="max", wl_ref=0.0):
    referencia = None
    if modo == "en_wl":
        referencia = float(wl_ref)
    return wl, normalizar(y, modo=modo, wl=wl, wl_ref=referencia)


def _op_derivar(wl, y, orden=1, ventana=9, polinomio=2):
    datos = _vector(y)
    ventana = _validar(ventana, max(int(polinomio), int(orden)), int(orden))
    return wl, savgol(datos, ventana=ventana, orden=max(int(polinomio), int(orden)),
                      derivada=int(orden), dx=_espaciado(wl))


def _op_recortar(wl, y, wl_min=0.0, wl_max=0.0):
    return recortar(wl, y,
                    wl_min if wl_min else None,
                    wl_max if wl_max else None)


def parsear_anclas(texto) -> List[float]:
    """'400, 450, 500' -> [400.0, 450.0, 500.0]."""
    if isinstance(texto, (list, tuple)):
        return [float(x) for x in texto]
    partes = [p.strip() for p in str(texto or "").replace(";", ",").split(",")]
    valores = []
    for parte in partes:
        if not parte:
            continue
        try:
            valores.append(float(parte))
        except ValueError:
            raise ValueError("Ancla '%s' no es un numero." % parte)
    if not valores:
        raise ValueError("Escribe al menos dos longitudes de onda de ancla.")
    return valores


_PARAM_VENTANA = Parametro("ventana", "Ventana (impar)", "int", 9, 3, 199,
                           (), "Numero de puntos de la ventana; debe ser impar.")
_PARAM_ORDEN = Parametro("orden", "Orden del polinomio", "int", 2, 0, 6)
_PARAM_MODO = Parametro("modo", "Borde", "lista", "reflect", None, None,
                        ("reflect", "symmetric", "nearest", "wrap", "constante"),
                        "Como se rellena el borde del espectro.")

OPERACIONES: Dict[str, Operacion] = {
    "suavizar_savgol": Operacion(
        "suavizar_savgol", "Suavizado Savitzky-Golay", "Suavizado", _op_savgol,
        (_PARAM_VENTANA, _PARAM_ORDEN, _PARAM_MODO),
        "Suaviza conservando la forma de los picos. La opcion habitual.",
    ),
    "suavizar_media": Operacion(
        "suavizar_media", "Media movil", "Suavizado", _op_media,
        (Parametro("ventana", "Ventana (impar)", "int", 5, 3, 199), _PARAM_MODO),
        "Rapida, pero aplana los picos.",
    ),
    "suavizar_mediana": Operacion(
        "suavizar_mediana", "Mediana movil", "Suavizado", _op_mediana,
        (Parametro("ventana", "Ventana (impar)", "int", 5, 3, 199),
         Parametro("modo", "Borde", "lista", "reflect", None, None,
                   ("reflect", "symmetric", "nearest", "wrap"))),
        "Robusta frente a picos espurios.",
    ),
    "despike": Operacion(
        "despike", "Quitar picos espurios", "Suavizado", _op_despike,
        (Parametro("ventana", "Ventana (impar)", "int", 5, 3, 199),
         Parametro("umbral", "Umbral (x MED)", "float", 3.0, 0.5, 20.0)),
        "Sustituye por la mediana local los puntos que se disparan.",
    ),
    "linea_snip": Operacion(
        "linea_snip", "Linea base SNIP", "Linea base", _op_snip,
        (Parametro("iteraciones", "Iteraciones", "int", 40, 1, 200),),
        "Algoritmo clasico de recorte iterativo; bueno para lineas base curvadas.",
    ),
    "linea_offset": Operacion(
        "linea_offset", "Quitar desplazamiento", "Linea base", _op_offset,
        (Parametro("metodo", "Referencia", "lista", "minimo", None, None,
                   ("minimo", "media", "mediana", "valor")),
         Parametro("valor", "Valor (si eliges 'valor')", "float", 0.0)),
        "Resta una constante: util para llevar el cero al minimo del espectro.",
    ),
    "linea_lineal": Operacion(
        "linea_lineal", "Linea base recta (2 puntos)", "Linea base", _op_lineal,
        (Parametro("wl_a", "Longitud de onda A (nm)", "float", 400.0),
         Parametro("wl_b", "Longitud de onda B (nm)", "float", 500.0)),
        "Resta la recta que une el valor en A con el valor en B.",
    ),
    "linea_polinomica": Operacion(
        "linea_polinomica", "Linea base polinomica (anclas)", "Linea base",
        _op_polinomica,
        (Parametro("anclas", "Anclas (nm, separadas por comas)", "texto",
                   "400, 450, 500"),
         Parametro("orden", "Orden", "int", 2, 1, 6)),
        "Ajusta un polinomio a las longitudes de onda de ancla y lo resta.",
    ),
    "normalizar": Operacion(
        "normalizar", "Normalizar", "Normalizacion", _op_normalizar,
        (Parametro("modo", "Criterio", "lista", "max", None, None,
                   ("max", "minmax", "area", "l2", "en_wl", "snv", "ninguna")),
         Parametro("wl_ref", "Longitud de onda de referencia (solo en_wl)", "float", 0.0)),
        "max: maximo=1 · minmax: 0..1 · area: integral=1 · l2: norma=1 · "
        "en_wl: valor en esa lambda=1 · snv: (y-media)/desviacion.",
    ),
    "derivar": Operacion(
        "derivar", "Derivar (Savitzky-Golay)", "Derivadas", _op_derivar,
        (Parametro("orden", "Orden de la derivada", "int", 1, 1, 2),
         Parametro("ventana", "Ventana (impar)", "int", 9, 3, 199),
         Parametro("polinomio", "Grado del polinomio", "int", 2, 1, 6)),
        "Deriva suavizando a la vez: revela hombros que en el espectro no se ven.",
    ),
    "recortar": Operacion(
        "recortar", "Recortar rango (nm)", "Seleccion", _op_recortar,
        (Parametro("wl_min", "Desde (nm)", "opcional_float", None),
         Parametro("wl_max", "Hasta (nm)", "opcional_float", None)),
        "Deja solo el rango indicado (sin interpolar).",
    ),
}


def grupos() -> List[str]:
    """Grupos de operaciones en orden de aparicion (para la interfaz)."""
    orden = []
    for operacion in OPERACIONES.values():
        if operacion.grupo not in orden:
            orden.append(operacion.grupo)
    return orden


def operaciones_de(grupo: str) -> List[Operacion]:
    return [o for o in OPERACIONES.values() if o.grupo == grupo]


def aplicar(clave: str, wl, y, **parametros):
    """Aplica una operacion del registro (rellenando parametros por defecto)."""
    if clave not in OPERACIONES:
        raise ValueError("Operacion '%s' desconocida." % clave)
    operacion = OPERACIONES[clave]
    valores = operacion.valores_por_defecto()
    valores.update({k: v for k, v in parametros.items() if k in valores})
    return operacion.fn(wl, y, **valores)


# ==========================================================================
# Cadena de procesado (no destructiva)
# ==========================================================================
@dataclass
class Cadena:
    """Secuencia de operaciones aplicadas en orden, con deshacer.

    Los pasos se guardan como ``{"clave": str, "parametros": dict}``; el
    espectro original nunca se toca, asi que "deshacer" es solo quitar el
    ultimo paso y volver a aplicar.
    """

    pasos: List[Dict] = field(default_factory=list)

    # -- gestion de pasos -------------------------------------------------
    def agregar(self, clave: str, **parametros) -> "Cadena":
        if clave not in OPERACIONES:
            raise ValueError("Operacion '%s' desconocida." % clave)
        operacion = OPERACIONES[clave]
        valores = operacion.valores_por_defecto()
        valores.update({k: v for k, v in parametros.items() if k in valores})
        self.pasos.append({"clave": clave, "parametros": valores})
        return self

    def quitar(self, indice: int) -> "Cadena":
        del self.pasos[int(indice)]
        return self

    def deshacer(self) -> bool:
        """Quita el ultimo paso.  True si se quito algo."""
        if self.pasos:
            self.pasos.pop()
            return True
        return False

    def limpiar(self) -> "Cadena":
        self.pasos.clear()
        return self

    def copia(self) -> "Cadena":
        return Cadena([{"clave": p["clave"], "parametros": dict(p["parametros"])}
                       for p in self.pasos])

    def __len__(self) -> int:
        return len(self.pasos)

    def __bool__(self) -> bool:
        return bool(self.pasos)

    # -- aplicacion -------------------------------------------------------
    def aplicar(self, wl, y):
        """Aplica la cadena completa y devuelve ``(wl, y)`` procesados."""
        longitudes, datos = np.asarray(wl, dtype=float), _vector(y)
        for paso in self.pasos:
            longitudes, datos = aplicar(paso["clave"], longitudes, datos,
                                        **paso["parametros"])
        return longitudes, datos

    # -- descripcion ------------------------------------------------------
    def etiquetas(self) -> List[str]:
        return [_texto_paso(p) for p in self.pasos]

    def descripcion(self) -> str:
        return " -> ".join(self.etiquetas()) if self.pasos else "(sin procesar)"


def _texto_paso(paso: Dict) -> str:
    """Texto corto y legible de un paso, con los parametros que no son por defecto."""
    operacion = OPERACIONES[paso["clave"]]
    partes = []
    for parametro in operacion.parametros:
        valor = paso["parametros"].get(parametro.nombre)
        if valor is None or valor == "":
            continue
        if valor == parametro.defecto and parametro.tipo != "lista":
            continue
        if parametro.tipo == "float":
            partes.append("%s=%g" % (parametro.nombre, float(valor)))
        else:
            partes.append("%s=%s" % (parametro.nombre, valor))
    detalle = ", ".join(partes)
    return "%s(%s)" % (operacion.etiqueta, detalle) if detalle else operacion.etiqueta
