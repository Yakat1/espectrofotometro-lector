@echo off
REM ---------------------------------------------------------------------------
REM Lanzador del banco de pruebas serie del espectrofotometro Jenway 6705.
REM
REM   Escanear_Serie.bat --listar          solo ver que puertos hay
REM   Escanear_Serie.bat                   escaneo rapido (15 configs, ~1 min)
REM   Escanear_Serie.bat --completo        132 configs, ~10 min
REM   Escanear_Serie.bat --flujo rtscts    con handshake RTS/CTS
REM   Escanear_Serie.bat --escuchar 60 --sin-sondas
REM                                        escucha pasiva 60 s sin enviar nada
REM   Escanear_Serie.bat --puerto COM3
REM   Escanear_Serie.bat --simular idn     autoprueba sin instrumento
REM
REM TIEMPOS DE ESPERA (son SEGUNDOS; aceptan unidad: 0.4, 90s, 1m30s, 500ms)
REM   --ventana 0.4       se escucha esto por sonda, siempre
REM   --ventana-larga 90s se AMPLIA a esto solo si algo empieza a llegar
REM                       (una consulta contesta en ms; un volcado de espectro
REM                        puede tardar minuto y medio)   --ventana-larga 0 lo apaga
REM   --asentar 1.5       pausa tras abrir el puerto, antes de la primera sonda
REM
REM   Escanear_Serie.bat --ventana-larga 3m --asentar 5s
REM                                        mas margen para una transferencia lenta
REM
REM Los informes quedan en la carpeta _escaneo_serie\
REM Guia completa: Escanear_Serie.md
REM ---------------------------------------------------------------------------
cd /d "%~dp0"
py -3.12 Script\escanear_serie.py %*
echo.
echo (pulsa una tecla para cerrar esta ventana)
pause >nul