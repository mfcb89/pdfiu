# Historial de cambios / Changelog

Todos los cambios relevantes de PDFiu se documentan en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa versionado semántico (`MAJOR.MINOR.PATCH`).

## [Sin publicar] / [Unreleased]

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
