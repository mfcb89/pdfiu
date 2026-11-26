<img src="assets/brand/pdfiu-wordmark.svg" alt="PDFiu" width="220">

# PDFiu

**Español** · [English](README.en.md)

![Versión 0.12.1](https://img.shields.io/badge/version-0.12.1-2f7d6d?style=flat-square)
![Licencia MIT](https://img.shields.io/badge/license-MIT-182a3d?style=flat-square)
![Windows x64](https://img.shields.io/badge/Windows-x64-294459?style=flat-square)
![100% local](https://img.shields.io/badge/privacidad-100%25%20local%20%C2%B7%20sin%20cuenta-317f72?style=flat-square)

Lector y editor de PDF de código abierto creado por **mfcb89**, pensado como alternativa ligera y 100% local a los lectores propietarios pesados. Abre, organiza, edita, firma, mide planos y convierte documentos desde una aplicación de escritorio sin cuentas, sin nube y sin telemetría. La interfaz (con tema claro y oscuro) y la visita guiada están disponibles en español e inglés.

![PDFiu en español con el documento de bienvenida, miniaturas y herramientas](docs/pdfiu-es.png)

## Por qué PDFiu

- **100 % local, sin nube y sin cuenta:** tus PDF se procesan únicamente en tu equipo. Desbloqueo, censura irreversible, firma digital, OCR y compresión funcionan sin subir archivos a ninguna web y sin límites diarios de tareas.
- **Pago único tras 15 días de prueba completa:** sin suscripciones mensuales, sin popups de *upgrade* y sin funciones esenciales bloqueadas.
- **Todo en una app ligera (~92 MB):** estima antes de comprimir si vas a ahorrar peso y compáralo al 100 %, firma con certificado (individual o en lote) o con firma visual (`PNG`/`JPG`/`PDF`), compara dos PDF visualmente (documentos, imágenes o planos), aplica OCR sin conexión y exporta a Word, Excel y Markdown.
- **Código abierto sostenible:** el código fuente es público bajo licencia MIT y puedes compilarlo gratis en tu equipo. La versión oficial en Microsoft Store financia el desarrollo y las actualizaciones.

## Capturas de funciones

| Compresión inteligente (3 niveles + avanzadas) | Panel de Firmas en modo oscuro |
| :---: | :---: |
| ![Compresión inteligente con 3 niveles y opciones avanzadas](docs/screenshots/compress.png) | ![Panel de firmas con tarjetas de integridad en tema oscuro](docs/screenshots/signatures-dark.png) |

| Firma visual (PNG, JPG o PDF con fondo transparente) | Organizar páginas arrastrando en cuadrícula |
| :---: | :---: |
| ![Firma visual desde imagen o PDF con eliminación automática de fondo blanco](docs/screenshots/visual-sign.png) | ![Cuadrícula visual para reordenar, girar y borrar páginas](docs/screenshots/organize.png) |

## Qué puedes hacer

| Área | Funciones |
| --- | --- |
| **Lectura y navegación** | Pestañas desmontables en varias ventanas, indicador siempre visible **Página X de Y**, vista continua o **doble página (`Ctrl+2`)**, tema claro y oscuro, panel lateral redimensionable, filtro de marcadores, búsqueda rápida (`Ctrl+F`) y paleta de comandos (`Ctrl+K`). |
| **Organizar, unir y dividir** | **Cuadrícula visual de páginas** para reordenar arrastrando, girar o eliminar; unir varios PDF con índice automático, **dividir PDF** por rangos o cada N hojas, extraer páginas, varias páginas por hoja y mesa de trabajo en lote. |
| **Comprimir PDF** | **3 niveles rápidos** (*Baja*, *Recomendada* y *Extrema*) más **Opciones avanzadas**: **estima antes si realmente vas a ahorrar peso**, comprime imágenes `RGB`, `ICCBased`, `CMYK`, `JPEG2000` y transparencias (`SMask`), paso a escala de grises, limpieza de datos privados/miniaturas/metadatos y **comparación visual al 100 %** antes de guardar. |
| **Editar y anotar** | Editar texto compatible, añadir texto nuevo, rellenar y fijar formularios **AcroForm**, encabezados, pies y numeración de páginas; resaltados, subrayados, notas, formas y panel de anotaciones con filtros. |
| **Firmar (certificado y visual)** | Firma digital **PAdES (RSA y ECDSA)** individual o **múltiple en lote** con certificados de Windows (FNMT/DNIe) o `.pfx`/`.p12`, **firma visual desde `PNG`, `JPG`, `WebP` o `PDF`** con eliminación automática de fondo blanco, y explorador de firmas en tarjetas con verificación de integridad. |
| **Proteger y privacidad** | **Desbloquear PDF sin suscripciones ni nube**, cifrar copias con contraseña **AES-256**, **censura irreversible real** (borra el contenido subyacente, con OCR opcional) y **preparar copia para compartir** sin metadatos. |
| **OCR y exportación** | **OCR local sin conexión ni límites** en español e inglés (Tesseract). Exportar a **Word (`.docx`)**, **Excel (`.xlsx`)**, **CSV**, **Markdown (`.md`)** con vista previa, **TXT**, **PNG**, **PDF/A** y **copiar página como imagen** (`Ctrl+Shift+C`). |
| **Comparar PDF, planos e impresión** | **Compara dos PDF visualmente** (documentos, imágenes o planos) en paralelo, superpuestos o resaltando diferencias en color; calibra escalas `1:N` y mide distancias, perímetros y superficies. Impresión con vista previa, tamaño real, mosaico y folleto. |

[Manual de usuario](LEEME.md) · [Guía de compilación](packaging/LEEME.md) · [Política de privacidad](PRIVACY.md) · [Historial de cambios](CHANGELOG.md)

## Obtener PDFiu

### Tienda oficial (Microsoft Store · Windows x64)

La versión oficial lista para usar en Windows 10/11 (sin instalar Python ni dependencias, con modelos de OCR incluidos, pago único y **15 días de prueba gratuita**) está disponible en [Microsoft Store](https://apps.microsoft.com/detail/9NK06R3SRRW3) y financia el desarrollo continuo y las actualizaciones.

### Ejecutar gratis desde el código fuente

El repositorio público contiene el código fuente completo. La receta de instalador está pensada para Windows x64; el empaquetado de macOS se realiza en macOS y requiere validación en la arquitectura de destino.

1. Abre una terminal PowerShell con Git y Python 3.12 de 64 bits.
2. Clona el repositorio y ejecuta estos comandos:

```powershell
git clone https://github.com/mfcb89/pdfiu.git
cd pdfiu
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdfiu.py
```

Para habilitar el OCR en español e inglés, coloca `spa.traineddata` y `eng.traineddata` en `runtime/tessdata`. [Preparar los modelos de OCR](LEEME.md#preparar-los-modelos-de-ocr)

## Compatibilidad

- La edición de formularios usa AcroForm. Los formularios que dependen únicamente de XFA dinámico requieren un lector compatible con XFA.
- La firma básica admite archivos P12/PFX y, en Windows, certificados compatibles del almacén del sistema. El panel de firmas muestra los datos disponibles del certificado. La confianza de la cadena, el sellado de tiempo y la validación de larga duración quedan fuera de esta versión.
- Word reconstruye el diseño de forma aproximada. Los planos complejos, las columnas y las páginas escaneadas pueden requerir ajustes.
- PDF/A requiere Ghostscript, veraPDF y Java. La censura rasteriza las páginas marcadas y ofrece OCR para recuperar el texto visible. [Detalles de uso](LEEME.md)

## Contribuir, seguridad y licencia

- Abre una [incidencia](https://github.com/mfcb89/pdfiu/issues) o envía una propuesta de cambios (en español o inglés). [Guía de contribución](CONTRIBUTING.md)
- Para informar de un problema de seguridad en privado, consulta [SECURITY.md](SECURITY.md).
- El código fuente original de PDFiu se distribuye bajo la [licencia MIT](LICENSE). Puedes usar, modificar y redistribuir el código, incluso comercialmente, conservando el aviso de copyright y la licencia.
- El nombre **PDFiu** y los logotipos en `assets/brand/` están reservados y no se incluyen en la licencia MIT. Consulta la [política de marca](TRADEMARKS.md).
- Las bibliotecas y recursos de terceros mantienen sus propios términos (incluidos Qt y PySide6 bajo LGPLv3). Consulta los [avisos de terceros](THIRD_PARTY_NOTICES.md) antes de redistribuir un binario.
