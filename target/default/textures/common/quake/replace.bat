@echo off 
setlocal EnableExtensions DisableDelayedExpansion

set "search=common/quake-fu"
set "replace=common/quake"

set "textFile=*.mat"
set "rootDir=."

for %%j in ("%rootDir%\%textFile%") do (
    for /f "delims=" %%i in ('type "%%~j" ^& break ^> "%%~j"') do (
        set "line=%%i"
        setlocal EnableDelayedExpansion
        set "line=!line:%search%=%replace%!"
        >>"%%~j" echo(!line!
        endlocal
    )
)