# -*- coding: utf-8 -*-
"""
Parser de reportes (.TXT) impresos por el espectrofotómetro Jenway 6705.

Contexto verificado (15/09): el equipo, al "imprimir a CSV", genera un archivo
`.TXT` que NO es CSV delimitado: es un reporte de texto formateado en español,
con una cabecera de metadatos y una sección de datos por modo.

  - Codificación: Latin-1/CP1252 (los acentos rompen la detección binaria de
    muchas herramientas; aquí se decodifica explícitamente).
  - Estructura por registro:
        ======
        <cabecera metadatos>  (lineas 'etiqueta: ,valor' o 'etiqueta:,valor')
        ======
        <datos según modo>
    Un mismo archivo puede contener VARIOS registros seguidos (por ejemplo
    varias corridas de Cinética, o el consolidado INTRODUZ.TXT).

  - Detección de modo por la primera línea de cabecera (normalizada sin
    acentos): Fotometría, Espectro, Cinética, Longitud de onda (multi-λ),
    Cuantificación.

  - Nota de precisión: el reporte imprime los valores a 3 decimales y recorta
    (clampa) la absorbancia a 3.000 en saturación; el .JWB guarda el %T real.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def _sin_acentos(texto: str) -> str:
    """Quita tildes/diacríticos ('ó'->'o') para emparejar etiquetas en español."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    )


def _numero(texto: str) -> Optional[float]:
    """Convierte '2.947', '-0.301', '1,5' a float; None si no es numérico."""
    s = str(texto).strip().replace(",", ".")
    m = re.fullmatch(r"[-+]?\d*(?:\.\d+)?(?:[eE][-+]?\d+)?", s)
    if m and m.group(0):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _es_separador(linea: str) -> bool:
    s = linea.strip()
    return len(s) >= 2 and all(c == "=" for c in s)


def _dividir_etiqueta(linea: str) -> Optional[Tuple[str, str]]:
    """Parte una línea de cabecera 'etiqueta: ,valor' en (etiqueta, valor)."""
    if ":" not in linea:
        return None
    etiqueta, _, valor = linea.partition(":")
    etiqueta = etiqueta.rstrip(".").strip()
    valor = valor.lstrip(" \t,").strip()
    return (etiqueta, valor)


# --------------------------------------------------------------------------
# modelo
# --------------------------------------------------------------------------

@dataclass
class Registro:
    numero: int
    modo: str                       # canonico: photometrics|spectrum|kinetics|multi|quantitation
    etiqueta: str                   # primera linea de cabecera (cruda)
    meta: Dict[str, str] = field(default_factory=dict)
    cuerpo: Dict = field(default_factory=dict)

    def obtener_meta(self, *claves: str) -> Optional[str]:
        """Busca una clave en `meta` ignorando mayúsculas y tildes."""
        for clave in claves:
             if clave in self.meta:
                 return self.meta[clave]
        buscadas = {_sin_acentos(c).lower().strip() for c in claves}
        for k, v in self.meta.items():
            if not isinstance(k, str) or k.startswith("__"):
                continue
            if _sin_acentos(k).lower().strip() in buscadas:
                return str(v)
        return None

    @property
    def nombre_metodo(self) -> Optional[str]:
        return self.obtener_meta(
            "Método", "Metodo", "Nombre del método", "Nombre del metodo",
            "Method", "Method Name", "Methode", "Méthode", "Nom de méthode", "Nom de methode",
            "Methodenname", "Nome metodo", "Metodnamn",
        )

    @property
    def usuario(self) -> Optional[str]:
        return self.obtener_meta(
            "ID de usuario", "Nombre de usuario", "Usuario", "Operador",
            "User ID", "User Name", "Operator", "Opérateur", "Operateur",
            "Bediener", "Benutzer-ID", "Operatore", "Operatör",
        )

    @property
    def fecha(self) -> Optional[str]:
        return self.obtener_meta(
            "Muestra obtenida", "Última calibración", "Línea basal", "Fecha",
            "Sample obtained", "Last calibration", "Last calibrated", "Date", "Datum", "Data",
        )

    @property
    def longitud_onda(self) -> Optional[float]:
        raw = self.obtener_meta(
            "Longitud de onda", "Wavelength", "Longueur d'onde",
            "Wellenlänge", "Wellenlaenge", "Lunghezza d'onda", "Våglängd", "Vaglangd",
        )
        if not raw:
            return None
        limpio = re.sub(r"(?i)\s*nm\s*$", "", str(raw).strip())
        return _numero(limpio)

    def __repr__(self) -> str:  # pragma: no cover
        m = f", muestras={self.cuerpo.get('muestras')}" if "muestras" in self.cuerpo else ""
        return f"<Registro #{self.numero} {self.modo} '{self.nombre_metodo}'{m}>"


# --------------------------------------------------------------------------
# cabecera y modo
# --------------------------------------------------------------------------

_ALIASES = [
    ("photometrics", ["fotometr", "photometr", "colorimetr"]),
    ("spectrum", ["espectro", "spectrum", "spektrum", "spettro", "spectral"]),
    ("kinetics", ["cinetic", "cinetica", "kinetic", "kinetik"]),
    ("multi", [
        "longitud de onda", "multi wavelength", "multi-wavelength",
        "multiplos", "multipel", "longitude de onda",
        "multi-lunghezza", "multi-wellenlaengen", "multi-longueur",
    ]),
    ("quantitation", ["cuantific", "quantit", "kwant"]),
]


def _detectar_modo(etiqueta: str) -> str:
    e = _sin_acentos(etiqueta).lower()
    for canon, claves in _ALIASES:
        for clave in claves:
            if clave in e:
                return canon
    return "desconocido"


def _parsear_cabecera(header: List[str]) -> Dict[str, str]:
    meta = {}
    for linea in header:
        par = _dividir_etiqueta(linea)
        if par:
            etiqueta, valor = par
            meta[etiqueta] = valor
    return meta


_RE_STD_SERIE = re.compile(
    r"^\s*STD\s*\d+\s*:\s*,?\s*([-+]?\d+(?:[.,]\d+)?)\s*(?:,|\s+)\s*[^:]+:\s*,?\s*([-+]?\d+(?:[.,]\d+)?)\s*$",
    re.IGNORECASE,
)


def _parsear_estandares(header: List[str]) -> List[Tuple[float, float]]:
    """Cuantificación: pares (concentración, absorbancia) desde 'Std i:,c,Resultado i:,r'
    o formato serie de 40 columnas 'STD i:   c   RESULTADO i:   r'."""
    stds = []
    for linea in header:
        m_serie = _RE_STD_SERIE.match(linea)
        if m_serie:
            conc = _numero(m_serie.group(1))
            absv = _numero(m_serie.group(2))
            if conc is not None and absv is not None:
                stds.append((conc, absv))
            continue
        m = re.match(r"^\s*Std\s+\d+\s*:", linea, re.IGNORECASE)
        if not m:
            continue
        _, _, resto = linea.partition(":")
        resto = resto.lstrip(", \t")
        partes = [p.strip() for p in resto.split(",") if p.strip()]
        if len(partes) >= 2:
            conc = _numero(partes[0])
            absv = _numero(partes[-1])
            if conc is not None and absv is not None:
                stds.append((conc, absv))
    return stds


# --------------------------------------------------------------------------
# cuerpos por modo
# --------------------------------------------------------------------------

_RE_PHOTO_SERIE = re.compile(
    r"^\s*(\d+)\s+"
    r"([-+]?\d+(?:[.,]\d+)?)\s*(?:ABS)?\s+"
    r"([-+]?\d+(?:[.,]\d+)?)\s*(?:%T|T%)\s+"
    r"(\S+(?:\s+\S+)?)\s*$",
    re.IGNORECASE,
)

_RE_QUANT_SERIE = re.compile(
    r"^\s*(\d+)\s+"
    r"([-+]?\d+(?:[.,]\d+)?)\s*ABS\s+"
    r"([-+]?\d+(?:[.,]\d+)?)\s*(?!(?:%T|T%)\b)([A-Za-z%µ/]+)\s*"
    r"(.*?)\s*$",
    re.IGNORECASE,
)


def _filas_photometrics(data: List[str]) -> List[Dict]:
    filas = []
    for linea in data:
        s = linea.strip()
        if not s:
            continue
        partes = [p.strip() for p in s.split(",")]
        if len(partes) >= 4 and _numero(partes[0]) is not None:
            filas.append({"id": partes[0], "abs": partes[1], "t": partes[2], "hora": partes[3]})
            continue
        # Formato de ticket serie de 40 columnas: "001 3.000ABS 0.0%T 10:36:36 19/10/26"
        m = _RE_PHOTO_SERIE.match(s)
        if m:
            filas.append({
                "id": m.group(1),
                "abs": m.group(2).replace(",", "."),
                "t": m.group(3).replace(",", "."),
                "hora": m.group(4).strip(),
            })
    return filas


def _cuerpo_spectrum(data: List[str]) -> Dict:
    puntos = []
    for linea in data:
        m = re.match(
            r"^\s*(-?[\d.]+)\s*(?:nm)?\s*(?:,|\s+)\s*(-?[\d.]+)\s*(?:ABS|%T|T%)?\s*$",
            linea.strip(),
            re.IGNORECASE,
        )
        if m:
            wl = _numero(m.group(1))
            val = _numero(m.group(2))
            if wl is not None and val is not None:
                puntos.append((wl, val))
    return {"puntos": puntos}


def _cuerpo_multi(data: List[str]) -> Dict:
    lote = None
    celdas = []
    calculos = {}
    for linea in data:
        s = linea.strip()
        m_lote = re.match(r"^\s*\d+\s*(?:,|\s+)\s*([0-9:/ ]+)\s*$", s)
        if m_lote and lote is None:
            lote = m_lote.group(1).strip()
            continue
        m_celda = re.match(
            r"^\s*\d+\s*-\s*,?\s*(\d+\.\d+)\s*nm\s*(?:[, ]+\s*([A-Z]\d))?\s*[, ]+\s*(-?[\d.]+)\s*(?:ABS|%T|T%)?\s*$",
            s,
            re.IGNORECASE,
        )
        if m_celda:
            celdas.append({"wl": float(m_celda.group(1)),
                           "etiqueta": m_celda.group(2),
                           "valor": float(m_celda.group(3))})
            continue
        m_calc = re.match(
            r"^\s*A1/A2\s*[,= ]+\s*(-?[\d.]+)\s*[, ]+\s*A1-A2\s*[,= ]+\s*(-?[\d.]+)\s*$",
            s,
        )
        if m_calc:
            calculos = {"A1/A2": float(m_calc.group(1)),
                        "A1-A2": float(m_calc.group(2))}
    return {"lote": lote, "celdas": celdas, "calculos": calculos}


_RE_CAB_CELDA = re.compile(
    r"^\s*(?:(?:Hora|Time)[^\n,]*,\s*)?(?:Celda|Cell|Carril|Cuvette|Posici[oó]n|Position)\s*[,:]?\s*(\d+)\s*$",
    re.IGNORECASE,
)


def _cuerpo_kinetics(data: List[str]) -> Dict:
    series: List[Dict] = []
    puntos_actuales: List[Tuple[float, float]] = []
    celda_actual: Optional[int] = None
    lote_txt: Optional[str] = None
    ultimo_tiempo: Optional[float] = None

    def _guardar_serie_activa():
        nonlocal puntos_actuales, celda_actual, ultimo_tiempo
        if puntos_actuales:
            c = celda_actual if celda_actual is not None else (len(series) + 1)
            series.append({
                "celda": c,
                "lote": lote_txt,
                "serie": list(puntos_actuales),
            })
            puntos_actuales = []
            ultimo_tiempo = None

    for linea in data:
        s = linea.strip()
        if not s:
            continue
        if s.startswith("Lote") or s.endswith(":-") or s.lower().startswith("batch"):
            if puntos_actuales:
                _guardar_serie_activa()
                celda_actual = None
            lote_txt = s.split(":")[0].strip()
            continue

        # Encabezado de celda / carril: "Hora (  segundos),Celda,1", "Celda 2", "Carril 2", etc.
        m_cab = _RE_CAB_CELDA.match(s)
        if m_cab:
            num_celda = int(m_cab.group(1))
            if puntos_actuales:
                _guardar_serie_activa()
            celda_actual = num_celda
            continue

        # Encabezado genérico en ticket serie de 40 columnas: "HORA ABS" o "TIME ABS"
        if re.match(r"^\s*(?:HORA|TIME)\b", _sin_acentos(s), re.IGNORECASE):
            if puntos_actuales:
                _guardar_serie_activa()
                celda_actual = len(series) + 1
            elif celda_actual is None:
                celda_actual = 1
            continue

        # Línea de 3 columnas: tiempo, celda (1..8), abs (e.g. "0, 1, 1.872" o "0  1  1.872")
        m_3col = re.match(
            r"^\s*(\d+(?:\.\d+)?)\s*[, \t]+\s*([1-8])\s*[, \t]+\s*(-?[\d.]+)\s*$",
            s,
        )
        if m_3col:
            t = float(m_3col.group(1))
            c = int(m_3col.group(2))
            a = float(m_3col.group(3))
            encontrada = False
            for s_dict in series:
                if s_dict["celda"] == c:
                    s_dict["serie"].append((t, a))
                    encontrada = True
                    break
            if not encontrada:
                if celda_actual == c:
                    puntos_actuales.append((t, a))
                else:
                    series.append({"celda": c, "lote": lote_txt, "serie": [(t, a)]})
            continue

        # Línea estándar de pares (tiempo, absorbancia)
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:,|\s+)\s*(-?[\d.]+)\s*$", s)
        if m:
            t = float(m.group(1))
            a = float(m.group(2))
            if celda_actual is None:
                celda_actual = len(series) + 1

            # Detección de reinicio de tiempo: t < ultimo_tiempo (o t == 0 cuando ya se avanzó)
            if (
                ultimo_tiempo is not None
                and len(puntos_actuales) >= 2
                and (t < ultimo_tiempo or (t == 0.0 and ultimo_tiempo > 0.0))
            ):
                _guardar_serie_activa()
                celda_actual = len(series) + 1

            puntos_actuales.append((t, a))
            ultimo_tiempo = t
            continue

    if puntos_actuales:
        _guardar_serie_activa()

    primera_serie = series[0]["serie"] if series else []
    primera_celda = series[0]["celda"] if series else 1
    return {
        "celda": primera_celda,
        "lote": lote_txt,
        "serie": primera_serie,
        "series": series,
    }


def _cuerpo_quantitation(data: List[str]) -> Dict:
    muestras = []
    for linea in data:
        s = linea.strip()
        if not s:
            continue
        m_cab = re.match(r"^\s*Id\s*,.*\s*$", s, re.IGNORECASE)
        if m_cab:
            continue
        m = re.match(r"^\s*(\S+)\s*,\s*(-?[\d.]+)\s*,\s*([-\d.]+)([a-zA-Zµ%]*)\s*,?\s*(.*?)\s*$", s)
        if m and _numero(m.group(2)) is not None:
            conc_num = _numero(m.group(3))
            muestras.append({"id": m.group(1),
                             "abs": float(m.group(2)),
                             "conc": conc_num,
                             "unidades": m.group(4) or "",
                             "fecha": m.group(5).strip()})
            continue
        # Formato de ticket serie de 40 columnas: "001  3.000ABS    0.00PPM 12:51:23"
        m_ser = _RE_QUANT_SERIE.match(s)
        if m_ser:
            abs_num = _numero(m_ser.group(2))
            conc_num = _numero(m_ser.group(3))
            if abs_num is not None:
                muestras.append({
                    "id": m_ser.group(1),
                    "abs": float(abs_num),
                    "conc": conc_num,
                    "unidades": m_ser.group(4) or "",
                    "fecha": m_ser.group(5).strip(),
                })
    return {"muestras": muestras}


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------

def parsear_reporte(ruta) -> List[Registro]:
    """Lee un .TXT de reporte (ruta o pathlib) y devuelve la lista de registros."""
    with open(ruta, "rb") as fh:
        datos = fh.read()
    return parsear_bytes(datos)


def parsear_bytes(datos: bytes) -> List[Registro]:
    return parsear_texto(_decodificar(datos))


def parsear_texto(texto: str) -> List[Registro]:
    """Parsea una cadena de texto (de archivo .TXT o de stream serie RS-232)."""
    limpio = texto.replace("\x00", "").replace("\x01", "").replace("\r\n", "\n").replace("\r", "\n")
    lineas = limpio.split("\n")
    seps_raw = [i for i, l in enumerate(lineas) if _es_separador(l)]

    # Colapsar separadores '====' consecutivos (p. ej. fin de un ticket + inicio del siguiente)
    seps: List[int] = []
    for idx in seps_raw:
        if seps and not any(lineas[k].strip() for k in range(seps[-1] + 1, idx)):
            continue
        seps.append(idx)

    if not seps:
        filas_sueltas = _filas_photometrics(lineas)
        if filas_sueltas:
            return [
                Registro(
                    numero=0,
                    modo="photometrics",
                    etiqueta="PHOTOMETRICS MODE",
                    meta={},
                    cuerpo={"filas": filas_sueltas},
                )
            ]
        muestras_sueltas = _cuerpo_quantitation(lineas).get("muestras", [])
        if muestras_sueltas:
            return [
                Registro(
                    numero=0,
                    modo="quantitation",
                    etiqueta="QUANTITATION MODE",
                    meta={},
                    cuerpo={"muestras": muestras_sueltas},
                )
            ]
        return []

    registros: List[Registro] = []
    nrec = (len(seps) + 1) // 2
    for i in range(nrec):
        h0 = seps[2 * i] + 1
        h1 = seps[2 * i + 1] if 2 * i + 1 < len(seps) else len(lineas)
        header = [l.strip() for l in lineas[h0:h1] if l.strip()]
        d0 = seps[2 * i + 1] + 1 if 2 * i + 1 < len(seps) else len(lineas)
        d1 = seps[2 * i + 2] if 2 * i + 2 < len(seps) else len(lineas)
        data = [l.strip() for l in lineas[d0:d1] if l.strip()]

        if not header and not data:
            continue

        etiqueta = header[0] if header else ""
        modo = _detectar_modo(etiqueta.split(":", 1)[0])
        meta = _parsear_cabecera(header)
        stds = _parsear_estandares(header)
        # En firmware español V1.64.5, el modo Cuantificación por RS-232 imprime
        # "MODO FOTOMETRíA....." en la primera línea pero incluye STD 1..N y AJUSTE DE CURVA
        if modo == "quantitation" or stds or any(
            re.search(r"\b(?:STD\s*\d+|AJUSTE DE CURVA|CURVE FIT)\b", _sin_acentos(l), re.IGNORECASE)
            for l in header
        ):
            modo = "quantitation"
            meta["__estandares__"] = stds

        cuerpo = {}
        if modo == "photometrics":
            cuerpo = {"filas": _filas_photometrics(data)}
        elif modo == "spectrum":
            cuerpo = _cuerpo_spectrum(data)
        elif modo == "multi":
            cuerpo = _cuerpo_multi(data)
        elif modo == "kinetics":
            cuerpo = _cuerpo_kinetics(data)
        elif modo == "quantitation":
            cuerpo = _cuerpo_quantitation(data)
        else:
            filas_cont = _filas_photometrics(header + data)
            if filas_cont:
                modo = "photometrics"
                etiqueta = "PHOTOMETRICS MODE"
                cuerpo = {"filas": filas_cont}
            else:
                muestras_cont = _cuerpo_quantitation(header + data).get("muestras", [])
                if muestras_cont:
                    modo = "quantitation"
                    etiqueta = "QUANTITATION MODE"
                    cuerpo = {"muestras": muestras_cont}
                else:
                    kin_cont = _cuerpo_kinetics(header + data)
                    if kin_cont.get("series") and any(len(s.get("serie", [])) > 0 for s in kin_cont["series"]):
                        if registros and registros[-1].modo == "kinetics":
                            prev_series = list(registros[-1].cuerpo.get("series") or [])
                            if not prev_series and registros[-1].cuerpo.get("serie"):
                                prev_series = [{"celda": registros[-1].cuerpo.get("celda", 1), "serie": registros[-1].cuerpo["serie"]}]
                            prev_series.extend(kin_cont["series"])
                            registros[-1].cuerpo["series"] = prev_series
                            continue
                        modo = "kinetics"
                        etiqueta = "KINETICS MODE"
                        cuerpo = kin_cont
                    else:
                        cuerpo = {"raw": data}

        registros.append(Registro(numero=len(registros), modo=modo, etiqueta=etiqueta,
                                  meta=meta, cuerpo=cuerpo))
    return registros


def _decodificar(datos: bytes) -> str:
    """Decodifica bytes de reporte o captura serie.

    Prueba primero UTF-8 (estricto: solo pasa si los bytes son UTF-8 válido, como
    las capturas guardadas desde consola en Windows) y luego CP1252/Latin-1
    (codificación nativa del firmware del Jenway 6705).
    """
    limpios = datos.replace(b"\x00", b"").replace(b"\x01", b"")
    for cod in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return limpios.decode(cod)
        except UnicodeDecodeError:
            continue
    return limpios.decode("cp1252", errors="replace")