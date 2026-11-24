# Historial de cambios / Changelog

Todos los cambios relevantes de PDFiu se documentan en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa versionado semántico (`MAJOR.MINOR.PATCH`).

## [Sin publicar] / [Unreleased]

## [0.12.1] - 2026-11-24

### Añadido / Added
- **Compresión PDF mejorada** con 3 niveles sencillos (*Baja · Alta calidad*, *Recomendada · Equilibrada* y *Extrema · Menor peso*) y sección plegable **Opciones avanzadas** (sin pérdida en imágenes, calidad JPEG, resolución máxima, escala de grises, eliminación de datos privados de edición `/PieceInfo`, miniaturas `/Thumb` y metadatos XMP).
- Soporte de compresión y remuestreo para imágenes **`/ICCBased`**, **`CMYK`**, **`JPEG2000` (`/JPXDecode`)** y transparencias **`/SMask`** manteniendo el canal alfa.
- **Panel lateral izquierdo redimensionable** arrastrando su borde (`QSplitter`) para **Páginas**, **Marcadores**, **Firmas**, **Archivos** y **Capas**.
- **Panel de Firmas rediseñado** con tarjetas por estado/color (*Íntegra · Vigente*, *Caducada*, *Alterada*), filtro por firmante o campo, divisor vertical arrastrable entre la lista y los detalles y botón *Ocultar/Ver detalles*.
- **Política de privacidad** bilingüe en [PRIVACY.md](PRIVACY.md) y 30 pruebas automatizadas.

### Cambiado / Changed
- **Panel de herramientas simplificado:** `Documento` ordenado por frecuencia real de uso (7 acciones claras), `PDF/A (archivo)…` y `Copiar página como imagen` en `Exportar`, y `Preparar copia para compartir…` accesible en `Proteger`.
- **Pantalla de bienvenida y diálogos modernizados:** tarjeta inicial más ancha con márgenes cómodos, logotipo adaptado al modo oscuro, controles modernos (`QCheckBox`, `QRadioButton`, `QDoubleSpinBox`, tarjetas `dialogCard`) y anchos mínimos en todos los diálogos.

## [0.12.0] - 2026-11-23

### Añadido / Added
- **Vista de doble página** (`Vista → Doble página`, botón de tamaño del lateral y atajo `Ctrl+2`).
- **Pestañas de documentos** encima del visor con botón de cierre Fluent UI, indicador `•` de cambios sin guardar, menú contextual y **arrastrar pestaña fuera para abrirla en una nueva ventana**.
- **Barra de búsqueda superior compacta** (`Ctrl+F`) con contador en vivo (`3 / 16`), salto rápido (`↑`/`↓`), botón de tildes y acceso al panel completo.
- **Organizar páginas en cuadrícula** (miniaturas arrastrables con deslizador de tamaño, giro de 90° y borrado en lote).
- **Dividir PDF** cada *N* páginas con vista previa del número de archivos a crear.
- **Soporte de certificados ECDSA (P-256 / P-384)** además de RSA en el almacén de Windows (`windows_cert.ps1` y `pdf_sign.py`).
- Pruebas automáticas reales de firma `.pfx` (RSA y ECDSA), censura irreversible, compresión, división de PDF y arranque de interfaz (26 tests en total).
- Página web estática en [docs/index.html](docs/index.html) lista para GitHub Pages con información del modelo de distribución y sección de cumplimiento LGPLv3.

### Cambiado / Changed
- Todos los iconos SVG se adaptan automáticamente al **tema oscuro** y se actualizan en vivo al cambiar de tema en Preferencias.
- Guardado directo (`Ctrl+S`) sin confirmación repetitiva sobre archivos ya guardados (manteniendo la protección de originales firmados).

## [0.11.0] - 2026-11-23

### Añadido / Added
- Panel de anotaciones rediseñado con tarjetas por tipo/color, buscador de texto y filtro por categoría.
- Paleta de comandos (`Ctrl+K`) para buscar y lanzar cualquier herramienta o acción al instante.
- Filtro de búsqueda en el panel de **Marcadores** conservando los nodos padres de contexto.
- Tema oscuro instantáneo en **Preferencias** (**Tema del sistema**, **Claro** y **Oscuro**).
- Registro local de errores en `%LOCALAPPDATA%\PDFiu\logs\pdfiu.log` (cero telemetría) con acceso en **Ayuda → Abrir carpeta de registros…**.
- Canal de actualizaciones activo por defecto con [updates.json](updates.json), soporte opcional de notas (`notes`) y huella `sha256`, comprobación opcional al iniciar y botón «Omitir esta versión».
- Política de marca y logotipos en [TRADEMARKS.md](TRADEMARKS.md) separando el código MIT de los activos de marca.
- Diálogo «Acerca de PDFiu» ampliado con información de licencia MIT, aviso LGPLv3 de Qt/PySide6, acceso a los avisos de terceros y cuadro «Acerca de Qt».
- Metadatos de editor y licencia en el instalador de Windows ([packaging/windows.iss](packaging/windows.iss)).
- Política de seguridad ([SECURITY.md](SECURITY.md)), plantillas de incidencias/PRs en `.github/` y 21 pruebas automatizadas en `tests/`.

### Cambiado / Changed
- Modularización de [pdfiu.py](pdfiu.py) extrayendo [pdfiu_views.py](pdfiu_views.py) y [pdfiu_dialogs.py](pdfiu_dialogs.py).
- Atajo de **Preferencias** unificado en `Ctrl+,` para liberar `Ctrl+K` para la **Paleta de comandos**.
- Manual de usuario ([LEEME.md](LEEME.md)) reorganizado con índice, secciones temáticas y tabla de atajos.

## [0.10.39] - 2026-11-22

### Cambiado / Changed
- Documentación unificada en español e inglés y consolidación de la identidad de marca PDFiu.

## [0.10.38] - 2026-11-22

### Añadido / Added
- Primera publicación pública del código fuente de PDFiu.
