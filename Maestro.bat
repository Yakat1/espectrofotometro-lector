@echo off
REM ============================================================
REM  Lanzador del Programa Maestro - Jenway 6705
REM  Uso:  Maestro.bat ["C:\ruta\a\tarjeta"] [--tema dark|light]
REM ============================================================
setlocal
cd /d "%~dp0"

REM Si existe la version portable empaquetada, se usa esa (no
REM necesita Python). Si no, se cae al codigo fuente con Python.
REM La chispa de "se la lleva a cualquier maquina": copiar
REM empaquetado\Programa_Maestro\ a la otra maquina y lanzar
REM Programa_Maestro.exe.
if exist "%~dp0empaquetado\Programa_Maestro\Programa_Maestro.exe" (
    "%~dp0empaquetado\Programa_Maestro\Programa_Maestro.exe" %*
    goto :fin
)

REM Probar Python 3.12 con las dependencias; luego py -3; luego python
py -3.12 -c "import PySide6, matplotlib, numpy, openpyxl" >nul 2>&1
if %errorlevel%==0 (
    py -3.12 Script\maestro_gui.py %*
    call :despedida
    goto :fin
)

py -3 -c "import PySide6, matplotlib, numpy, openpyxl" >nul 2>&1
if %errorlevel%==0 (
    py -3 Script\maestro_gui.py %*
    call :despedida
    goto :fin
)

echo.
echo  No se encontro un Python 3 con las dependencias necesarias.
echo  Instalalas con:  py -3.12 -m pip install PySide6 matplotlib numpy openpyxl
echo.
pause
goto :fin

REM --- Si la aplicacion se cierra (sobre todo si es por un error), dejar la
REM     ventana abierta: si no, el fallo se va con la consola y no se ve nada.
:despedida
echo.
echo  La aplicacion se ha cerrado.
echo  Si arriba hay un error, copialo y mandalo. Tambien queda en
echo  maestro_errores.log
echo.
pause
goto :eof

:fin
endlocal
