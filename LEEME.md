# Manual de PDFiu

**Español** · [English](USER_GUIDE.en.md) · [Inicio](README.md)

Guía práctica de uso de **PDFiu**. Todas las operaciones se ejecutan en tu equipo sin cuentas ni nube.

## Índice

- [Primeros pasos y preferencias](#primeros-pasos-y-preferencias)
- [Lectura, navegación y búsqueda](#lectura-navegación-y-búsqueda)
- [Mesa de trabajo, ventanas y páginas](#mesa-de-trabajo-ventanas-y-páginas)
- [Edición, formularios y anotaciones](#edición-formularios-y-anotaciones)
- [Planos y mediciones](#planos-y-mediciones)
- [Firmas digitales, protección y censura](#firmas-digitales-protección-y-censura)
- [Exportar, imprimir, comprimir y PDF/A](#exportar-imprimir-comprimir-y-pdfa)
- [Preparar los modelos de OCR](#preparar-los-modelos-de-ocr)

---

## Primeros pasos y preferencias

- **Arranque y visita guiada.** En el primer inicio, **Ver bienvenida** abre el documento de ejemplo y te guía paso a paso para abrir un anexo, unir ambos archivos y guardar el resultado. Puedes repetirla desde **Ayuda → Visita guiada…** o recorrer doce funciones clave en **Ayuda → Guía de herramientas…**. Deja el ratón sobre cualquier herramienta para leer su explicación.
- **Ejecutar desde el código fuente.** Prepara el entorno indicado en el [README](README.md#ejecutar-gratis-desde-el-código-fuente) y abre `Iniciar PDFiu.cmd`. Puedes arrastrar un PDF sobre el lanzador o varios sobre la ventana.
- **Documentos recientes.** **Archivo → Documentos recientes** recuerda hasta diez PDF abiertos (también visibles al iniciar sin documento) y permite vaciar la lista.
- **Preferencias.** En **Edición → Preferencias** puedes configurar:
  - Ajuste inicial de zoom (**Ajustar página** o **Ajustar ancho**).
  - Recordar la última carpeta usada al abrir o guardar.
  - **Comprobar actualizaciones al iniciar** (desactivado por defecto; también puedes comprobar manualmente en **Ayuda → Buscar actualizaciones…**).
  - **Idioma de la interfaz** (idioma del sistema, Español o English; se aplica al reiniciar PDFiu).
  - **Favoritos:** crea tu panel personal desde la estrella **Favoritos → Personalizar…** o con clic derecho sobre cualquier herramienta.
- **Recuperación y cancelación.** Tras un cierre inesperado, PDFiu ofrece reabrir las copias locales con cambios pendientes para guardarlas con un nombre nuevo. Las operaciones largas muestran un botón **Cancelar**; en lotes, los archivos ya guardados permanecen en la carpeta de salida.
- **Actualizar el instalador de Windows.** Ejecuta el instalador nuevo: conserva la carpeta de instalación y tus preferencias. Si PDFiu está abierto, te permite guardar y cerrar antes de continuar.

---

## Lectura, navegación y búsqueda

- **Desplazamiento y zoom.** La rueda del ratón recorre las páginas en modo continuo. Usa **Ctrl + rueda**, indica un porcentaje o pulsa **Página** / **Ancho**. Con zoom ampliado, mantén pulsado **Espacio** y arrastra para moverte por la hoja, o usa el recuadro del **Navegador** en la izquierda.
- **Paneles y modo lectura.** El lateral izquierdo da acceso a **Archivos**, **Páginas**, **Marcadores**, **Capas**, **Anotaciones** y **Firmas**. En ventanas estrechas el panel de herramientas se recoge automáticamente. Pulsa **F9** (**Enfocar documento**) para ocultar paneles o **F11** (**Pantalla completa**); sal con **Esc** o **F11**.
- **Múltiples vistas y creación rápida.** **Archivo → Abrir otra vista del PDF** abre una segunda ventana de lectura con su propia página y zoom. También puedes crear un PDF en blanco, desde imágenes ordenadas y giradas o desde una imagen del portapapeles, recargar con **Volver a la versión guardada** o usar **Preparar copia para compartir** para copiar el archivo al portapapeles.
- **Copiar texto e imágenes.** Arrastra sobre el texto y pulsa **Ctrl+C** (en escaneos, aplica OCR primero). **Copiar página** copia la hoja completa como imagen para pegarla en Word o correo; **Guardar PNG** la exporta como archivo.
- **Búsqueda y búsqueda avanzada.** Pulsa **Ctrl+F**, escribe y pulsa **Enter** (**F3** / **Mayús+F3** para saltar entre coincidencias). Marca **Distinguir tildes** para diferenciar `medicion` de `medición`. En **Búsqueda avanzada**, usa operadores en mayúsculas y comillas para frases exactas, por ejemplo `(plano OR croquis) AND NOT borrador` o `"health and safety"`. Selecciona un resultado y pulsa **Coincidencias de la página…** para elegir un fragmento concreto.

### Atajos principales

| Acción | Windows | macOS |
| --- | --- | --- |
| Abrir PDF | `Ctrl+O` | `⌘+O` |
| Nueva ventana | `Ctrl+N` | `⌘+N` |
| Guardar / Guardar como | `Ctrl+S` / `Ctrl+Mayús+S` | `⌘+S` / `⌘+Mayús+S` |
| Imprimir | `Ctrl+P` | `⌘+P` |
| Propiedades del documento | `Ctrl+D` | `⌘+I` |
| Buscar / Siguiente / Anterior | `Ctrl+F` / `F3` / `Mayús+F3` | `⌘+F` / `F3` / `Mayús+F3` |
| Paleta de comandos | `Ctrl+K` | `⌘+K` |
| Preferencias | `Ctrl+,` | `⌘+,` |
| Deshacer / Rehacer | `Ctrl+Z` / `Ctrl+Y` | `⌘+Z` / `⌘+Y` |
| Enfocar / Pantalla completa | `F9` / `F11` | `F9` / `F11` |
| Cerrar PDF | `Ctrl+W` | `⌘+W` |
| Desplazar con zoom | Mantener `Espacio` + arrastrar | Mantener `Espacio` + arrastrar |

---

## Mesa de trabajo, ventanas y páginas

- **Mesa de trabajo.** Abre o arrastra varios PDF a la ventana. Selecciona uno o varios en **Archivos** (con casillas, `Ctrl` o `Mayús`) para operar en lote; el panel derecho indica siempre a qué archivos afecta cada herramienta. Pulsa **Supr** para quitar documentos de la lista sin borrarlos del disco.
- **Unir PDFs.** Selecciona varios archivos y pulsa **Unir PDFs**. Ordena la lista y activa **Crear índice** para generar un marcador por archivo. El resultado reemplaza a los originales guardados; los que tengan cambios pendientes siguen abiertos.
- **Integración con Windows.** Con el instalador de Windows puedes elegir PDFiu como lector predeterminado para `.pdf` en **Configuración → Aplicaciones → Aplicaciones predeterminadas**. En el Explorador, selecciona varios PDF y haz clic derecho en **Combinar archivos con PDFiu** (en Windows 11, dentro de **Mostrar más opciones**).
- **Reordenar, girar, extraer e insertar páginas.** En **Páginas**, arrastra miniaturas para reordenar, gira o elimina páginas, o extrae rangos como `1,3-5`. También puedes soltar PDF del Explorador entre miniaturas para insertar sus páginas o arrastrar miniaturas entre dos ventanas de PDFiu (**Archivo → Nueva ventana** o **Mover PDF a otra ventana**). `Ctrl+Z` deshace la inserción.
- **Varias páginas por hoja.** En **Documento → Varias páginas por hoja…** elige 2, 4, 6, 9 o 16 páginas, una cuadrícula personalizada o todas en una hoja, en A4, A3 o Carta. La copia incluye el contenido de página (las anotaciones y campos interactivos permanecen en el original).
- **Procesos de expediente.** En **Documento → Proceso de expediente…** encadena OCR, numeración y paso al flujo de firma sobre varios archivos, y guarda los ajustes como receta reutilizable.

---

## Edición, formularios y anotaciones

- **Editar texto existente.** En **Editar → Editar texto**, haz clic en un bloque compatible y confirma con **Enter**. Conserva la fuente original cuando admite los caracteres nuevos; no redistribuye párrafos ni modifica texto dentro de imágenes escaneadas.
- **Añadir texto y anotaciones.** En **Anotar** puedes añadir texto libre, resaltar, escribir notas o dibujar rectángulos, óvalos, líneas y flechas con color, grosor, opacidad, trazo discontinuo o relleno suave. Desde el **Panel de anotaciones** puedes localizarlas, moverlas, redimensionarlas o eliminarlas. `Ctrl+Z` y `Ctrl+Y` deshacen y rehacen durante la sesión.
- **Formularios AcroForm.** Al abrir un formulario, los campos editables se resaltan en azul. Haz clic para escribir (`Enter` guarda campos de una línea, `Ctrl+Enter` los multilínea, `Esc` cancela). Usa **Resaltar campos** para ocultar el fondo o **Editar → Campos y respuestas** para listar, vaciar o fijar las respuestas. En formularios híbridos XFA/AcroForm, PDFiu ofrece trabajar sobre una copia AcroForm (conserva el original si el trámite exige XFA dinámico).
- **Encabezados, pies y numeración.** **Editar → Encabezados y pies** admite varias líneas, fuentes Helvetica/Times/Courier, negrita, cursiva, subrayado y variables de **Página**, **Total** y **Archivo** con vista previa (también en lote). Para numerar rápidamente, usa **Editar → Numerar páginas…**.

---

## Planos y mediciones

- **Comparar dos PDF.** En **Planos → Planos y revisiones → Comparar dos PDF** elige original y revisión:
  - **Diferencias:** destaca lo añadido en verde, lo quitado en rojo y los cambios de color en ámbar, atenuando lo común. Permite ajustar tolerancia y alineación en milímetros.
  - **En paralelo:** sincroniza desplazamiento, zoom y página.
  - **Superponer:** tiñe la revisión y vuelve transparente su fondo blanco.
- **Capas.** El panel **Capas** permite activar o desactivar las capas visibles del plano.
- **Calibrar y medir.** En **Planos → Medir plano**, calibra con dos puntos a distancia conocida o introduce una escala `1:N` para medir longitudes, perímetros y superficies.
- **Superficies guardadas.** En **Planos → Superficies → Nueva superficie**, marca los vértices y pulsa **Ctrl+Enter**. Cada medición se guarda como anotación PDF con relleno translúcido y queda listada en el panel para localizarla al reabrir el archivo.

---

## Firmas digitales, protección y censura

- **PDF firmados y protegidos.** Introduce la contraseña de apertura para leer el PDF y consultar sus firmas. Si desbloqueas o editas un PDF firmado, PDFiu avisa y crea una copia sin firmas; guárdala con otro nombre para conservar el original firmado.
- **Firmar con certificado.** Pulsa **Firmar con certificado** y dibuja el recuadro en la página. PDFiu lee los certificados RSA vigentes con clave privada y uso de firma del almacén de Windows y también admite archivos `.p12` / `.pfx`. Muestra titular, DNI/NIE/NIF (si figura), empresa, emisor y vigencia. La firma es PAdES básica con SHA-256. *(El sellado de tiempo y la validación de larga duración quedan fuera de esta versión).*
- **Varias firmas, varias páginas y lotes.** Puedes añadir firmas sucesivas en zonas libres (los campos existentes se marcan en naranja), firmar todas las páginas de un documento manteniendo la posición relativa, o firmar varios archivos en lote con **Firmar lote…** (Windows puede pedir el PIN más de una vez al crearse una firma por página).
- **Explorar firmas.** Cuando un PDF contiene firmas, una cinta superior y el panel **Firmas** muestran titular, DNI/NIE/NIF, empresa, emisor, algoritmo, vigencia, fecha declarada y cobertura. Esta lectura es informativa e independiente de la validación de confianza de la cadena.
- **Desbloquear y proteger.** **Proteger → Desbloquear PDF** retira restricciones de uso en una copia (`nombre_unlocked.pdf`). También puedes cifrar una copia con contraseña de apertura.
- **Censurar datos.** En **Proteger → Censurar datos**, marca las zonas a ocultar y pulsa **Guardar copia censurada**. Las páginas marcadas se convierten en imagen eliminando por completo el contenido oculto; el resto conserva texto y vectores. Puedes activar **Con texto seleccionable (OCR)** para recuperar el texto visible. La copia omite formularios, anotaciones, marcadores y adjuntos: revísala antes de compartirla.

---

## Exportar, imprimir, comprimir y PDF/A

- **Exportar documentos.** Desde **Archivo → Exportar**, elige todo el documento, la página actual o un rango (también en lote seleccionando varios PDF):
  - **Word (`.docx`):** *Con formato* reconstruye texto editable, fuentes, colores, imágenes y tablas de forma aproximada; *Texto y tablas básicos* permite aplicar OCR a páginas sin texto.
  - **Excel (`.xlsx`) y CSV:** extraen tablas (en escaneos, aplica OCR primero y activa la detección de columnas alineadas).
  - **Markdown (`.md`):** extrae párrafos y tablas con vista previa, OCR opcional y copia directa.
  - **TXT y PNG:** texto plano o una imagen por página.
- **Impresión.** Pulsa **Ctrl+P** para abrir la vista previa con aviso de recortes. Admite tamaño real, ajuste al papel, porcentaje, mosaico con solape para planos, varias páginas por hoja y folleto. En Windows, **Propiedades de la impresora…** abre el panel del fabricante sin cambiar la configuración global del sistema. **Guardar como PDF** desde el diálogo de impresión reproduce la salida como imagen.
- **Comprimir copia.** En **Documento → Comprimir copia…**, elige **Tamaño reducido · 150 ppp** o **Extremo · 96 ppp**, pulsa **Estimar tamaño** (muestrea hasta ocho páginas) y revisa el resultado con **Comparar al 100 %**. El texto y el dibujo vectorial se conservan.
- **PDF/A.** **Archivo → Guardar copia PDF/A** genera y valida PDF/A-1b, 2b o 3b usando **Ghostscript**, **veraPDF** (`greenfield-apps-*.jar`) y **Java** instalados por separado. Si vas a firmar el expediente, convierte y valida antes de firmar.

---

## Preparar los modelos de OCR

Con **Documento → Reconocer texto (OCR)** puedes añadir una capa de texto seleccionable en español, inglés o ambos sobre la página actual o todo el documento conservando el aspecto original. Guarda el PDF para conservar el resultado.

Si ejecutas PDFiu desde el código fuente (tras instalar las dependencias del [README](README.md#ejecutar-gratis-desde-el-código-fuente)), descarga los modelos desde PowerShell en la carpeta del proyecto:

```powershell
New-Item -ItemType Directory -Force -Path .\runtime\tessdata | Out-Null
foreach ($lang in @('spa', 'eng')) {
    Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/$lang.traineddata" -OutFile ".\runtime\tessdata\$lang.traineddata"
}
```

---

*Recetas de empaquetado para Windows y macOS en [packaging/LEEME.md](packaging/LEEME.md). Avisos de iconos y bibliotecas de terceros en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).*
