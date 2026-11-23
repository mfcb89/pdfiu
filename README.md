<img src="assets/brand/pdfiu-wordmark.svg" alt="PDFiu" width="220">

# PDFiu

**Español** · [English](README.en.md)

![Versión 0.12.0](https://img.shields.io/badge/version-0.12.0-2f7d6d?style=flat-square)
![Licencia MIT](https://img.shields.io/badge/license-MIT-182a3d?style=flat-square)
![Windows x64](https://img.shields.io/badge/Windows-x64-294459?style=flat-square)
![100% local](https://img.shields.io/badge/privacidad-100%25%20local%20%C2%B7%20sin%20cuenta-317f72?style=flat-square)

Lector y editor de PDF de código abierto creado por **mfcb89**, pensado como alternativa ligera y 100% local a los lectores propietarios pesados. Abre, organiza, edita, firma, mide planos y convierte documentos desde una aplicación de escritorio sin cuentas, sin nube y sin telemetría. La interfaz (con tema claro y oscuro) y la visita guiada están disponibles en español e inglés.

![PDFiu en español con el documento de bienvenida, miniaturas y herramientas](docs/pdfiu-es.png)

## Por qué PDFiu

- **100% local y privado:** tus PDF se procesan únicamente en tu equipo. PDFiu no requiere cuenta ni realiza conexiones de red salvo que consultes actualizaciones manualmente o actives la comprobación opcional al iniciar.
- **Todo en una sola app ligera:** incluye funciones que suelen exigir licencias o suscripciones externas (unir y organizar páginas, editar texto, rellenar formularios, OCR en español e inglés, firma digital, censura, medición/comparación de planos y exportación a Word, Excel y Markdown).
- **Código abierto sostenible:** el código fuente es público bajo licencia MIT y puedes compilarlo gratis en tu equipo. El instalador oficial de pago para Windows financia el desarrollo, la firma de código y las actualizaciones.

## Qué puedes hacer

| Área | Funciones |
| --- | --- |
| Lectura | Desplazamiento continuo, zoom, pantalla completa, miniaturas, marcadores, capas, búsqueda con contexto, tildes opcionales y operadores. |
| Páginas y lotes | Mesa de trabajo para varios PDF, unión con índice, extracción, inserción arrastrando, reordenación, giro y varias páginas por hoja. |
| Edición y revisión | Editar texto compatible, rellenar formularios AcroForm, añadir notas, resaltados, formas, encabezados, pies y números de página. |
| Certificados y protección | Firmar con recuadro visible, firmar varias páginas y documentos, consultar los datos de las firmas, proteger copias y censurar zonas. |
| Planos | Comparar en paralelo, superponer o ver diferencias. Calibrar una distancia o escala y medir longitudes, perímetros y superficies. |
| OCR y exportación | Reconocer español e inglés en una página o en todo el PDF. Exportar a Word, Excel, CSV, Markdown con vista previa, TXT o PNG. Copiar una página como imagen. |
| Impresión y salida | Vista previa, tamaño real, ajuste, mosaico, folleto, compresión con estimación y exportación PDF/A con herramientas externas. |

[Manual de usuario](LEEME.md) · [Guía de compilación](packaging/LEEME.md) · [Historial de cambios](CHANGELOG.md)

## Obtener PDFiu

### Instalador oficial (Windows x64)

El instalador oficial listo para usar (sin necesidad de instalar Python ni configurar dependencias) estará disponible en la página oficial de descargas y financia el desarrollo continuo, la firma de código y el canal de actualizaciones.

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
