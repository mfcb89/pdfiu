# PDFiu

Lector y editor local de PDF creado por **mfcb89**. Permite unir documentos, editar y anotar, buscar texto, firmar con certificado, aplicar OCR y comprimir copias. [Manual de PDFiu](LEEME.md)

El código y los recursos originales de PDFiu se publican bajo la [licencia MIT](LICENSE). Puedes usarlos, modificarlos y redistribuirlos conservando el aviso de licencia. Las bibliotecas y los recursos de terceros conservan sus propias condiciones. [Avisos de terceros](THIRD_PARTY_NOTICES.md)

Para ejecutar PDFiu desde el código, abre una terminal en la carpeta del proyecto y usa Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe folio.py
```

Para usar OCR, coloca `spa.traineddata` y `eng.traineddata` en `runtime/tessdata`. La receta de empaquetado explica cómo preparar un paquete de Windows o macOS. [Instrucciones de compilación](packaging/LEEME.md)
