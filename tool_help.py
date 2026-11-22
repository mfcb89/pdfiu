"""Short descriptions shown when hovering over PDFiu controls."""

from translations import tr


TOOL_HINTS = {
    'Abrir': 'Abre uno o varios PDF y los añade a Archivos. Ctrl+O.',
    'Guardar': 'Guarda los cambios del documento actual. Ctrl+S.',
    'Guardar como…': 'Guarda el documento con otro nombre o en otra carpeta.',
    'Buscar': 'Busca texto en todo el PDF y muestra coincidencias con contexto. Pulsa un resultado para ir a su página. Ctrl+F.',
    'Buscar texto': 'Busca texto en todo el PDF y muestra coincidencias con contexto. Ctrl+F.',
    'Unir PDFs': 'Selecciona varios PDF en Archivos, revisa su orden y crea un documento combinado.',
    'Exportar': 'Convierte el PDF a Word, Excel, Markdown o imágenes. También puedes copiar una página como imagen.',
    'Reconocer texto (OCR)': 'Reconoce el texto de páginas escaneadas para poder buscarlo y seleccionarlo.',
    'Extraer páginas…': 'Elige un intervalo de páginas y guárdalo en un PDF independiente.',
    'Extraer página…': 'Guarda la página actual en un PDF independiente.',
    'Insertar PDF…': 'Añade las páginas de otro PDF. También puedes soltar un archivo entre las miniaturas.',
    'Comprimir copia…': 'Elige un perfil y estima el tamaño antes de comprimir. Revisa la copia y guárdala.',
    'Desbloquear PDF': 'Crea una copia editable del PDF abierto. Si tiene contraseña de apertura, necesitarás conocerla.',
    'Firmar con certificado': 'Dibuja el recuadro de firma y elige un certificado digital. Con varios PDF marcados, configura la firma en lote.',
    'Firmar lote…': 'Firma varios PDF con certificado y configura la posición y las páginas de la firma.',
    'Explorar firmas': 'Consulta los certificados disponibles y los datos de sus titulares y su validez.',
    'Añadir texto': 'Pulsa en la página para escribir un texto nuevo.',
    'Editar texto': 'Pulsa sobre un bloque de texto del PDF para modificarlo.',
    'Rellenar formulario': 'Activa los campos editables del PDF y pulsa sobre ellos para rellenarlos.',
    'Campos y respuestas': 'Consulta los campos, vacía el formulario o fija sus respuestas en la página.',
    'Encabezados y pies': 'Añade texto arriba o abajo de las páginas y elige fuente, posición e intervalo.',
    'Numerar páginas…': 'Añade números de página y elige el inicio, la posición y las páginas donde aparecen.',
    'Subrayar selección': 'Selecciona texto y pulsa aquí para subrayarlo.',
    'Resaltar selección': 'Selecciona texto en la página y pulsa aquí para resaltarlo.',
    'Añadir nota': 'Añade una nota de revisión al PDF. También admite varios archivos seleccionados.',
    'Formas': 'Elige un rectángulo, óvalo, línea o flecha y dibújalo en la página.',
    'Panel de anotaciones': 'Muestra las notas y formas del documento para localizarlas, editarlas o eliminarlas.',
    'Censurar datos': 'Marca las zonas que quieres eliminar y después guarda una copia censurada.',
    'Poner contraseña…': 'Protege una copia del PDF con una contraseña.',
    'Medir plano': 'Calibra con dos puntos y una distancia real, o introduce la escala. Después mide distancias, perímetros y áreas.',
    'Superficies': 'Consulta las áreas dibujadas en el plano, sus colores y sus medidas.',
    'Planos y revisiones': 'Compara documentos y consulta las capas y los datos del PDF.',
    'Varias páginas por hoja…': 'Distribuye varias páginas del PDF en una misma hoja.',
    'Proceso de expediente…': 'Configura un proceso de OCR, numeración y firma para tus documentos.',
    'Personalizar…': 'Elige las herramientas que quieres tener a mano en Favoritos.',
    'Documento': 'Unir, exportar, extraer, reconocer texto y comprimir PDF.',
    'Editar': 'Editar o añadir texto, rellenar formularios y añadir encabezados y números.',
    'Anotar': 'Resaltar texto, añadir notas y dibujar formas.',
    'Firmar': 'Firmar con certificado y consultar los certificados disponibles.',
    'Planos': 'Medir distancias y áreas, comparar PDF y consultar capas.',
    'Proteger': 'Desbloquear, proteger con contraseña y censurar datos.',
    'Favoritos': 'Accede a tus herramientas habituales. Pulsa Personalizar para elegirlas.',
    'Girar': 'Gira la página actual un cuarto de vuelta.',
}


def tool_hint(label):
    for source, description in TOOL_HINTS.items():
        if label in (source, tr(source)):
            return tr(description)
    return label
