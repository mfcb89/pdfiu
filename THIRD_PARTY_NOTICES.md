# Avisos de terceros de PDFiu

La licencia MIT de PDFiu cubre el código y los recursos originales del proyecto. Cada dependencia y recurso de terceros conserva su licencia y sus titulares.

- Los iconos de interfaz proceden de Fluent UI System Icons (paquete SVG 1.1.347 de Microsoft), bajo licencia MIT. [Aviso de Fluent UI System Icons](assets/fluent/LICENSE)
- La fuente Bitstream Vera se incrusta en la apariencia de las firmas de PDF/A. [Licencia de Bitstream Vera](assets/fonts/bitstream-vera-license.txt)
- La vía prevista para Qt, PySide6 y Shiboken es la edición comunitaria de LGPLv3, donde corresponda. Qt se carga como bibliotecas separadas en el paquete. La LGPL permite modificar esas bibliotecas y realizar ingeniería inversa para depurar dichas modificaciones. [Texto oficial y obligaciones de Qt](https://www.qt.io/licensing/open-source-lgpl-obligations)
- El lector usa pypdfium2 y PDFium. Su directorio de licencias incluye avisos de PDFium y de los componentes que lleva incorporados. [Licencias de PDFium](https://github.com/pypdfium2-team/pypdfium2#licensing)
- El OCR usa Tesseract y traineddata en español e inglés. Los avisos de la rueda de tesserocr incluyen los de Tesseract y sus bibliotecas nativas. El inventario registra la huella de los modelos usados en cada compilación. [Modelos oficiales de OCR](https://github.com/tesseract-ocr/tessdata_fast)

Cada paquete compilado genera una carpeta `third-party` con las versiones, los textos recogidos de las dependencias y las incidencias que queden por verificar. En la compilación de prueba de Windows está en `_internal/third-party`.

Antes de ofrecer públicamente un binario, el distribuidor debe verificar las licencias de los archivos que realmente incluye, preparar el acceso al código fuente correspondiente cuando lo exija la licencia, y comprobar que es posible ejecutar PDFiu con bibliotecas modificadas compatibles. Un enlace a un proyecto sin identificar la versión y la configuración de compilación no sustituye esta verificación.
