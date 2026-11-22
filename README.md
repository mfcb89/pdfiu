<img src="assets/brand/pdfiu-wordmark.svg" alt="PDFiu" width="220">

# PDFiu

**Español** · [English](README.en.md)

Lector y editor de PDF de código abierto creado por **mfcb89**. Abre, organiza, firma y convierte documentos desde una aplicación de escritorio. PDFiu procesa los PDF en tu equipo y no requiere una cuenta. La interfaz y la visita guiada están disponibles en español e inglés.

![PDFiu en español con el documento de bienvenida, miniaturas y herramientas](docs/pdfiu-es.png)

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

[Manual de usuario](LEEME.md) · [Guía de compilación](packaging/LEEME.md)

## Ejecutar desde el código

El repositorio público contiene el código fuente. La receta de instalador está pensada para Windows x64. El empaquetado de macOS se realiza en macOS y requiere validación en la arquitectura de destino.

1. Abre una terminal PowerShell con Git y Python 3.12 de 64 bits.
2. Clona el repositorio y ejecuta estos comandos.

```powershell
git clone https://github.com/mfcb89/pdfiu.git
cd pdfiu
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdfiu.py
```

Si ya tienes un clon abierto en un editor como Antigravity, empieza en la carpeta del repositorio. Para habilitar OCR, coloca `spa.traineddata` y `eng.traineddata` en `runtime/tessdata`. [Preparar los modelos de OCR](LEEME.md#preparar-los-modelos-de-ocr)

## Compatibilidad

- La edición de formularios usa AcroForm. Los formularios que dependen únicamente de XFA dinámico requieren un lector compatible con XFA.
- La firma básica admite archivos P12/PFX y, en Windows, certificados compatibles del almacén del sistema. El panel de firmas muestra los datos disponibles del certificado. La confianza de la cadena, el sellado de tiempo y la validación de larga duración quedan fuera de esta versión.
- Word reconstruye el diseño de forma aproximada. Los planos complejos, las columnas y las páginas escaneadas pueden requerir ajustes.
- PDF/A requiere Ghostscript, veraPDF y Java. La censura rasteriza las páginas marcadas y ofrece OCR para recuperar el texto visible. [Detalles de uso](LEEME.md)

## Contribuir y licencia

Abre una [incidencia](https://github.com/mfcb89/pdfiu/issues) o envía una propuesta de cambios. Puedes escribir en español o en inglés. [Guía de contribución](CONTRIBUTING.md)

El código y el logotipo originales de PDFiu se distribuyen bajo la [licencia MIT](LICENSE). Puedes usar, modificar y redistribuir el código, incluso comercialmente, si conservas el aviso de copyright y la licencia. Las bibliotecas y los recursos de terceros mantienen sus propios términos. Consulta los [avisos de terceros](THIRD_PARTY_NOTICES.md) antes de redistribuir un instalador.
