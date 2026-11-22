# Empaquetar PDFiu

**Español** · [English](LEEME.en.md) · [Inicio](../README.md)

Estas recetas preparan artefactos de prueba. El código propio se distribuye bajo [MIT](../LICENSE). La compilación incorpora la licencia de PDFiu, los [avisos de terceros](../THIRD_PARTY_NOTICES.md) y un inventario de las dependencias y modelos usados. Contrasta esos avisos con los archivos realmente incluidos antes de distribuir el binario.

Para la compilación Windows con Qt 6.12.0, las referencias de origen son [Qt Base](https://github.com/qt/qtbase/tree/v6.12.0), [Qt SVG](https://github.com/qt/qtsvg/tree/v6.12.0), [Qt Translations](https://github.com/qt/qttranslations/tree/v6.12.0) y [PySide6 y Shiboken](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/). Antes de la publicación del binario, verifica estas referencias contra las ruedas usadas, documenta parches y configuración de compilación aplicables y establece cómo se ofrece el código correspondiente a los usuarios de esa descarga. En Windows, verifica también la sustitución de las bibliotecas LGPL compatibles en `_internal` y las condiciones de los componentes nativos del OCR.

## Windows

1. En un entorno virtual de Python 3.12 x64, instala `requirements.txt` y PyInstaller. Usa Inno Setup 6.3 o posterior con la receta `windows.iss`.
2. Define la versión en `release_info.py`. Desde el directorio de PDFiu, ejecuta `python packaging/build_app.py --tessdata "RUTA_A_TESSDATA" --output "RUTA_DE_COMPILACION"`. Añade `--dry-run` para inspeccionar los parámetros sin compilar.
3. Define `PDFIU_BUILD_DIR` con la ruta absoluta de compilación. Ejecuta `ISCC.exe packaging/windows.iss`. El instalador usa la misma versión que muestra la app.
4. Comprueba el arranque sin Python instalado, OCR en ambos idiomas, firma con el almacén de Windows y con PFX, actualización y desinstalación. Los objetivos son Windows 10 1809 o posterior y Windows 11, ambos x64. La receta limita la instalación a equipos x64. Para admitir Windows ARM, valida primero la emulación o prepara un paquete ARM nativo.
5. Para una distribución pública, firma el ejecutable y el instalador con el certificado de publicación que corresponda.

La instalación es por usuario. El desinstalador retira los archivos instalados, el acceso del menú Inicio, las preferencias y las sesiones temporales de `%LOCALAPPDATA%\PDFiu`. Si PDFiu está abierto, el instalador y el desinstalador piden cerrarlo para que el usuario pueda guardar su trabajo. Al actualizar desde una versión anterior, se conserva la ruta de instalación. PDFiu importa las preferencias antiguas si todavía no tiene preferencias propias.

### Actualizaciones

Conserva el `AppId` y el ámbito por usuario. Cada versión debe tener su propio número. Instala primero una versión y actualiza con la siguiente sobre la misma carpeta. Comprueba que queda una sola entrada en Aplicaciones instaladas, que se conservan las preferencias y que el desinstalador retira los archivos de ambas versiones.

**Ayuda → Buscar actualizaciones** consulta el canal incluido al compilar con `--updates-url https://tu-dominio/updates.json` y ofrece abrir la página de la nueva versión en el navegador. El manifiesto admite un número de versión con tres partes y una URL HTTPS indicando dónde descargar los instaladores firmados:

```json
{"version":"0.2.1","url":"https://tu-dominio/descargas/0.2.1"}
```

Si omites `--updates-url`, la consulta muestra la versión instalada y avisa de que el canal aún no está configurado.

## macOS

Compila en macOS con Python 3.12, las dependencias nativas de la arquitectura elegida y los dos modelos de OCR. Ejecuta el mismo script. PyInstaller genera el paquete `.app`. Valida Apple Silicon e Intel en compilaciones separadas. Un binario universal requiere que todas las extensiones nativas tengan ambas arquitecturas.

Comprueba específicamente la instalación de Tesseract y los binarios de `tesserocr`. La firma con archivos PFX/P12 ya tiene un camino independiente de Windows. El llavero de macOS requiere una integración específica. Para distribuir fuera de App Store, firma el paquete con Developer ID y notarízalo con Apple.
