from pathlib import Path
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from contextlib import ExitStack
from dataclasses import dataclass, field as dataclass_field, replace
from html import escape
from math import ceil, floor
from shutil import copyfile
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
import base64
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get("PDFIU_RUNTIME", ROOT / "runtime"))
WINDOWS_BUNDLE = sys.platform == "win32" and getattr(sys, "frozen", False)
if (RUNTIME / "deps").is_dir():
    sys.path.insert(0, str(RUNTIME / "deps"))

from PySide6.QtCore import QEasingCurve, QEvent, QItemSelectionModel, QLocale, QMimeData, QPoint, QPointF, QPropertyAnimation, QRectF, QSettings, QSignalBlocker, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QDrag, QIcon, QImage, QKeySequence, QPageSize, QPainterPath, QPen, QPixmap, QTextDocument, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTabBar, QTabWidget, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from pdf_ops import (
    Coordinates, OperationCancelled, ProtectedPdf, add_batch_note, add_header_footer, add_review_annotation, add_shape, add_signature_stamp, add_surface_annotation, add_text, atomic_output, blank_pdf,
    change_annotation_box, clear_form, compress_copy, convert_hybrid_form, document_text, edit_pages, estimate_compression, fill_form, flatten_form, form_fields,
    has_signed_fields, has_xfa, images_to_pdf, insert_pages,
    merge, ocr_document, page_range, page_text, pages_per_sheet, pdf_has_signatures, pdfium_reader, project_signature_box, protect_copy, reader_for,
    redact_copy, redact_searchable_copy, remove_review_annotation, render_page, render_page_tile, replace_text_block, review_annotations, search_advanced_document,
    signature_boxes, signature_plan, signature_value, signature_widgets, split_pdf, surface_records, text_block_at, unlock_pdf,
    validate_signature_box, workspace_batch_copies,
)
from pdfiu_ui import ANNOTATION_CARD_ROLE, AnimatedStackedWidget, HeaderEditor, PageNavigator, PanelRail, SEARCH_EXCERPT_ROLE, STYLE, SearchResultDelegate, SlidingCategoryPanel, TourSpotlight, apply_theme, brand_icon, brand_pixmap, icon, signature_details_html, startup_screen, text_line_boxes
from plan_tools import inspect_document, layer_list, layer_preview, measured_value, prepare_recipe
from release_info import APP_NAME, APP_VERSION, STORE_PROTOCOL_URL, is_store_package, latest_release, update_channel
from document_export import export_document, markdown_from_pdf
from translations import current_language, initialize_language, tr
from tool_help import tool_hint
from search_query import SearchQuery, SearchSyntaxError
from session_recovery import RecoveryJournal, interrupted_sessions, retain_unrecovered
from pdf_print import document_sizes, print_pages
from pdf_print_dialog import PrintDialog
from pdf_archive import PROFILES, archive_tools, export_archive
from app_logging import log_directory, setup_logging
from pdfiu_views import (
    BookmarkRows, ContinuousPageView, DocumentTabBar, Job, MEASURE_UNITS, PageCalibration, PageList, PageView,
    SEARCH_PAGE_COUNT_ROLE, WorkDocument, WorkspaceList, action_menu, as_qimage, button,
    check_cancellation, file_size_label, icon_button, search_result_item,
)
from pdfiu_dialogs import (
    BatchDialog, CertificateDialog, CommandPaletteDialog, CompressDialog, CompressionPreview, MergeDialog,
    OrganizePagesDialog, RevisionComparison, ShortcutsDialog, SplitDialog, VisualSignatureDialog,
)


class PDFiu(QMainWindow):
    secondary_windows = set()
    compact_width = 1050

    def __init__(self, *, show_startup=False):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 830)
        self.setMinimumSize(870, 560)
        self.setAcceptDrops(True)
        if WINDOWS_BUNDLE:
            local_data = Path(os.environ["LOCALAPPDATA"])
            data = local_data / APP_NAME
            scratch = data / "sesiones"
            scratch.mkdir(parents=True, exist_ok=True)
            self.temp = TemporaryDirectory(dir=scratch, prefix="pdfiu-", ignore_cleanup_errors=True)
            preferences_file = data / "preferencias.ini"
            self.preferences = QSettings(str(preferences_file), QSettings.Format.IniFormat)
            legacy = local_data / "Folio PDF" / "preferencias.ini"
            if not preferences_file.exists() and legacy.is_file():
                old_preferences = QSettings(str(legacy), QSettings.Format.IniFormat)
                for key in old_preferences.allKeys():
                    self.preferences.setValue(key, old_preferences.value(key))
                self.preferences.sync()
        else:
            self.temp = TemporaryDirectory(prefix="pdfiu-", ignore_cleanup_errors=True)
            self.preferences = QSettings(
                QSettings.Format.IniFormat, QSettings.Scope.UserScope, APP_NAME, APP_NAME
            )
            if not Path(self.preferences.fileName()).is_file():
                old_preferences = QSettings(
                    QSettings.Format.IniFormat, QSettings.Scope.UserScope, "Folio PDF", "Folio PDF"
                )
                for key in old_preferences.allKeys():
                    self.preferences.setValue(key, old_preferences.value(key))
                self.preferences.sync()
        self.scratch = Path(self.temp.name)
        self.document_views = {}
        self.recovery = RecoveryJournal(self.scratch)
        initialize_language(self.preferences.value("idioma/interfaz", "system"))
        self.startup = None
        if show_startup:
            self.startup = startup_screen(tr("Proyecto libre creado por mfcb89"))
            self.startup.show()
            QApplication.processEvents()
        self.path = None
        self.saved_path = None
        self.protected_source = None
        self.document_password = None
        self.name = ""
        self.dirty = False
        self.count = 0
        self.current = 0
        self.coordinates = None
        self.job = None
        self.update_job = None
        self.search_job = False
        self.search_pending = None
        self.search_result_key = None
        self.search_hits = []
        self.search_cursor = -1
        self.actions = []
        self.tour_step = 0
        self.tour_paths = ()
        self.tour_result_key = None
        self.tour_destination = None
        self.tool_tour_index = None
        self.tool_tour_target = None
        self.redaction_boxes = {}
        self.work_docs = {}
        self.work_key = None
        self.form_kind = None
        self.current_fields = []
        self.measure_points = []
        self.pending_measure = None
        self.calibrations = {}
        self.annotation_edit = None
        self.undo_versions = {}
        self.redo_versions = {}
        saved_favorites = self.preferences.value("herramientas/favoritas", [])
        self.favorite_names = [saved_favorites] if isinstance(saved_favorites, str) else list(saved_favorites or [])
        self.favorite_names = ["Exportar" if name == "Exportar imagen" else name for name in self.favorite_names]

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        self.tools_requested = True
        self.tools_compact_open = False
        self.navigation_requested = True
        bar = QFrame(objectName="shellBar")
        self.shell_bar = bar
        self.fullscreen_state = None
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 9, 16, 9)
        row.setSpacing(9)
        logo = QLabel(objectName="brandIcon")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(brand_icon().pixmap(34, 34))
        row.addWidget(logo)
        row.addWidget(QLabel(APP_NAME, objectName="brand"))
        row.addSpacing(6)
        self.open_btn = button("Abrir", self.open_dialog, glyph="folder-plus")
        self.undo_btn = icon_button(tr("Deshacer (Ctrl+Z)"), "chevron-left", self.undo_edit)
        self.redo_btn = icon_button(tr("Rehacer (Ctrl+Y)"), "chevron-right", self.redo_edit)
        self.search_btn = button("Buscar", self.open_search, glyph="search")
        self.merge_btn = button("Unir PDFs", self.merge_dialog, glyph="combine")
        self.unlock_btn = button("Desbloquear PDF", self.unlock_dialog, glyph="unlock-open")
        self.save_btn = button("Guardar", self.save, primary=True, glyph="save")
        self.save_copy_btn = button("Guardar como…", lambda: self.save(as_copy=True))
        self.close_pdf_btn = icon_button(tr("Cerrar PDF (Ctrl+W)"), "close", self.close_work_document)
        self.name_label = QLabel("", objectName="fileTitle")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.installEventFilter(self)
        self.file_state = QLabel(tr("Sin guardar"), objectName="fileState")
        self.file_state.hide()
        row.addWidget(self.name_label, 1)
        row.addWidget(self.file_state)
        row.addWidget(self.undo_btn)
        row.addWidget(self.redo_btn)
        row.addWidget(self.search_btn)
        row.addWidget(self.open_btn)
        row.addWidget(self.save_btn)
        row.addWidget(self.save_copy_btn)
        row.addWidget(self.close_pdf_btn)
        divider = QFrame(objectName="toolbarDivider")
        divider.setFixedSize(1, 23)
        row.addWidget(divider)
        self.navigation_toggle = icon_button(tr("Mostrar u ocultar Archivos y Páginas"), "checkbox-list", self.toggle_navigation)
        self.navigation_toggle.setCheckable(True)
        self.navigation_toggle.setChecked(True)
        row.addWidget(self.navigation_toggle)
        self.tool_toggle = button("Herramientas", self.toggle_tool_panel, glyph="view-columns")
        self.tool_toggle.setToolTip(tr("Mostrar u ocultar herramientas"))
        self.tool_toggle.setCheckable(True)
        self.tool_toggle.setChecked(True)
        row.addWidget(self.tool_toggle)
        self.focus_toggle = button("Enfocar", self.toggle_focus, glyph="maximize")
        self.focus_toggle.setToolTip(tr("Enfocar documento (F9)"))
        self.focus_toggle.setCheckable(True)
        self.focus_layout = None
        layout.addWidget(bar)

        tools = QFrame(objectName="toolPanel")
        self.tools = tools
        tools.setMinimumWidth(0)
        tools.setMaximumWidth(260)
        self._tool_panel_width = 260
        self._tool_panel_anim = None
        tool_layout = QVBoxLayout(tools)
        tool_layout.setContentsMargins(14, 15, 14, 12)
        tool_layout.setSpacing(9)
        tool_header = QHBoxLayout()
        tool_header.setContentsMargins(0, 0, 0, 0)
        tool_header.addWidget(QLabel(tr("Herramientas"), objectName="toolHeading"), 1)
        self.quick_search_btn = button("Ctrl+K", self.open_command_palette, glyph="search")
        self.quick_search_btn.setObjectName("quickSearchBtn")
        self.quick_search_btn.setToolTip(tr("Buscar herramienta rápidamente (Ctrl+K)"))
        tool_header.addWidget(self.quick_search_btn)
        tool_layout.addLayout(tool_header)
        category_panel = SlidingCategoryPanel(objectName="toolCategories")
        self.category_panel = category_panel
        categories = QGridLayout(category_panel)
        categories.setContentsMargins(5, 5, 5, 5)
        categories.setSpacing(4)
        tool_layout.addWidget(category_panel)
        self.tool_group = QButtonGroup(self)
        self.tool_group.idClicked.connect(self.show_tool_group)
        self.tool_scope = QLabel(objectName="toolScope")
        self.tool_scope.setWordWrap(True)
        self.tool_scope.setTextFormat(Qt.TextFormat.PlainText)
        self.tool_scope.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.tool_scope.hide()
        tool_layout.addWidget(self.tool_scope)
        self.tool_pages = AnimatedStackedWidget()
        tool_layout.addWidget(self.tool_pages, 1)
        self.sign_btn = button("Firmar con certificado",
                               lambda: self.sign_workspace() if self.batch_selection_count() else self.select_mode("signature"),
                               glyph="sign")
        self.visual_sign_btn = button("Firma visual (imagen/PDF)…", self.start_visual_signature, glyph="edit-pen-2")
        self.pending_stamp = None
        self.batch_btn = button("Firmar lote…", self.batch_dialog, glyph="batch-sign")
        self.text_btn = button("Añadir texto", lambda: self.select_mode("text"), glyph="textbox")
        self.text_btn.setCheckable(True)
        self.edit_text_btn = button("Editar texto", lambda: self.select_mode("edit-text"), glyph="edit-pen-2")
        self.edit_text_btn.setCheckable(True)
        self.form_btn = button("Rellenar formulario", self.start_form, glyph="checkbox-list")
        self.form_btn.setCheckable(True)
        forms = action_menu("Campos y respuestas", (
            (tr("Campos de esta página…"), self.list_form_fields),
            (tr("Vaciar formulario…"), lambda: self.finalize_form(False)),
            (tr("Fijar respuestas en el PDF…"), lambda: self.finalize_form(True)),
        ), "checkbox-list")
        headers = button("Encabezados y pies", self.header_footer, glyph="headers")
        redact = action_menu("Censurar datos", (
            (tr("Marcar zonas para censurar"), self.start_redaction),
            (tr("Quitar marcas de esta página"), self.clear_redaction_page),
            (tr("Guardar copia censurada…"), self.save_redaction),
        ), "redact")
        shapes = action_menu("Formas", tuple(
            (label, lambda kind=kind: self.select_mode(f"shape-{kind}"))
            for label, kind in ((tr("Rectángulo"), "rectangle"), (tr("Óvalo"), "ellipse"),
                                (tr("Línea"), "line"), (tr("Flecha"), "arrow"))
        ), "shapes")
        measurements = action_menu("Medir plano", (
            (tr("Calibrar con dos puntos…"), self.begin_calibration),
            (tr("Introducir escala 1:N…"), self.enter_page_scale),
            (tr("Distancia"), lambda: self.start_measure("distance")),
            (tr("Perímetro"), lambda: self.start_measure("perimeter")),
            (tr("Superficie"), lambda: self.start_measure("area")),
            (tr("Crear superficie en el PDF"), lambda: self.start_measure("surface")),
            (tr("Ver superficies"), self.open_surfaces),
            (tr("Terminar medición"), self.finish_measure),
        ), "measure")
        plan_menu = action_menu("Planos y revisiones", (
            (tr("Comparar dos PDF…"), self.compare_documents),
            (tr("Capas del documento…"), self.show_layers),
            (tr("Inspeccionar el PDF…"), self.inspect_pdf),
        ), "document")
        self.shape_color = QComboBox()
        for label, color in ((tr("Azul"), "#3569aa"), (tr("Rojo"), "#aa443e"), (tr("Verde"), "#458061"), (tr("Negro"), "#282825")):
            self.shape_color.addItem(label, color)
        self.shape_color.setAccessibleName(tr("Color de las formas"))
        self.shape_color.setToolTip(tr("Color de las anotaciones con formas"))
        self.shape_color.currentIndexChanged.connect(self.update_shape_color)
        self.ocr_btn = button("Reconocer texto (OCR)", self.run_ocr, glyph="scanner")
        export_tool = action_menu("Exportar", self.export_actions(), "export")
        export_tool.menu().insertSeparator(export_tool.menu().actions()[5])
        export_tool.menu().aboutToShow.connect(lambda: self.update_export_menu(export_tool.menu()))
        more_doc_tools = action_menu("Más herramientas", (
            (tr("Extraer páginas…"), self.extract_range),
            (tr("Varias páginas por hoja…"), self.sheet_layout_dialog),
            (tr("Proceso de expediente…"), self.start_recipe),
        ), "document")
        numbering = button("Numerar páginas…", lambda: self.header_footer(numbering=True), glyph="numbering")
        note_tool = button("Añadir nota", lambda: self.note_workspace() if self.batch_selection_count() else self.start_note(),
                           glyph="add-note")
        self.batch_tools = {self.merge_btn, self.ocr_btn, self.unlock_btn, self.sign_btn, headers,
                            numbering, note_tool, export_tool, more_doc_tools}
        self.signature_explorer_btn = button("Explorar firmas", self.signature_explorer, glyph="document-award")
        self.pan_btn = button("Desplazar página", lambda: self.select_mode("pan"), glyph="hand")
        self.pan_btn.setCheckable(True)
        self.pan_btn.setToolTip(tr("Arrastra para desplazar la página cuando está ampliada"))
        groups = (
            (tr("Documento"), "document", (
                button("Organizar páginas…", self.organize_pages_grid, glyph="view-columns"),
                self.merge_btn,
                button("Dividir PDF…", self.split_current_pdf, glyph="extract"),
                button("Comprimir PDF…", self.compress_pdf, glyph="compress"),
                export_tool,
                self.ocr_btn,
                more_doc_tools,
            )),
            (tr("Editar"), "edit-pen-2", (self.edit_text_btn, self.text_btn, self.form_btn, forms, headers, numbering)),
            (tr("Anotar"), "chat-2-text", (button("Resaltar selección", self.highlight_selection, glyph="highlight"),
                        button("Subrayar selección", lambda: self.highlight_selection(underline=True), glyph="underline"),
                        note_tool, shapes, self.shape_controls(),
                        button("Panel de anotaciones", self.open_comments, glyph="chat-2-text"))),
            (tr("Firmar"), "document-award", (self.sign_btn, self.visual_sign_btn, self.batch_btn, self.signature_explorer_btn)),
            (tr("Planos"), "view-columns", (measurements, button("Superficies", self.open_surfaces, glyph="view-columns"), plan_menu)),
            (tr("Proteger"), "key", (
                self.unlock_btn,
                button("Poner contraseña…", self.protect_pdf, glyph="lock"),
                redact,
                button("Preparar copia para compartir…", self.share_pdf_copy, glyph="export"),
            )),
        )
        self.tool_library = [(label, widget) for label, _, widgets in groups for widget in widgets
                             if isinstance(widget, QPushButton)]
        self.favorite_controls = {}
        def add_category(index, label, glyph):
            category = button(label, lambda: None, glyph=glyph)
            category.setProperty("role", "category")
            category.setCheckable(True)
            category.setChecked(index == 0)
            self.tool_group.addButton(category, index)
            categories.addWidget(category, index // 2, index % 2, 1, 2 if index == len(groups) else 1)

        for index, (label, glyph, widgets) in enumerate(groups):
            add_category(index, label, glyph)
            tool_row = QWidget(objectName="toolRow")
            row = QVBoxLayout(tool_row)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(3)
            for widget in widgets:
                if isinstance(widget, QPushButton):
                    widget.setProperty("role", "tool")
                row.addWidget(widget)
            row.addStretch(1)
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(tool_row)
            scroll.verticalScrollBar().valueChanged.connect(self.schedule_tour_highlight)
            self.tool_pages.addWidget(scroll)
        for _, widget in self.tool_library:
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda point, tool=widget: self.tool_context(tool, point))
        self.favorite_pane = QWidget(objectName="toolRow")
        favorites = QVBoxLayout(self.favorite_pane)
        favorites.setContentsMargins(0, 0, 0, 0)
        favorites.setSpacing(6)
        favorites.addWidget(button("Personalizar…", self.choose_favorites, glyph="star"))
        favorite_scroll = QScrollArea()
        favorite_scroll.setFrameShape(QFrame.Shape.NoFrame)
        favorite_scroll.setWidgetResizable(True)
        favorite_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        favorite_list = QWidget(objectName="toolRow")
        self.favorite_rows = QVBoxLayout(favorite_list)
        self.favorite_rows.setContentsMargins(0, 0, 0, 0)
        self.favorite_rows.setSpacing(3)
        favorite_scroll.setWidget(favorite_list)
        favorites.addWidget(favorite_scroll, 1)
        self.tool_pages.addWidget(self.favorite_pane)
        add_category(len(groups), tr("Favoritos"), "star")
        self.category_panel.move_to(self.tool_group.button(0), animate=False)
        self.refresh_favorites()

        self.form_strip = QFrame(objectName="formStrip")
        form_row = QHBoxLayout(self.form_strip)
        form_row.setContentsMargins(16, 4, 16, 4)
        self.form_label = QLabel()
        self.form_label.setWordWrap(True)
        form_row.addWidget(self.form_label, 1)
        self.tint_btn = QPushButton(tr("Resaltar campos"))
        self.tint_btn.setCheckable(True)
        self.tint_btn.setChecked(True)
        self.tint_btn.toggled.connect(self.refresh_field_tint)
        form_row.addWidget(self.tint_btn)
        self.form_strip.hide()

        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame(objectName="sidebar")
        self.navigation = QTabWidget()
        self.navigation.setObjectName("workspaceNavigation")
        self.navigation.tabBar().setUsesScrollButtons(False)
        self.navigation.tabBar().setExpanding(False)
        self.navigation.tabBar().hide()
        self.navigation.setMinimumWidth(220)
        self.pages_panel = sidebar
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(11, 13, 11, 12)
        page_header = QHBoxLayout()
        page_header.addWidget(QLabel(tr("Miniaturas"), objectName="panelLabel"), 1)
        page_header.addWidget(icon_button(tr("Cerrar panel"), "close", lambda: self.set_navigation(False, animate=True)))
        column.addLayout(page_header)
        self.pages = PageList(self)
        self.pages.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pages.setUniformItemSizes(True)
        self.pages.setIconSize(QSize(52, 60))
        self.pages.currentRowChanged.connect(self.goto)
        self.thumbnail_timer = QTimer(self, singleShot=True, interval=45)
        self.thumbnail_cache = OrderedDict()
        self.thumbnail_timer.timeout.connect(self.render_visible_thumbnails)
        self.pages.verticalScrollBar().valueChanged.connect(self.schedule_thumbnails)
        self.thumbnail_viewport = self.pages.viewport()
        self.thumbnail_viewport.installEventFilter(self)
        self.navigation.currentChanged.connect(self.schedule_thumbnails)
        column.addWidget(self.pages, 1)
        page_actions = QHBoxLayout()
        self.rotate_btn = button("Girar", self.rotate_page, glyph="reload-circle")
        self.remove_btn = icon_button(tr("Quitar página"), "delete-bin", self.remove_page)
        page_actions.addWidget(self.rotate_btn)
        page_actions.addWidget(self.remove_btn)
        column.addLayout(page_actions)
        self.extract_btn = button("Extraer página…", self.extract_page, glyph="extract")
        column.addWidget(self.extract_btn)
        self.insert_btn = button("Insertar PDF…", self.select_pdfs_to_insert, glyph="file-plus")
        column.addWidget(self.insert_btn)
        self.navigation.addTab(sidebar, tr("Páginas"))
        self.view = ContinuousPageView()
        self.selection_tools = QFrame(self.view.viewport(), objectName="tourStrip")
        selection_row = QHBoxLayout(self.selection_tools)
        selection_row.setContentsMargins(4, 4, 4, 4)
        selection_row.setSpacing(4)
        selection_row.addWidget(button("Copiar", self.view.copy_text))
        selection_row.addWidget(button("Resaltar", self.highlight_selection))
        selection_row.addWidget(button("Subrayar", lambda: self.highlight_selection(underline=True)))
        self.selection_tools.hide()
        self.view.selection_finished.connect(self.show_selection_actions)
        self.view.text_selection_changed.connect(lambda selected: self.selection_tools.hide() if not selected else None)
        self.view.context_menu_requested.connect(self.show_view_context_menu)
        self.navigation_column = QWidget(objectName="navigationPanel")
        self.navigation_column.setMinimumWidth(220)
        self.navigation_column.setMaximumWidth(640)
        self._nav_last_width = 260
        self._nav_anim = None
        self._rail_anim = None
        self._nav_fade_anim = None
        navigation_layout = QVBoxLayout(self.navigation_column)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(0)
        self.navigator_panel = QFrame(objectName="navigationOverview")
        overview = QVBoxLayout(self.navigator_panel)
        overview.setContentsMargins(10, 8, 10, 8)
        overview.setSpacing(5)
        self.navigator_label = QLabel(objectName="panelLabel")
        overview.addWidget(self.navigator_label)
        self.navigator = PageNavigator()
        self.navigator.center_requested.connect(self.center_from_navigator)
        overview.addWidget(self.navigator)
        navigation_layout.addWidget(self.navigator_panel)
        navigation_layout.addWidget(self.navigation, 1)
        self.navigator_panel.hide()
        self.navigation_rail = PanelRail(objectName="navigationRail")
        self.navigation_rail.setFixedWidth(46)
        self.navigation_shell = self.navigation_rail
        self.rail_layout = QVBoxLayout(self.navigation_rail)
        self.rail_layout.setContentsMargins(0, 8, 1, 6)
        self.rail_layout.setSpacing(4)
        rail_scroll = QScrollArea(objectName="railScroll")
        rail_scroll.viewport().setObjectName("railViewport")
        rail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rail_scroll.setMinimumHeight(42)
        rail_sections = QWidget(objectName="railSections")
        self.rail_sections = QVBoxLayout(rail_sections)
        self.rail_sections.setContentsMargins(5, 0, 5, 0)
        self.rail_sections.setSpacing(1)
        rail_scroll.setWidget(rail_sections)
        self.rail_layout.addWidget(rail_scroll, 1)
        body.addWidget(self.navigation_rail)
        self.navigator_timer = QTimer(self, singleShot=True, interval=16)
        self.navigator_timer.timeout.connect(self.update_navigator)
        for scrollbar in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            scrollbar.valueChanged.connect(self.schedule_navigator)
        self.view.zoom_changed.connect(self.schedule_navigator)
        self.view.active_page_changed.connect(self.schedule_navigator)
        self.view.active_page_changed.connect(self.visible_page_changed)
        self.view.selected.connect(self.handle_rectangle)
        self.view.shape_drawn.connect(self.save_shape)
        self.view.form_clicked.connect(self.edit_form_field)
        self.view.signature_clicked.connect(self.signature_explorer)
        self.view.link_clicked.connect(self.open_pdf_link)
        self.view.point_selected.connect(self.text_point)
        self.view.text_error.connect(self.note)
        viewer_column = QWidget()
        viewer_layout = QVBoxLayout(viewer_column)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)

        self.doc_tab_strip = QFrame(objectName="docTabStrip")
        tab_strip_layout = QHBoxLayout(self.doc_tab_strip)
        tab_strip_layout.setContentsMargins(8, 2, 8, 2)
        tab_strip_layout.setSpacing(4)
        self.doc_tabs = DocumentTabBar(objectName="docTabs")
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.setExpanding(False)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.doc_tabs.setUsesScrollButtons(True)
        self.doc_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.doc_tabs.currentChanged.connect(self.activate_doc_tab)
        self.doc_tabs.tab_detached.connect(self.detach_doc_tab)
        self.doc_tabs.customContextMenuRequested.connect(self.doc_tab_context)
        tab_strip_layout.addWidget(self.doc_tabs, 1)
        tab_strip_layout.addWidget(icon_button(tr("Abrir PDF"), "plus", self.open_dialog, size=26, glyph_size=16))
        tab_strip_layout.addWidget(icon_button(tr("Nueva ventana"), "view-columns", self.new_window, size=26, glyph_size=16))
        self.doc_tab_strip.hide()
        viewer_layout.addWidget(self.doc_tab_strip)

        self.find_bar = QFrame(objectName="findBar")
        find_layout = QHBoxLayout(self.find_bar)
        find_layout.setContentsMargins(10, 5, 10, 5)
        find_layout.setSpacing(6)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(tr("Buscar en el PDF…"))
        self.find_input.setClearButtonEnabled(True)
        self.find_input.setMaximumWidth(320)
        self.find_input.returnPressed.connect(lambda: self.step_search(1) if self.search_hits and self.search_result_key == self._current_search_key() else self.run_search(jump=True))
        self.find_input.textChanged.connect(self.sync_find_input)
        find_layout.addWidget(self.find_input, 1)
        self.find_count = QLabel(objectName="muted")
        self.find_count.setMinimumWidth(68)
        find_layout.addWidget(self.find_count)
        find_layout.addWidget(icon_button(tr("Coincidencia anterior (Mayús+F3)"), "chevron-up", lambda: self.step_search(-1), size=26, glyph_size=16))
        find_layout.addWidget(icon_button(tr("Siguiente coincidencia (F3)"), "chevron-down", lambda: self.step_search(1), size=26, glyph_size=16))
        self.find_accents_btn = QPushButton(tr("Tildes"))
        self.find_accents_btn.setCheckable(True)
        self.find_accents_btn.setToolTip(tr("Distinguir tildes"))
        self.find_accents_btn.toggled.connect(self.sync_find_accents)
        find_layout.addWidget(self.find_accents_btn)
        find_layout.addWidget(button("Lista y avanzada", self.open_search_panel))
        find_layout.addWidget(icon_button(tr("Cerrar búsqueda (Esc)"), "close", self.close_find_bar, size=26, glyph_size=16))
        self.find_bar.hide()
        viewer_layout.addWidget(self.find_bar)

        viewer_layout.addWidget(self.build_tour_strip())
        self.signature_strip = QFrame(objectName="signatureStrip")
        signatures = QHBoxLayout(self.signature_strip)
        signatures.setContentsMargins(12, 5, 12, 5)
        self.signature_label = QLabel()
        self.signature_label.setWordWrap(True)
        signatures.addWidget(self.signature_label, 1)
        self.signature_details_btn = button("Ver firmas", self.signature_explorer, glyph="document-award")
        signatures.addWidget(self.signature_details_btn)
        self.signature_strip.hide()
        viewer_layout.addWidget(self.signature_strip)
        viewer_layout.addWidget(self.form_strip)
        self.redaction_strip = QFrame(objectName="redactionStrip")
        redaction_layout = QHBoxLayout(self.redaction_strip)
        redaction_layout.setContentsMargins(12, 4, 12, 4)
        self.redaction_label = QLabel()
        self.redaction_label.setWordWrap(True)
        redaction_layout.addWidget(self.redaction_label, 1)
        redaction_layout.addWidget(button("Marcar zonas", self.start_redaction))
        self.redaction_save_btn = button("Guardar copia censurada…", self.save_redaction, primary=True)
        redaction_layout.addWidget(self.redaction_save_btn)
        self.redaction_strip.hide()
        viewer_layout.addWidget(self.redaction_strip)
        self.canvas = QStackedWidget()
        self.empty_state = self.build_empty_state()
        self.canvas.addWidget(self.empty_state)
        self.canvas.addWidget(self.view)
        viewer_layout.addWidget(self.canvas, 1)
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(4)
        self.body_splitter.addWidget(self.navigation_column)
        self.body_splitter.addWidget(viewer_column)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([260, 960])
        body.addWidget(self.body_splitter, 1)
        body.addWidget(self.tools)
        layout.addLayout(body, 1)
        self.bookmark_filter = QLineEdit()
        self.bookmark_filter.setPlaceholderText(tr("Filtrar marcadores…"))
        self.bookmark_filter.setClearButtonEnabled(True)
        self.bookmark_filter.textChanged.connect(self.filter_bookmarks)
        self.bookmark_tree = QTreeWidget()
        self.bookmark_tree.setHeaderHidden(True)
        self.bookmark_tree.setWordWrap(True)
        self.bookmark_tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.bookmark_tree.setUniformRowHeights(False)
        self.bookmark_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bookmark_tree.setItemDelegate(BookmarkRows(self.bookmark_tree))
        self.bookmark_tree.itemClicked.connect(self.open_bookmark)
        self.bookmarks_panel = self.navigation_panel("Marcadores", self.bookmark_filter, self.bookmark_tree)
        self.work_list = WorkspaceList(objectName="files")
        self.work_list.setAccessibleName(tr("Archivos de la mesa de trabajo"))
        self.work_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.work_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.work_list.setToolTip(tr("Haz clic en un nombre para abrir el PDF. Marca las casillas para trabajar con varios archivos."))
        remove_from_workspace = QAction(tr("Quitar de la mesa de trabajo"), self.work_list)
        remove_from_workspace.setShortcut(QKeySequence("Delete"))
        remove_from_workspace.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        remove_from_workspace.triggered.connect(self.remove_selected_work_documents)
        self.work_list.addAction(remove_from_workspace)
        self.work_list.itemActivated.connect(self.activate_work_item)
        self.work_list.open_requested.connect(self.activate_work_item)
        self.work_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.work_list.customContextMenuRequested.connect(self.work_context)
        work_panel = QWidget(objectName="workspaceFiles")
        work_layout = QVBoxLayout(work_panel)
        work_layout.setContentsMargins(10, 12, 10, 12)
        files_header = QHBoxLayout()
        files_header.addWidget(QLabel(tr("Mesa de trabajo"), objectName="panelLabel"), 1)
        files_header.addWidget(icon_button(tr("Añadir PDFs"), "plus", self.open_dialog))
        files_header.addWidget(icon_button(tr("Cerrar panel"), "close", lambda: self.set_navigation(False, animate=True)))
        work_layout.addLayout(files_header)
        work_layout.addWidget(self.work_list, 1)
        self.work_hint = QLabel(objectName="muted")
        self.work_hint.setWordWrap(True)
        work_layout.addWidget(self.work_hint)
        self.work_tab = work_panel
        self.navigation.insertTab(0, work_panel, icon("file", 16), tr("Archivos"))
        self.navigation.setTabIcon(1, icon("view-columns", 16))
        self.navigation.setCurrentWidget(work_panel)
        self.work_list.itemSelectionChanged.connect(self.sync_workspace_checks)
        self.work_list.itemChanged.connect(self.change_workspace_check)
        self.work_list.verticalScrollBar().valueChanged.connect(self.schedule_tour_highlight)
        self.navigation.currentChanged.connect(self.update_tool_scope)
        self.review_list = QListWidget()
        self.review_list.setItemDelegate(SearchResultDelegate(self.review_list))
        self.review_list.setWordWrap(True)
        self.review_list.itemClicked.connect(self.open_review_result)
        review = QWidget()
        review_layout = QVBoxLayout(review)
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Buscar texto en el documento"))
        self.query.returnPressed.connect(self.run_search)
        review_layout.addWidget(self.query)
        self.search_timer = QTimer(self, singleShot=True, interval=300)
        self.search_timer.timeout.connect(lambda: self.run_search(jump=False))
        self.query.textChanged.connect(self.schedule_search)
        self.search_accents = QCheckBox(tr("Distinguir tildes"))
        self.search_accents.setToolTip(tr("Con esta opción desmarcada, medicion encuentra medición. La ñ y la n se buscan por separado."))
        self.search_accents.toggled.connect(self.schedule_search)
        review_layout.addWidget(self.search_accents)
        self.search_advanced = QCheckBox(tr("Búsqueda avanzada"))
        self.search_advanced.setToolTip(tr(
            'Escribe los operadores en mayúsculas.\n'
            'AND · ambos términos en la misma página.\n'
            'OR · cualquiera de los términos.\n'
            'NOT · excluye páginas con ese término.\n'
            'Comillas · "health and safety" busca la frase.\n'
            'Paréntesis · (plano OR croquis) AND NOT borrador.\n'
            'Un espacio entre términos equivale a AND. NOT se aplica antes que AND, y AND antes que OR.'
        ))
        self.search_advanced.setToolTipDuration(24000)
        self.search_advanced.toggled.connect(self.schedule_search)
        review_layout.addWidget(self.search_advanced)
        self.search_run_btn = button("Buscar", self.run_search, glyph="search")
        review_layout.addWidget(self.search_run_btn)
        self.search_summary = QLabel(tr("Escribe para buscar en el PDF."))
        self.search_summary.setWordWrap(True)
        review_layout.addWidget(self.search_summary)
        self.comment_filter = QLineEdit()
        self.comment_filter.setPlaceholderText(tr("Filtrar anotaciones…"))
        self.comment_filter.setClearButtonEnabled(True)
        self.comment_filter.textChanged.connect(self.apply_comment_filter)
        review_layout.addWidget(self.comment_filter)
        self.comment_kind_filter = QComboBox()
        self.comment_kind_filter.currentIndexChanged.connect(self.apply_comment_filter)
        review_layout.addWidget(self.comment_kind_filter)
        self.comment_summary = QLabel(objectName="muted")
        self.comment_summary.setWordWrap(True)
        review_layout.addWidget(self.comment_summary)
        self.comment_records = []
        self.review_list.currentItemChanged.connect(
            lambda item, previous: self.open_review_result(item) if item and self.review_mode == "search" else None)
        review_layout.addWidget(self.review_list)
        self.search_page_btn = button("Coincidencias de la página…", self.open_search_page)
        self.search_page_btn.hide()
        review_layout.addWidget(self.search_page_btn)
        self.review_list.currentItemChanged.connect(self.update_search_page_button)
        self.delete_comment_btn = button("Eliminar anotación", self.delete_comment)
        review_layout.addWidget(self.delete_comment_btn)
        self.annotation_menu = action_menu("Editar anotación", (
            (tr("Mover…"), lambda: self.start_annotation_edit(False)),
            (tr("Redimensionar forma…"), lambda: self.start_annotation_edit(True)),
        ))
        review_layout.addWidget(self.annotation_menu)
        self.review_dock = QDockWidget(tr("Revisión"), self)
        self.review_widget = review
        self.review_dock.setWidget(review)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.review_dock)
        self.review_dock.hide()
        self.comments_panel = self.navigation_panel("Anotaciones")
        self.layers_list = QListWidget()
        self.layers_list.setWordWrap(True)
        self.layers_panel = self.navigation_panel("Capas", self.layers_list)
        self.layer_source = self.layer_view_path = None
        self.layer_timer = QTimer(self, singleShot=True, interval=170)
        self.layer_timer.timeout.connect(self.apply_layer_view)
        self.layers_list.itemChanged.connect(lambda _: self.layer_timer.start())
        sig_bar = QWidget()
        sig_bar_layout = QHBoxLayout(sig_bar)
        sig_bar_layout.setContentsMargins(0, 0, 0, 0)
        sig_bar_layout.setSpacing(6)
        self.signature_summary = QLabel("", objectName="muted")
        sig_bar_layout.addWidget(self.signature_summary, 1)
        self.signature_details_toggle = QPushButton(tr("Ocultar detalles"))
        self.signature_details_toggle.setCheckable(True)
        self.signature_details_toggle.setChecked(True)
        self.signature_details_toggle.setProperty("role", "flat")
        self.signature_details_toggle.toggled.connect(self.toggle_signature_details)
        sig_bar_layout.addWidget(self.signature_details_toggle)
        self.signature_filter = QLineEdit()
        self.signature_filter.setPlaceholderText(tr("Filtrar firmante o campo…"))
        self.signature_filter.setClearButtonEnabled(True)
        self.signature_filter.textChanged.connect(lambda _: self.populate_signatures_list())
        self.signatures_list = QListWidget()
        self.signatures_list.setWordWrap(True)
        self.signatures_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.signatures_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.signatures_list.setItemDelegate(SearchResultDelegate(self.signatures_list))
        self.signature_info = QTextBrowser(objectName="signatureDetails")
        self.signature_info.setAccessibleName(tr("Datos del certificado"))
        self.signature_splitter = QSplitter(Qt.Orientation.Vertical)
        self.signature_splitter.setChildrenCollapsible(False)
        self.signature_splitter.setHandleWidth(5)
        self.signature_splitter.addWidget(self.signatures_list)
        self.signature_splitter.addWidget(self.signature_info)
        self.signature_splitter.setStretchFactor(0, 3)
        self.signature_splitter.setStretchFactor(1, 2)
        self.signature_splitter.setSizes([280, 220])
        self.signatures_panel = self.navigation_panel("Firmas", sig_bar, self.signature_filter, self.signature_splitter)
        self.signatures_list.currentItemChanged.connect(lambda current, _: self.show_signature_details(current))
        self.signatures_list.itemClicked.connect(lambda item: self.jump_to_signature(item))
        self.signature_cache_key, self.signature_data = None, []
        self.rail_buttons = {}
        for panel, label, glyph in (
            (self.work_tab, "Archivos", "files"), (self.pages_panel, "Páginas", "pages"),
            (self.bookmarks_panel, "Marcadores", "bookmarks"), (self.layers_panel, "Capas", "layers"),
            (self.comments_panel, "Anotaciones", "comments"), (self.signatures_panel, "Firmas", "signatures"),
        ):
            control = button("", lambda current=panel: self.choose_navigation(current, toggle=True))
            control.setProperty("iconGlyph", (f"rail-{glyph}", 20, False, True))
            control.setIcon(icon(f"rail-{glyph}", 20, filled_when_checked=True))
            control.setIconSize(QSize(20, 20))
            control.setToolTip(tr(label))
            control.setAccessibleName(tr(label))
            control.setFixedHeight(34)
            control.setProperty("role", "railSection")
            control.setCheckable(True)
            self.rail_sections.addWidget(control)
            self.rail_buttons[panel] = control
        self.rail_sections.addStretch()
        self.navigation.currentChanged.connect(self.sync_navigation)
        self.surface_dock = self.build_surface_dock()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.surface_dock)
        self.tabifyDockWidget(self.review_dock, self.surface_dock)
        self.surface_dock.hide()
        self.review_mode = None
        self.review_dock.visibilityChanged.connect(lambda _: QTimer.singleShot(0, self.sync_tool_panel))
        self.review_dock.visibilityChanged.connect(self.clear_search_marks_if_closed)
        self.surface_dock.visibilityChanged.connect(lambda _: QTimer.singleShot(0, self.sync_tool_panel))

        footer = QFrame(objectName="footer")
        self.document_footer = footer
        row = QHBoxLayout(footer)
        row.setContentsMargins(12, 5, 12, 5)
        self.status = QLabel("", objectName="muted")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.status, 1)
        self.scale_label = QLabel("", objectName="muted")
        self.scale_label.setToolTip(tr("Escala de medición de esta página, válida durante esta sesión"))
        self.scale_label.hide()
        row.addWidget(self.scale_label)
        self.footer_page_pill = QLabel("", objectName="footerPage")
        self.footer_page_pill.setToolTip(tr("Página actual del documento"))
        self.footer_page_pill.hide()
        row.addWidget(self.footer_page_pill)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(125)
        self.progress.setTextVisible(False)
        self.progress.hide()
        row.addWidget(self.progress)
        self.cancel_job_btn = button("Cancelar operación", self.cancel_job)
        self.cancel_job_btn.hide()
        row.addWidget(self.cancel_job_btn)
        self.page_number = QLineEdit("1", objectName="readerPageNumber")
        self.page_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_number.setFixedWidth(40)
        self.page_number.setFixedHeight(26)
        self.page_number.setMaxLength(8)
        self.page_number.setAccessibleName(tr("Ir a la página"))
        self.page_number.setToolTip(tr("Escribe el número de página y pulsa Enter."))
        self.page_number.editingFinished.connect(self.apply_page_number)
        self.page_label = QLabel("", objectName="readerPageTotal")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        previous_page = icon_button(tr("Página anterior"), "chevron-left", lambda: self.goto(self.current - 1), size=28, glyph_size=16)
        next_page = icon_button(tr("Página siguiente"), "chevron-right", lambda: self.goto(self.current + 1), size=28, glyph_size=16)
        self.previous_page_btn = previous_page
        self.next_page_btn = next_page
        zoom_out = icon_button(tr("Alejar (Ctrl+-)"), "rail-zoom-out", lambda: self.view.zoom(0.8), size=28, glyph_size=16)
        zoom_in = icon_button(tr("Acercar (Ctrl+=)"), "rail-zoom-in", lambda: self.view.zoom(1.25), size=28, glyph_size=16)
        for control in (previous_page, next_page, zoom_out, zoom_in):
            control.setProperty("role", "hudButton")
        self.zoom_level = QLineEdit("100 %", objectName="zoomLevel")
        self.zoom_level.hide()
        self.zoom_level.editingFinished.connect(self.apply_zoom_level)
        size_menu = action_menu("100 %", (
            ("50 %", lambda: self.view.set_percent(50)),
            ("75 %", lambda: self.view.set_percent(75)),
            (tr("Tamaño real (100 %)"), lambda: self.view.set_percent(100)),
            ("125 %", lambda: self.view.set_percent(125)),
            ("150 %", lambda: self.view.set_percent(150)),
            ("200 %", lambda: self.view.set_percent(200)),
        ))
        size_menu.setObjectName("hudZoomButton")
        size_menu.setAccessibleName(tr("Porcentaje de zoom"))
        size_menu.setToolTip(tr("Zoom del visor. Haz clic para elegir un nivel rápido o usa Ctrl + rueda."))
        size_menu.menu().addSeparator()
        size_menu.menu().addAction(tr("Ajustar ancho"), self.view.fit_width)
        size_menu.menu().addAction(tr("Ajustar página"), self.view.fit_page)
        self.size_two_page_action = size_menu.menu().addAction(tr("Doble página"))
        self.size_two_page_action.setCheckable(True)
        self.size_two_page_action.toggled.connect(self.toggle_two_page)
        self.hud_zoom_btn = size_menu
        self.view.zoom_changed.connect(self.update_zoom_level)

        hud_fit_width = button("Ancho", self.view.fit_width)
        hud_fit_width.setProperty("role", "hudButton")
        hud_fit_width.setToolTip(tr("Ajustar ancho"))
        hud_fit_page = button("Página", self.view.fit_page, glyph="rail-fit")
        hud_fit_page.setProperty("role", "hudButton")
        hud_fit_page.setToolTip(tr("Ajustar página"))
        self.hud_two_page_btn = button("Doble", lambda: self.toggle_two_page(self.hud_two_page_btn.isChecked()), glyph="view-columns")
        self.hud_two_page_btn.setProperty("role", "hudToggle")
        self.hud_two_page_btn.setCheckable(True)
        self.hud_two_page_btn.setToolTip(tr("Doble página"))
        hud_rotate = icon_button(tr("Girar página"), "reload-circle", self.rotate_page, size=28, glyph_size=16)
        hud_rotate.setProperty("role", "hudButton")

        self.viewer_hud = QFrame(self.canvas, objectName="viewerHud")
        self.reader_controls = self.viewer_hud
        self.reader_in_rail = False
        self._hud_opacity = QGraphicsOpacityEffect(self.viewer_hud)
        self._hud_opacity.setOpacity(0.42)
        self.viewer_hud.setGraphicsEffect(self._hud_opacity)
        self._hud_anim = QPropertyAnimation(self._hud_opacity, b"opacity", self)
        self._hud_anim.setDuration(170)
        self._hud_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hud_idle_timer = QTimer(self, singleShot=True, interval=2200)
        self._hud_idle_timer.timeout.connect(self._dim_viewer_hud)
        self._hud_hovered = False
        self.viewer_hud.installEventFilter(self)
        self.canvas.installEventFilter(self)
        self.canvas.currentChanged.connect(lambda _: self.position_viewer_hud())
        self.view.viewport().setMouseTracking(True)
        size_menu.menu().aboutToShow.connect(lambda: self._wake_viewer_hud(sticky=True))
        size_menu.menu().aboutToHide.connect(lambda: self._wake_viewer_hud(sticky=False))
        hud_layout = QHBoxLayout(self.viewer_hud)
        hud_layout.setContentsMargins(8, 5, 8, 5)
        hud_layout.setSpacing(4)

        def hud_sep():
            sep = QFrame(objectName="hudDivider")
            sep.setFrameShape(QFrame.Shape.VLine)
            return sep

        for item in (
            previous_page, self.page_number, self.page_label, next_page,
            hud_sep(),
            zoom_out, size_menu, zoom_in,
            hud_sep(),
            hud_fit_width, hud_fit_page, self.hud_two_page_btn, hud_rotate,
        ):
            hud_layout.addWidget(item)
        self.viewer_hud.hide()
        self.view.viewport().installEventFilter(self)
        self.footer_layout = row
        row.addWidget(self.focus_toggle)
        self.fullscreen_toggle = button("Pantalla completa", self.toggle_fullscreen, glyph="maximize")
        row.addWidget(self.fullscreen_toggle)
        layout.addWidget(footer)
        self.document_controls = (
            self.save_btn, self.save_copy_btn, self.close_pdf_btn, self.search_btn, self.rotate_btn, self.remove_btn, self.extract_btn, self.pages,
            self.zoom_level, self.page_number, self.bookmark_tree, self.focus_toggle,
            previous_page, next_page, zoom_out, zoom_in, size_menu, hud_fit_width, hud_fit_page, self.hud_two_page_btn, hud_rotate,
            *(widget for _, _, widgets in groups for widget in widgets),
        )
        self.build_menus()
        self.shortcut("Ctrl+Shift+C", self.copy_page)
        self.shortcut("Esc", self.escape_view)
        self.shortcut("Ctrl+Return", self.finish_measure)
        self.shortcut("Ctrl+Tab", lambda: self.step_doc_tab(1))
        self.shortcut("Ctrl+Shift+Tab", lambda: self.step_doc_tab(-1))
        self.view.page()
        self.note(tr("Abre un PDF o arrástralo a la ventana."))
        self.enable_controls()
        self.tour_spotlight = TourSpotlight(self)
        self.tour_highlight_timer = QTimer(self, singleShot=True)
        self.tour_highlight_timer.timeout.connect(self.refresh_tour_highlight)
        QApplication.instance().installEventFilter(self)

    def build_menus(self):
        bar = self.menuBar()

        def add(menu, label, callback, standard=None, *alternates):
            action = menu.addAction(label)
            action.triggered.connect(lambda: callback())
            shortcuts = QKeySequence.keyBindings(standard) if standard is not None else []
            for keys in alternates:
                sequence = QKeySequence(keys)
                if sequence not in shortcuts:
                    shortcuts.append(sequence)
            if shortcuts:
                action.setShortcuts(shortcuts)
                self.addAction(action)
            return action

        key = QKeySequence.StandardKey
        files = bar.addMenu(tr("&Archivo"))
        add(files, tr("&Nueva ventana"), self.new_window, key.New)
        self.menu_open = add(files, tr("&Abrir PDF…"), self.open_dialog, key.Open)
        self.recent_menu = files.addMenu(tr("Documentos recientes"))
        self.recent_menu.aboutToShow.connect(self.populate_recent_menu)
        create = files.addMenu(tr("Crear PDF"))
        add(create, tr("PDF en blanco…"), self.create_blank_pdf)
        add(create, tr("Desde imágenes…"), self.create_from_images)
        add(create, tr("Desde imagen del portapapeles"), self.create_from_clipboard)
        add(files, tr("Unir PDFs"), self.merge_dialog)
        files.addSeparator()
        save = add(files, tr("&Guardar"), self.save, key.Save)
        save_copy = add(files, tr("Guardar &como…"), lambda: self.save(as_copy=True), key.SaveAs)
        export = files.addMenu(tr("&Exportar"))
        for label, callback in self.export_actions():
            add(export, label, callback)
        export.insertSeparator(export.actions()[5])
        export.aboutToShow.connect(lambda: self.update_export_menu(export))
        protect = add(files, tr("Proteger con contraseña…"), self.protect_pdf)
        archive = add(files, tr("Guardar copia PDF/A…"), self.export_pdf_archive)
        share = add(files, tr("Preparar copia para compartir…"), self.share_pdf_copy)
        self.menu_reload = add(files, tr("Volver a la versión guardada…"), self.reload_saved_pdf, key.Refresh)
        files.addSeparator()
        self.menu_print = add(files, tr("&Imprimir…"), self.print_pdf, key.Print)
        properties = add(files, tr("Propiedades del documento…"), self.show_document_properties, None,
                         "Ctrl+I" if sys.platform == "darwin" else "Ctrl+D")
        self.menu_document_folder = add(files, tr("Abrir carpeta del documento"), self.open_document_folder)
        files.addSeparator()
        close = add(files, tr("&Cerrar PDF"), self.close_work_document, key.Close)
        close_all = add(files, tr("Cerrar todos los PDF"), self.close_all_documents, None, "Ctrl+Shift+W")
        move = add(files, tr("Mover PDF a otra ventana"), self.move_to_new_window)
        another_view = add(files, tr("Abrir otra vista del PDF"), self.open_secondary_view)
        if sys.platform == "win32":
            add(files, tr("Elegir lector PDF predeterminado…"), self.open_default_apps)
        files.addSeparator()
        quit_action = add(files, tr("&Salir"), QApplication.closeAllWindows, key.Quit, "Ctrl+Q")
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.document_controls += (save, save_copy, export.menuAction(), protect, archive, share, self.menu_print,
                                   properties, close, close_all, move, another_view, self.insert_btn)

        edit = bar.addMenu(tr("&Edición"))
        self.menu_undo = add(edit, tr("&Deshacer"), self.undo_edit, key.Undo)
        self.menu_redo = add(edit, tr("&Rehacer"), self.redo_edit, key.Redo, "Ctrl+Shift+Z")
        edit.addSeparator()
        self.menu_copy_text = add(edit, tr("Copiar texto seleccionado"), self.copy_text, key.Copy)
        self.menu_copy_text.setEnabled(False)
        self.menu_select_all = add(edit, tr("Seleccionar todo"), self.select_all_text, key.SelectAll)
        self.view.text_selection_changed.connect(self.update_text_selection)
        self.view.text_copied.connect(lambda: self.note(tr("Texto copiado al portapapeles.")))
        edit.addSeparator()
        find = add(edit, tr("Buscar texto"), self.open_search, key.Find)
        next_match = add(edit, tr("Siguiente coincidencia"), lambda: self.step_search(1), key.FindNext, "F3")
        previous_match = add(edit, tr("Coincidencia anterior"), lambda: self.step_search(-1), key.FindPrevious, "Shift+F3")
        preferences = add(edit, tr("&Preferencias…"), self.show_preferences, key.Preferences, "Ctrl+,")
        preferences.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.document_controls += (self.menu_select_all, find, next_match, previous_match)

        view = bar.addMenu(tr("&Vista"))
        self.menu_two_page = view.addAction(tr("Doble página"))
        self.menu_two_page.setCheckable(True)
        self.menu_two_page.setShortcut(QKeySequence("Ctrl+2"))
        self.menu_two_page.toggled.connect(self.toggle_two_page)
        add(view, tr("Enfocar documento"), self.toggle_focus, None, "F9")
        add(view, tr("Pantalla completa"), self.toggle_fullscreen, key.FullScreen, "F11")
        self.document_controls += (
            add(view, tr("Acercar"), lambda: self.view.zoom(1.25), key.ZoomIn, "Ctrl+="),
            add(view, tr("Alejar"), lambda: self.view.zoom(0.8), key.ZoomOut),
            add(view, tr("Tamaño real (100 %)"), lambda: self.view.set_percent(100), None, "Ctrl+1"),
            add(view, tr("Ajustar página"), self.view.fit_page, None, "Ctrl+0"),
        )
        view.addSeparator()
        add(view, tr("Mostrar u ocultar Archivos y Páginas"), self.toggle_navigation)
        add(view, tr("Mostrar u ocultar herramientas"), self.toggle_tool_panel)

        help_menu = bar.addMenu(tr("A&yuda"))
        add(help_menu, tr("Paleta de comandos…"), self.open_command_palette, None, "Ctrl+K")
        add(help_menu, tr("Atajos de teclado y ratón…"), self.show_shortcuts, None, "Ctrl+/")
        add(help_menu, tr("Visita guiada…"), self.start_tour)
        add(help_menu, tr("Guía de herramientas…"), self.open_welcome_guide, key.HelpContents)
        self.menu_update = add(help_menu, tr("&Buscar actualizaciones…"), self.check_updates)
        add(help_menu, tr("Abrir carpeta de registros…"), self.open_logs_folder)
        about = add(help_menu, tr("&Acerca de {0}").format(APP_NAME), self.show_about)
        about.setMenuRole(QAction.MenuRole.AboutRole)

    def create_blank_pdf(self):
        if self.job is not None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Crear PDF en blanco…"))
        dialog.setMinimumWidth(420)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        paper = QComboBox()
        for label, size in (("A4", QPageSize.PageSizeId.A4), ("A3", QPageSize.PageSizeId.A3),
                            (tr("Carta"), QPageSize.PageSizeId.Letter)):
            paper.addItem(label, size)
        landscape = QCheckBox(tr("Horizontal"))
        layout.addRow(tr("Tamaño de página"), paper)
        layout.addRow(tr("Orientación"), landscape)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Crear PDF"))
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addRow(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        paper_size = QPageSize(paper.currentData()).sizePoints()
        width, height = paper_size.width(), paper_size.height()
        if landscape.isChecked():
            width, height = height, width
        destination = self.scratch_path()
        try:
            blank_pdf(destination, width, height)
            self.new_work_document(destination, name=tr("Sin título.pdf"), dirty=True)
        except (OSError, ValueError) as error:
            destination.unlink(missing_ok=True)
            self.error(error)

    def print_pdf(self):
        if not self.path or self.job is not None:
            return
        self.view.finish_inline()
        if self.redaction_boxes:
            self.error(tr("Guarda y abre la copia censurada para imprimir con la censura aplicada."))
            return
        source, password = self.path, self.document_password
        try:
            sizes = document_sizes(source, self.document_reader, password)
        except Exception as error:
            self.error(error)
            return
        dialog = PrintDialog(self, source, password, self.name, sizes, self.current)
        if not dialog.exec():
            return
        destination = None
        if not dialog.device.currentData():
            name = tr("{0} - impresión.pdf").format(Path(self.name).stem)
            destination = self.save_as(tr("Guardar PDF de impresión"), name, "pdf")
            if not destination:
                return
            if destination.resolve() in (source.resolve(), self.saved_path, self.protected_source):
                self.error(tr("Elige otro nombre para conservar el PDF original."))
                return

        operation = QProgressDialog(tr("Preparando páginas para imprimir…"), tr("Cancelar"), 0, len(dialog.sheets), self)
        operation.setWindowTitle(tr("Imprimir PDF"))
        operation.setWindowModality(Qt.WindowModality.WindowModal)

        def progress(current, total):
            operation.setMaximum(total)
            operation.setValue(current)
            if operation.wasCanceled():
                raise OperationCancelled()

        settings = dialog.render_settings()
        try:
            if destination:
                with atomic_output(destination) as temporary:
                    dialog.printer.setOutputFileName(str(temporary))
                    print_pages(source, password, dialog.printer, None, progress, **settings)
                    if len(reader_for(temporary).pages) != len(dialog.sheets):
                        raise ValueError(tr("El PDF de impresión no contiene todas las caras previstas."))
                self.note(tr("PDF de impresión guardado."))
            elif dialog.native_driver:
                from windows_print import print_driver_job

                print_driver_job(dialog.native_driver, source, password, self.name, sizes, dialog.sheets,
                                 progress, quality=settings["quality"], annotations=settings["annotations"])
                self.note(tr("Trabajo enviado a la impresora."))
            else:
                print_pages(source, password, dialog.printer, None, progress, **settings)
                self.note(tr("Trabajo enviado a la impresora."))
        except OperationCancelled:
            self.note(tr("Impresión cancelada."))
        except Exception as error:
            self.error(error)
        finally:
            operation.close()

    def create_from_images(self):
        if self.job is not None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Elegir imágenes"), filter=
                                               tr("Imágenes (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)"))
        if not paths:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Crear PDF desde imágenes"))
        dialog.resize(470, 365)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(tr("Arrastra para cambiar el orden. Cada imagen ocupará una página A4.")))
        images = QListWidget()
        images.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for path in map(Path, paths):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setData(Qt.ItemDataRole.UserRole + 1, 0)
            item.setToolTip(str(path))
            images.addItem(item)
        images.setCurrentRow(0)
        layout.addWidget(images)

        def rotate():
            item = images.currentItem()
            if item:
                angle = (item.data(Qt.ItemDataRole.UserRole + 1) + 90) % 360
                item.setData(Qt.ItemDataRole.UserRole + 1, angle)
                name = Path(item.data(Qt.ItemDataRole.UserRole)).name
                item.setText(f"{name} · {angle}°" if angle else name)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(tr("Girar 90°"), QDialogButtonBox.ButtonRole.ActionRole).clicked.connect(rotate)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Crear PDF"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            items = [images.item(row) for row in range(images.count())]
            self.make_image_pdf([(item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1))
                                 for item in items])

    def create_from_clipboard(self):
        if self.job is not None:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            self.note(tr("El portapapeles no contiene una imagen."))
            return
        source = self.scratch_path().with_suffix(".png")
        if not image.save(str(source), "PNG"):
            self.error(tr("No se pudo leer la imagen del portapapeles."))
            return
        self.make_image_pdf([(source, 0)], temporary_image=source)

    def make_image_pdf(self, files, *, temporary_image=None):
        destination = self.scratch_path()

        def convert(progress):
            try:
                images_to_pdf(files, destination, progress)
            finally:
                if temporary_image:
                    temporary_image.unlink(missing_ok=True)

        self.start_job(tr("Convirtiendo imágenes…"), convert,
                       lambda _: self.new_work_document(destination, name=tr("Imágenes.pdf"), dirty=True),
                       progress_label=tr("Convirtiendo imagen"), cancellable=True)

    def reload_saved_pdf(self):
        source = self.saved_path or self.protected_source
        if not source or self.job is not None:
            return
        self.view.finish_inline()
        if (self.dirty or self.redaction_boxes) and QMessageBox.question(
            self, tr("Volver a la versión guardada…"),
            tr("Se perderán los cambios pendientes. ¿Volver a cargar el PDF guardado?"),
        ) != QMessageBox.StandardButton.Yes:
            return
        obsolete = [self.path, *[state.path for state in self.undo_versions.get(self.work_key, ())],
                    *[state.path for state in self.redo_versions.get(self.work_key, ())]]
        password = self.document_password
        try:
            while True:
                try:
                    self.load(source, page=self.current, preserve_previous=True, password=password)
                    break
                except ProtectedPdf:
                    password, okay = QInputDialog.getText(self, tr("PDF protegido"), tr("Contraseña"),
                                                          QLineEdit.EchoMode.Password)
                    if not okay:
                        return
            self.undo_versions.pop(self.work_key, None)
            self.redo_versions.pop(self.work_key, None)
            for path in set(obsolete):
                if path != self.path and path.parent == self.scratch:
                    path.unlink(missing_ok=True)
            self.sync_secondary_views(self.work_key, self.document_snapshot(), force=True)
            self.enable_controls()
            self.note(tr("Versión guardada cargada."))
        except Exception as error:
            self.error(error)

    def share_pdf_copy(self):
        if not self.path or self.job is not None:
            return
        self.view.finish_inline()
        if self.redaction_boxes:
            self.error(tr("Guarda primero la copia censurada para compartirla."))
            return
        destination = self.save_as(tr("Preparar copia para compartir…"), tr("{0} - copia.pdf").format(Path(self.name).stem), "pdf")
        if not destination:
            return
        if destination.resolve() in (self.path.resolve(), self.saved_path, self.protected_source):
            self.error(tr("Elige otro nombre para conservar el PDF original."))
            return
        try:
            with atomic_output(destination) as temporary:
                copyfile(self.path, temporary)
        except OSError as error:
            self.error(error)
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(destination.resolve()))])
        QApplication.clipboard().setMimeData(mime)
        self.note(tr("Copia guardada y copiada al portapapeles como archivo."))

    def export_pdf_archive(self):
        if not self.path or self.job is not None:
            return
        self.view.finish_inline()
        if self.redaction_boxes:
            self.error(tr("Guarda primero la copia censurada para exportarla a PDF/A."))
            return
        ghostscript, java, validator = archive_tools()
        ghostscript = self.preferences.value("pdfa/ghostscript", ghostscript or "")
        validator = self.preferences.value("pdfa/verapdf", str(validator or ""))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Guardar copia PDF/A…"))
        layout = QFormLayout(dialog)
        profile = QComboBox()
        for item in PROFILES:
            profile.addItem(f"PDF/A-{item}", item)
        profile.setCurrentIndex(1)
        layout.addRow(tr("Perfil"), profile)
        help_label = QLabel(tr("La copia se guarda solo si veraPDF confirma que cumple el perfil. La conversión puede cambiar los formularios."))
        help_label.setWordWrap(True)
        layout.addRow(help_label)
        fields = []
        for label, value, filter_text in (("Ghostscript", ghostscript, "Ghostscript (gs gswin64c.exe);;*"),
                                          ("veraPDF", validator, "veraPDF (greenfield-apps-*.jar)")):
            field = QLineEdit(value)
            browse = button("Examinar…", lambda checked=field, filters=filter_text: self.browse_archive_tool(checked, filters))
            row = QHBoxLayout()
            row.addWidget(field)
            row.addWidget(browse)
            layout.addRow(label, row)
            fields.append(field)
        guides = QLabel('<a href="https://ghostscript.com/releases/gsdnld.html">Ghostscript</a>'
                        ' · <a href="https://docs.verapdf.org/install/">veraPDF</a>')
        guides.setOpenExternalLinks(True)
        layout.addRow(tr("Descargas oficiales"), guides)
        if not java:
            layout.addRow(QLabel(tr("Instala Java para ejecutar el validador veraPDF.")))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(java))
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addRow(controls)
        dialog.resize(550, dialog.sizeHint().height())
        if not dialog.exec():
            return
        ghostscript, validator = (field.text().strip() for field in fields)
        if not Path(ghostscript).is_file() or not Path(validator).is_file():
            self.error(tr("Selecciona el ejecutable de Ghostscript y el archivo greenfield-apps de veraPDF."))
            return
        if pdf_has_signatures(self.document_reader) and not self.confirm_unsigned_copy():
            return
        version = profile.currentData()
        name = f"{Path(self.name).stem}_PDF-A-{version}.pdf"
        destination = self.save_as(tr("Guardar copia PDF/A…"), name, "pdf")
        if not destination:
            return
        if destination.resolve() in (self.path.resolve(), self.saved_path, self.protected_source):
            self.error(tr("Elige otro nombre para conservar el PDF original."))
            return
        self.preferences.setValue("pdfa/ghostscript", ghostscript)
        self.preferences.setValue("pdfa/verapdf", validator)
        source, password = self.path, self.document_password

        def done(_):
            self.register_work_document(WorkDocument(destination, destination.name, saved_path=destination))
            self.note(tr("Copia PDF/A-{0} validada y guardada.").format(version))

        self.start_job(tr("Generando PDF/A…"), lambda progress: export_archive(
            source, destination, version, ghostscript, java, validator, progress, password=password,
        ), done, progress_label=tr("Conversión y validación"), cancellable=True)

    def browse_archive_tool(self, field, filters):
        path, _ = QFileDialog.getOpenFileName(self, tr("Elegir herramienta"), field.text(), filters)
        if path:
            field.setText(path)

    def show_document_properties(self):
        if not self.path or self.job is not None:
            return
        reader = self.document_reader
        metadata = reader.metadata or {}
        version = max(reader.pdf_header.removeprefix("%PDF-"),
                      str(reader.root_object.get("/Version", "")).removeprefix("/"))
        page = reader.pages[self.current]
        unit = float(page.get("/UserUnit", 1)) * 25.4 / 72
        width, height = float(page.cropbox.width) * unit, float(page.cropbox.height) * unit
        if page.rotation % 180:
            width, height = height, width
        location = self.saved_path or self.protected_source
        try:
            size = file_size_label(self.path.stat().st_size)
        except OSError:
            size = "—"
        fields = [
            (tr("Archivo"), self.name),
            (tr("Ubicación"), str(location) if location else tr("Aún no se ha guardado")),
            (tr("Tamaño del archivo"), size),
            (tr("Páginas"), str(self.count)),
            (tr("Tamaño de la página actual"), f"{width:.1f} × {height:.1f} mm"),
            (tr("Versión del PDF"), version),
            (tr("Cifrado con contraseña"), tr("Sí") if reader.is_encrypted else tr("No")),
            (tr("Firmas digitales"), tr("Sí") if pdf_has_signatures(reader) else tr("No")),
        ]
        for label, key in ((tr("Título"), "/Title"), (tr("Autor"), "/Author"), (tr("Asunto"), "/Subject"),
                           (tr("Palabras clave"), "/Keywords"), (tr("Aplicación de origen"), "/Creator"),
                           (tr("Generador del PDF"), "/Producer")):
            if metadata.get(key):
                fields.append((label, str(metadata[key])))
        for label, attribute, key in ((tr("Creado"), "creation_date", "/CreationDate"),
                                      (tr("Modificado"), "modification_date", "/ModDate")):
            if metadata.get(key):
                try:
                    value = getattr(metadata, attribute, None)
                except ValueError:
                    value = None
                fields.append((label, value.isoformat(sep=" ", timespec="minutes") if value else str(metadata[key])))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Propiedades del documento…"))
        dialog.resize(555, 465)
        layout = QVBoxLayout(dialog)
        details = QTextBrowser()
        details.setAccessibleName(tr("Propiedades del documento…"))
        details.setHtml("".join(f"<p><b>{escape(label)}</b><br>{escape(value)}</p>" for label, value in fields))
        layout.addWidget(details)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.button(QDialogButtonBox.StandardButton.Close).setText(tr("Cerrar"))
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def open_document_folder(self):
        path = self.saved_path or self.protected_source
        if path and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))):
            self.error(tr("No se pudo abrir la carpeta del documento."))

    def close_all_documents(self):
        while self.path is not None and self.close_work_document():
            pass

    def show_preferences(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Preferencias"))
        dialog.setMinimumWidth(480)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        zoom = QComboBox()
        zoom.addItem(tr("Ajustar página"), "page")
        zoom.addItem(tr("Ajustar ancho"), "width")
        zoom.setCurrentIndex(int(self.preferences.value("vista/ajuste_inicial", "page") == "width"))
        layout.addRow(tr("Al abrir un PDF"), zoom)
        remember = QCheckBox(tr("Recordar la última carpeta"))
        remember.setChecked(self.preferences.value("archivos/recordar_carpeta", True, type=bool))
        layout.addRow(tr("Archivos"), remember)
        auto_updates = QCheckBox(tr("Comprobar actualizaciones al iniciar"))
        auto_updates.setChecked(self.preferences.value("actualizaciones/comprobar_al_iniciar", False, type=bool))
        layout.addRow(tr("Actualizaciones"), auto_updates)
        theme = QComboBox()
        for text, code in ((tr("Tema del sistema"), "system"), (tr("Claro"), "light"), (tr("Oscuro"), "dark")):
            theme.addItem(text, code)
        old_theme = self.preferences.value("apariencia/tema", "system")
        theme.setCurrentIndex(max(0, theme.findData(old_theme)))
        layout.addRow(tr("Tema"), theme)
        language = QComboBox()
        for text, code in ((tr("Idioma del sistema"), "system"), (tr("Español"), "es"), ("English", "en")):
            language.addItem(text, code)
        old_language = self.preferences.value("idioma/interfaz", "system")
        index = language.findData(old_language)
        language.setCurrentIndex(max(0, index))
        layout.addRow(tr("Idioma de la interfaz"), language)
        restart = QLabel(tr("El cambio de idioma se aplica al reiniciar PDFiu."), objectName="muted")
        restart.setWordWrap(True)
        layout.addRow(restart)
        layout.addRow(tr("Herramientas"), button("Personalizar favoritos…", self.choose_favorites))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Guardar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            self.preferences.setValue("vista/ajuste_inicial", zoom.currentData())
            self.preferences.setValue("archivos/recordar_carpeta", remember.isChecked())
            self.preferences.setValue("actualizaciones/comprobar_al_iniciar", auto_updates.isChecked())
            self.preferences.setValue("apariencia/tema", theme.currentData())
            self.preferences.setValue("idioma/interfaz", language.currentData())
            if QApplication.instance() is not None:
                apply_theme(QApplication.instance(), theme.currentData())
            if not remember.isChecked():
                self.preferences.remove("archivos/ultima_carpeta")
            self.preferences.sync()
            if self.preferences.status() != QSettings.Status.NoError:
                self.error(tr("No se pudieron guardar las preferencias."))

    def open_logs_folder(self):
        folder = log_directory(APP_NAME)
        folder.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.error(tr("No se pudo abrir la carpeta de registros."))

    def filter_bookmarks(self, text):
        query = text.strip().casefold()

        def apply(item):
            label = item.text(0).casefold()
            child_match = False
            for idx in range(item.childCount()):
                if apply(item.child(idx)):
                    child_match = True
            matched = not query or query in label or child_match
            item.setHidden(not matched)
            if query and child_match:
                item.setExpanded(True)
            return matched

        for idx in range(self.bookmark_tree.topLevelItemCount()):
            apply(self.bookmark_tree.topLevelItem(idx))

    def collect_palette_commands(self):
        entries = []
        seen = set()

        def visit_menu(menu, prefix=""):
            for action in menu.actions():
                if action.isSeparator() or not action.isVisible() or not action.isEnabled():
                    continue
                label = action.text().replace("&", "").strip()
                if not label:
                    continue
                submenu = action.menu()
                if submenu is not None:
                    visit_menu(submenu, f"{prefix} › {label}" if prefix else label)
                    continue
                shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                key = (label, prefix)
                if key not in seen:
                    seen.add(key)
                    entries.append((label, prefix, shortcut, action.trigger))

        for action in self.menuBar().actions():
            if action.menu() is not None and action.isVisible():
                visit_menu(action.menu(), action.text().replace("&", "").strip())

        for control in self.tools.findChildren(QPushButton):
            if not control.isEnabled():
                continue
            label = control.text().replace("&", "").strip()
            if not label:
                continue
            if control.menu() is not None:
                visit_menu(control.menu(), label)
                continue
            if any(existing[0] == label for existing in entries):
                continue
            entries.append((label, tr("Herramientas"), "", control.click))

        return entries

    def open_command_palette(self):
        if self.job is not None:
            return
        dialog = CommandPaletteDialog(self.collect_palette_commands(), self)
        if dialog.exec() and dialog.chosen is not None:
            dialog.chosen()

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Acerca de {0}").format(APP_NAME))
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(brand_icon().pixmap(48, 48))
        logo.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel(f"<b>{escape(APP_NAME)} {escape(APP_VERSION)}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        summary = QLabel(tr("Lector y editor de PDF de código abierto para trabajar en tu equipo."))
        summary.setWordWrap(True)
        copyright_note = QLabel(
            tr("© 2026 mfcb89 · Código fuente bajo licencia MIT. Nombre y logotipos reservados."),
            objectName="muted",
        )
        copyright_note.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(summary)
        title_box.addWidget(copyright_note)
        header.addLayout(title_box, 1)
        layout.addLayout(header)

        notices = QLabel(
            tr(
                "PDFiu utiliza Qt y PySide6 bajo LGPLv3 (cargados como bibliotecas dinámicas sustituibles), "
                "PDFium / pypdfium2, Tesseract OCR, pyHanko, pypdf y Fluent UI System Icons. "
                "Consulta los avisos de terceros y el texto de las licencias incluidos con esta copia."
            )
        )
        notices.setWordWrap(True)
        layout.addWidget(notices)

        repo_link = QLabel(
            '<a href="https://github.com/mfcb89/pdfiu">github.com/mfcb89/pdfiu</a>'
        )
        repo_link.setOpenExternalLinks(True)
        layout.addWidget(repo_link)

        actions = QHBoxLayout()
        notices_path = ROOT / "third-party" if (ROOT / "third-party").is_dir() else ROOT / "THIRD_PARTY_NOTICES.md"
        if notices_path.exists():
            notices_btn = QPushButton(tr("Avisos de terceros"))
            notices_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(notices_path))))
            actions.addWidget(notices_btn)
        license_path = ROOT / "LICENSE"
        if license_path.is_file():
            license_btn = QPushButton(tr("Licencia MIT"))
            license_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(license_path))))
            actions.addWidget(license_btn)
        qt_btn = QPushButton(tr("Acerca de Qt…"))
        qt_btn.clicked.connect(lambda: QMessageBox.aboutQt(dialog, tr("Acerca de Qt")))
        actions.addWidget(qt_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Cerrar"))
        buttons.rejected.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def schedule_update_check(self):
        if is_store_package():
            return
        if not self.preferences.value("actualizaciones/comprobar_al_iniciar", False, type=bool):
            return
        last_checked = self.preferences.value("actualizaciones/ultima_comprobacion", 0, type=int)
        if int(time.time()) - last_checked < 86400:
            return
        self.check_updates(silent=True)

    def show_update_dialog(self, release):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Actualización disponible"))
        dialog.setText(
            tr("Ya está disponible {0} {1}. Tienes instalada la versión {2}.").format(
                APP_NAME, release.version, APP_VERSION
            )
        )
        details = []
        if release.notes:
            details.append(release.notes)
        if release.sha256:
            details.append(f"SHA-256: {release.sha256}")
        if details:
            dialog.setInformativeText("\n\n".join(details))
        open_release = dialog.addButton(tr("Abrir página de descarga"), QMessageBox.ButtonRole.AcceptRole)
        skip_release = dialog.addButton(tr("Omitir esta versión"), QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton(tr("Ahora no"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == skip_release:
            self.preferences.setValue("actualizaciones/version_omitida", release.version)
            self.preferences.sync()
        elif clicked == open_release and not QDesktopServices.openUrl(QUrl(release.url)):
            QMessageBox.warning(self, tr("Actualizaciones"), tr("No se pudo abrir la página de descarga."))

    def check_updates(self, silent=False):
        if is_store_package():
            if not silent:
                dialog = QMessageBox(self)
                dialog.setWindowTitle(tr("Actualizaciones"))
                dialog.setText(
                    tr("Tienes {0} {1}. Las actualizaciones de esta versión se gestionan automáticamente desde Microsoft Store.").format(
                        APP_NAME, APP_VERSION
                    )
                )
                open_store = dialog.addButton(tr("Abrir Microsoft Store"), QMessageBox.ButtonRole.AcceptRole)
                dialog.addButton(tr("Cerrar"), QMessageBox.ButtonRole.RejectRole)
                dialog.exec()
                if dialog.clickedButton() == open_store:
                    QDesktopServices.openUrl(QUrl(STORE_PROTOCOL_URL))
            return
        if not silent and self.job is not None:
            return
        if silent and self.update_job is not None:
            return
        try:
            channel = update_channel()
        except (OSError, ValueError) as error:
            if not silent:
                QMessageBox.warning(self, tr("Actualizaciones"), str(error))
            return
        if not channel:
            if not silent:
                QMessageBox.information(
                    self,
                    tr("Actualizaciones"),
                    tr("Tienes {0} {1}. Esta compilación aún no tiene un canal de publicación.").format(
                        APP_NAME, APP_VERSION
                    ),
                )
            return

        def check(_):
            try:
                return latest_release(channel), None
            except (OSError, ValueError) as error:
                return None, str(error)

        if silent:
            def finish():
                job = self.update_job
                self.update_job = None
                if job is None or job.failure or job.result is None:
                    return
                release, error = job.result
                if error is not None:
                    return
                self.preferences.setValue("actualizaciones/ultima_comprobacion", int(time.time()))
                self.preferences.sync()
                if release is None:
                    return
                skipped = self.preferences.value("actualizaciones/version_omitida", "")
                if skipped == release.version:
                    return
                if self.isVisible():
                    self.show_update_dialog(release)

            job = Job(check, None, self)
            job.finished.connect(finish)
            self.update_job = job
            job.start()
            return

        def show(result):
            release, error = result
            self.note(tr("Consulta de actualizaciones terminada."))
            if error is not None:
                QMessageBox.warning(self, tr("Actualizaciones"), tr("No se pudo consultar el canal. ") + error)
                return
            self.preferences.setValue("actualizaciones/ultima_comprobacion", int(time.time()))
            self.preferences.sync()
            if release is None:
                QMessageBox.information(self, tr("Actualizaciones"), tr("Ya tienes la última versión ({0}).").format(APP_VERSION))
                return
            self.show_update_dialog(release)

        self.start_job(tr("Buscando actualizaciones…"), check, show, preserve_selection=True)

    def shortcut(self, keys, action):
        shortcut = QAction(self)
        shortcut.setShortcut(QKeySequence(keys))
        shortcut.triggered.connect(action)
        self.addAction(shortcut)
        self.actions.append(shortcut)

    def build_empty_state(self):
        surface = QWidget(objectName="emptyState")
        outer = QVBoxLayout(surface)
        outer.setContentsMargins(22, 22, 22, 22)
        outer.addStretch(1)
        card = QFrame(objectName="emptyCard")
        card.setMinimumWidth(460)
        card.setMaximumWidth(520)
        content = QVBoxLayout(card)
        content.setContentsMargins(34, 32, 34, 30)
        content.setSpacing(14)
        preview = QLabel(objectName="emptyIcon")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setFixedSize(58, 58)
        preview.setProperty("brandMark", ("papel-en-vuelo", 44))
        preview.setPixmap(brand_pixmap("papel-en-vuelo", 44))
        content.addWidget(preview)
        content.addWidget(QLabel(tr("Abre un PDF"), objectName="emptyHeading"))
        hint = QLabel(tr("Arrastra uno o varios PDF a esta ventana o elígelos de tu equipo."), objectName="muted")
        hint.setWordWrap(True)
        content.addWidget(hint)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(button("Abrir PDF", self.open_dialog, primary=True, glyph="folder-plus"))
        actions.addWidget(button("Unir varios PDF", self.merge_dialog, glyph="document"))
        actions.addStretch(1)
        content.addLayout(actions)
        self.welcome_offer = QFrame(objectName="welcomeOffer")
        self.welcome_offer.setMinimumHeight(90)
        welcome = QVBoxLayout(self.welcome_offer)
        welcome.setContentsMargins(0, 14, 0, 0)
        welcome.setSpacing(8)
        introduction = QLabel(tr("¿Es tu primera vez? Prueba con dos PDF de ejemplo."), objectName="muted")
        introduction.setWordWrap(True)
        welcome.addWidget(introduction)
        options = QHBoxLayout()
        options.addWidget(button("Ver bienvenida", self.start_tour, glyph="document"))
        options.addWidget(button("Ahora no", self.dismiss_welcome))
        options.addStretch(1)
        welcome.addLayout(options)
        content.addWidget(self.welcome_offer)
        self.welcome_offer.setVisible(not self.preferences.value("ayuda/bienvenida_resuelta", False, type=bool))
        self.recent_offer = QFrame(objectName="welcomeOffer")
        recent = QVBoxLayout(self.recent_offer)
        recent.setContentsMargins(0, 14, 0, 0)
        recent.setSpacing(8)
        recent_header = QHBoxLayout()
        recent_header.setContentsMargins(0, 0, 0, 0)
        recent_header.addWidget(QLabel(tr("Documentos recientes"), objectName="panelLabel"), 1)
        clear_recent = button("Limpiar", lambda: self.set_recent_files([]))
        clear_recent.setProperty("role", "flat")
        clear_recent.setToolTip(tr("Borrar historial de recientes"))
        recent_header.addWidget(clear_recent)
        recent.addLayout(recent_header)
        self.recent_rows = QVBoxLayout()
        self.recent_rows.setSpacing(6)
        recent.addLayout(self.recent_rows)
        content.addWidget(self.recent_offer)
        self.refresh_recent_files()
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        return surface

    def dismiss_welcome(self):
        self.preferences.setValue("ayuda/bienvenida_resuelta", True)
        self.preferences.sync()
        self.welcome_offer.hide()
        self.refresh_recent_files()

    def recent_files(self):
        values = self.preferences.value("archivos/recientes", []) or []
        if isinstance(values, str):
            values = [values]
        return [Path(value) for value in values]

    def set_recent_files(self, paths):
        self.preferences.setValue("archivos/recientes", [str(path) for path in paths])
        self.preferences.sync()
        self.refresh_recent_files()

    def remember_recent_file(self, path):
        if not path.is_relative_to(self.scratch):
            others = [other for other in self.recent_files() if other != path]
            self.set_recent_files([path, *others[:9]])

    def open_recent_file(self, path):
        if not path.is_file():
            self.set_recent_files([other for other in self.recent_files() if other != path])
            self.note(tr("El PDF ya no está en esa ubicación y se quitó de los recientes."))
            QMessageBox.information(self, tr("Documento no encontrado"),
                                    tr("El PDF ya no está en esa ubicación y se quitó de los recientes."))
            return
        self.open_path(path)

    def populate_recent_menu(self):
        self.recent_menu.clear()
        paths = self.recent_files()
        for path in paths:
            label = path.name
            if sum(other.name.casefold() == path.name.casefold() for other in paths) > 1:
                label = f"{label} · {path.parent.name}"
            action = self.recent_menu.addAction(label.replace("&", "&&"))
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked=False, file=path: self.open_recent_file(file))
        if paths:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction(tr("Borrar historial de recientes"), lambda: self.set_recent_files([]))
        else:
            self.recent_menu.addAction(tr("Aún no hay documentos recientes")).setEnabled(False)

    def refresh_recent_files(self):
        while self.recent_rows.count():
            old = self.recent_rows.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        paths = self.recent_files()[:5 if self.welcome_offer.isHidden() else 3]
        for path in paths:
            item = button("", lambda file=path: self.open_recent_file(file))
            item.setProperty("role", "recentCard")
            item.setToolTip(str(path))
            item.setFixedHeight(52)
            item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row = QHBoxLayout(item)
            row.setContentsMargins(10, 6, 10, 6)
            row.setSpacing(10)
            badge = QLabel()
            badge.setPixmap(icon("document", 20).pixmap(20, 20))
            badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            row.addWidget(badge)
            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(1)
            title = QLabel(path.name)
            title.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent;")
            title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            meta_parts = [path.parent.name or str(path.parent)]
            try:
                if path.is_file():
                    meta_parts.append(file_size_label(path.stat().st_size))
            except OSError:
                pass
            subtitle = QLabel(" · ".join(meta_parts), objectName="muted")
            subtitle.setStyleSheet("font-size: 11px; background: transparent;")
            subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            text_col.addWidget(title)
            text_col.addWidget(subtitle)
            row.addLayout(text_col, 1)
            arrow = QLabel()
            arrow.setPixmap(icon("chevron-right", 16).pixmap(16, 16))
            arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            row.addWidget(arrow)
            self.recent_rows.addWidget(item)
        self.recent_offer.setMinimumHeight(34 + 58 * len(paths) if paths else 0)
        self.recent_offer.setVisible(bool(paths))

    def build_tour_strip(self):
        self.tour_panel = panel = QFrame(objectName="tourStrip")
        row = QHBoxLayout(panel)
        row.setContentsMargins(12, 7, 12, 7)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.tour_title = QLabel(objectName="tourTitle")
        self.tour_instruction = QLabel()
        self.tour_instruction.setTextFormat(Qt.TextFormat.PlainText)
        self.tour_instruction.setWordWrap(True)
        self.tour_instruction.setMinimumHeight(52)
        self.tour_instruction.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        copy.addWidget(self.tour_title)
        copy.addWidget(self.tour_instruction)
        row.addLayout(copy, 1)
        self.tour_action = button("", self.advance_tour, primary=True)
        self.tour_back = button("Anterior", lambda: self.set_tool_tour_step(self.tool_tour_index - 1))
        self.tour_back.hide()
        self.tour_exit = button("Salir de la visita", self.finish_tour)
        row.addWidget(self.tour_back)
        row.addWidget(self.tour_action)
        row.addWidget(self.tour_exit)
        panel.hide()
        return panel

    def start_tour(self):
        if self.tour_step or self.tool_tour_index is not None:
            return
        self.show_welcome_guide(guided=True)

    def open_welcome_guide(self):
        self.show_welcome_guide(guided=False)

    def show_welcome_guide(self, *, guided):
        window = PDFiu()
        try:
            folder = window.scratch / "visita"
            folder.mkdir()
            assets = ROOT / "assets" / "bienvenida"
            names = (("Welcome to PDFiu.pdf", "Practice appendix.pdf") if current_language() == "en" else
                     ("Bienvenida a PDFiu.pdf", "Anexo de ejemplo.pdf"))
            paths = tuple(folder / name for name in (names if guided else names[:1]))
            for path in paths:
                copyfile(assets / path.name, path)
            window.new_work_document(paths[0], page=0 if guided else 1)
        except Exception as error:
            window.temp.cleanup()
            window.deleteLater()
            self.error(tr("No se pudo abrir la bienvenida. {0}").format(error))
            return
        window.welcome_offer.hide()
        if guided:
            self.dismiss_welcome()
            window.tour_paths = paths
            window.set_tour_step(1)
        else:
            window.set_tool_tour_step(0)
        window.view.fit_width()
        self.show_new_window(window)

    def set_tour_step(self, step):
        self.tour_step = step
        title, instruction, action = (
            (tr("Abrir"), tr("Ya tienes la bienvenida abierta. Abre el anexo para tener dos PDF en la mesa."), tr("Abrir el anexo")),
            (tr("Seleccionar"), tr("Marca las casillas resaltadas para seleccionar los dos PDF de ejemplo."), ""),
            (tr("Unir"), tr("En Herramientas, pulsa Unir PDFs. Revisa el orden y confirma."), ""),
            (tr("Guardar"), tr("Pulsa Guardar y elige dónde quieres dejar el PDF unido."), ""),
            (tr("PDF guardado"), tr("Guardaste el PDF en {0}. Continúa para conocer las herramientas principales.").format(self.tour_destination), tr("Continuar con las herramientas")),
        )[step - 1]
        self.tour_title.setText(tr("{0} de 4 · {1}").format(step, title) if step < 5 else title)
        self.tour_instruction.setText(instruction)
        self.tour_action.setText(action)
        self.tour_action.setVisible(bool(action))
        self.tour_exit.setText(tr("Terminar") if step == 5 else tr("Salir de la visita"))
        self.tour_panel.show()
        self.schedule_tour_highlight()

    def tool_tour_entries(self):
        return (
            ("Unir PDFs", "Unir PDFs", "Selecciona los PDF en Archivos y pulsa Unir PDFs. Revisa su orden antes de crear el resultado."),
            ("Exportar", "Exportar", "Abre Exportar y elige Word, Excel, Markdown u otro formato."),
            ("Copiar una página como imagen", "Exportar", "Abre Exportar. Usa Copiar página como imagen o Imagen PNG."),
            ("Firmar con certificado", "Firmar con certificado", "Aquí dibujas el recuadro y eliges el certificado digital."),
            ("Firmar varios PDF", "Firmar lote…", "Aquí eliges los archivos y la posición de cada firma."),
            ("Desbloquear PDF", "Desbloquear PDF", "Usa este botón para crear una copia desbloqueada."),
            ("Encabezados y pies", "Encabezados y pies", "Aquí eliges el texto, su posición y las páginas donde se aplica."),
            ("Numerar páginas", "Numerar páginas…", "Aquí eliges el número inicial, la posición y las páginas."),
            ("Censurar datos", "Censurar datos", "Abre este menú para marcar zonas y guardar una copia censurada."),
            ("Extraer páginas", "Más herramientas", "Abre Más herramientas para extraer páginas a un PDF independiente."),
            ("Añadir páginas arrastrando", "drag-pages", "Arrastra un PDF desde el Explorador entre las miniaturas. También puedes arrastrar páginas entre dos ventanas de PDFiu."),
            ("Comprimir archivo", "Comprimir PDF…", "Elige un nivel de compresión, estima el tamaño y comprueba la copia antes de guardarla."),
        )

    def set_tool_tour_step(self, index):
        entries = self.tool_tour_entries()
        if not 0 <= index < len(entries):
            self.finish_tour()
            return
        self.tool_tour_index = index
        title, key, instruction = entries[index]
        if key == "drag-pages":
            self.set_navigation(True)
            self.navigation.setCurrentIndex(1)
            self.tool_tour_target = self.pages
            self.tool_tour_group = None
            menu = None
        else:
            group, self.tool_tour_target = next((group, tool) for group, tool in self.tool_library
                                                if tool.property("sourceLabel") == key)
            self.tool_tour_group = next(button for button in self.tool_group.buttons() if button.text() == group)
            self.tool_tour_group.click()
            self.show_selection_tools()
            self.tool_pages.currentWidget().ensureWidgetVisible(self.tool_tour_target, 0, 8)
            menu = self.tool_tour_target.menu()
        if menu is not None and not hasattr(menu, "tour_spotlight"):
            menu.tour_spotlight = TourSpotlight(menu)
            menu.aboutToShow.connect(lambda: QTimer.singleShot(0, menu, lambda: self.highlight_tour_menu(menu)))
            menu.aboutToHide.connect(menu.tour_spotlight.hide)
        self.tour_title.setText(tr("{0} de {1} · {2}").format(index + 1, len(entries), tr(title)))
        self.tour_instruction.setText(tr(instruction))
        self.tour_back.setVisible(index > 0)
        self.tour_action.setText(tr("Terminar") if index == len(entries) - 1 else tr("Siguiente"))
        self.tour_action.show()
        self.tour_exit.setText(tr("Salir de la visita"))
        self.tour_panel.show()
        self.schedule_tour_highlight()

    def highlight_tour_menu(self, menu):
        if not menu.isVisible() or self.tool_tour_target is None or self.tool_tour_target.menu() is not menu:
            return
        key = self.tool_tour_entries()[self.tool_tour_index][1]
        label = {"Exportar": "Copiar página al portapapeles" if self.tool_tour_index == 2 else "Word (.docx)…",
                 "Censurar datos": "Marcar zonas para censurar"}.get(key)
        if label is not None:
            action = next((action for action in menu.actions() if action.text() == tr(label) and action.isVisible()), None)
            if action is not None:
                menu.tour_spotlight.highlight([(menu, menu.actionGeometry(action))])

    def advance_tour(self):
        if self.tool_tour_index is not None:
            self.set_tool_tour_step(self.tool_tour_index + 1)
        elif self.tour_step == 1:
            try:
                self.open_path(self.tour_paths[1], remember_recent=False)
                if self.path == self.tour_paths[1]:
                    self.navigation.setCurrentWidget(self.work_tab)
                    self.set_navigation(True)
                    self.set_tour_step(2)
            except Exception as error:
                self.error(error)
        elif self.tour_step == 5:
            self.tour_step = 0
            self.set_tool_tour_step(0)

    def update_tour_selection(self):
        if self.tour_step not in (2, 3):
            return
        keys = (item.data(Qt.ItemDataRole.UserRole) for item in self.work_list.selectedItems())
        selected = {self.work_docs[key].path for key in keys if key in self.work_docs}
        step = 3 if self.batch_selection_count() == 2 and selected == set(self.tour_paths) else 2
        if step != self.tour_step:
            self.set_tour_step(step)
            if step == 3:
                group = self.tool_group.button(0)
                group.click()
                self.show_selection_tools()
                self.tool_pages.currentWidget().ensureWidgetVisible(self.merge_btn, 0, 8)
        self.schedule_tour_highlight()

    def finish_tour(self):
        self.tour_step = 0
        self.tool_tour_index = None
        self.tool_tour_target = None
        self.tour_panel.hide()
        self.tour_spotlight.hide()

    def schedule_tour_highlight(self, *_):
        if (self.tour_step or self.tool_tour_index is not None) and hasattr(self, "tour_highlight_timer"):
            self.tour_highlight_timer.start()

    def tour_tool_anchor(self, group, tool):
        if tool is self.pages:
            if self.navigation_column.isHidden():
                return self.navigation_toggle, None
            if self.navigation.currentIndex() != 1:
                return self.navigation.tabBar(), self.navigation.tabBar().tabRect(1)
            return self.pages.viewport(), None
        if self.tools.isHidden():
            return self.tool_toggle, None
        if self.tool_pages.currentIndex() != self.tool_group.id(group):
            return group, None
        return tool, None

    def refresh_tour_highlight(self):
        anchors = []
        if self.job is None:
            if self.tool_tour_index is not None:
                anchors = [self.tour_tool_anchor(self.tool_tour_group, self.tool_tour_target)]
            elif self.tour_step in (1, 5):
                anchors = [(self.tour_action, None)]
            elif self.tour_step == 2:
                if self.navigation_column.isHidden():
                    anchors = [(self.navigation_toggle, None)]
                elif self.navigation.currentWidget() is not self.work_tab:
                    tabs = self.navigation.tabBar()
                    anchors = [(tabs, tabs.tabRect(self.navigation.indexOf(self.work_tab)))]
                else:
                    for row in range(self.work_list.count()):
                        item = self.work_list.item(row)
                        state = self.work_docs.get(item.data(Qt.ItemDataRole.UserRole))
                        if state and state.path in self.tour_paths and not item.isSelected():
                            anchors.append((self.work_list.viewport(), self.work_list.checkbox_rect(item)))
            elif self.tour_step == 3:
                anchors = [self.tour_tool_anchor(self.tool_group.button(0), self.merge_btn)]
            elif self.tour_step == 4:
                if self.work_key == self.tour_result_key:
                    anchors = [(self.save_btn, None)]
                elif self.navigation_column.isHidden():
                    anchors = [(self.navigation_toggle, None)]
                elif self.navigation.currentWidget() is not self.work_tab:
                    tabs = self.navigation.tabBar()
                    anchors = [(tabs, tabs.tabRect(self.navigation.indexOf(self.work_tab)))]
                else:
                    for row in range(self.work_list.count()):
                        item = self.work_list.item(row)
                        if item.data(Qt.ItemDataRole.UserRole) == self.tour_result_key:
                            anchors = [(self.work_list.viewport(), self.work_list.visualItemRect(item))]
                            break
        self.tour_spotlight.highlight(anchors, keep_bright=self.tour_panel)

    def show_tool_group(self, index):
        if hasattr(self, "category_panel"):
            self.category_panel.move_to(self.tool_group.button(index), animate=True)
        if index == self.tool_pages.currentIndex():
            return
        self.view.finish_inline()
        self.clear_mode()
        self.tool_pages.setCurrentIndex(index)

    def persist_favorites(self):
        self.preferences.setValue("herramientas/favoritas", self.favorite_names)
        self.preferences.sync()
        self.refresh_favorites()
        if self.preferences.status() != QSettings.Status.NoError:
            self.note(tr("Los favoritos están disponibles en esta sesión. No se pudieron guardar las preferencias."))

    def refresh_favorites(self):
        while self.favorite_rows.count():
            entry = self.favorite_rows.takeAt(0)
            widget = entry.widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.favorite_controls.clear()
        available = {tool.property("sourceLabel"): tool for _, tool in self.tool_library}
        for name in self.favorite_names:
            original = available.get(name)
            if original is None:
                continue
            favorite = button(name, original.click)
            favorite.setIcon(original.icon())
            favorite.setProperty("role", "tool")
            favorite.setEnabled(original.isEnabled())
            if original.menu():
                favorite.setMenu(original.menu())
            favorite.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            favorite.customContextMenuRequested.connect(lambda point, tool=favorite: self.tool_context(tool, point))
            self.favorite_controls[name] = (favorite, original)
            self.favorite_rows.addWidget(favorite)
        if not self.favorite_controls:
            hint = QLabel(tr("Elige tus herramientas habituales o haz clic derecho sobre una para guardarla."), objectName="muted")
            hint.setWordWrap(True)
            self.favorite_rows.addWidget(hint)
        self.favorite_rows.addStretch()
        if hasattr(self, "work_list"):
            self.update_tool_scope()

    def tool_context(self, tool, point):
        name = tool.property("sourceLabel")
        menu = QMenu(self)
        added = name in self.favorite_names
        menu.addAction(tr("Quitar de favoritos") if added else tr("Añadir a favoritos"))
        if menu.exec(tool.mapToGlobal(point)):
            if added:
                self.favorite_names.remove(name)
            else:
                self.favorite_names.append(name)
            self.persist_favorites()
        menu.deleteLater()

    def choose_favorites(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Personalizar favoritos"))
        dialog.resize(420, 500)
        layout = QVBoxLayout(dialog)
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        groups, choices = {}, {}
        for group, tool in self.tool_library:
            if group not in groups:
                groups[group] = QTreeWidgetItem(tree, [group])
            name = tool.property("sourceLabel")
            choice = QTreeWidgetItem(groups[group], [tool.text()])
            choice.setCheckState(0, Qt.CheckState.Checked if name in self.favorite_names else Qt.CheckState.Unchecked)
            choices[name] = choice
        tree.expandAll()
        layout.addWidget(tree)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Guardar favoritos"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            selected = [name for name, item in choices.items() if item.checkState(0) == Qt.CheckState.Checked]
            self.favorite_names = [name for name in self.favorite_names if name in selected]
            self.favorite_names.extend(name for name in selected if name not in self.favorite_names)
            self.persist_favorites()

    def sync_tool_panel(self, *, animate=False):
        dock = next((item for item in (self.review_dock, self.surface_dock) if item.isVisible()), None)
        wide_or_open = self.width() >= self.compact_width or self.tools_compact_open
        visible = bool(self.path and self.fullscreen_state is None and self.focus_layout is None
                       and self.tools_requested and wide_or_open and dock is None)
        if animate and self.isVisible() and visible != self.tools.isVisible():
            if self._tool_panel_anim is not None:
                self._tool_panel_anim.stop()
            anim = QPropertyAnimation(self.tools, b"maximumWidth", self)
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            if visible:
                self.tools.setMaximumWidth(0)
                self.tools.show()
                anim.setStartValue(0)
                anim.setEndValue(self._tool_panel_width)
            else:
                anim.setStartValue(self.tools.width() or self._tool_panel_width)
                anim.setEndValue(0)
                anim.finished.connect(self.tools.hide)
            self._tool_panel_anim = anim
            anim.start()
        else:
            if self._tool_panel_anim is not None:
                self._tool_panel_anim.stop()
            self.tools.setMaximumWidth(self._tool_panel_width if visible else 0)
            self.tools.setVisible(visible)
        self.tool_toggle.setChecked(visible)
        self.update_workspace_hint()
        if dock is not None:
            self.resizeDocks([dock], [226], Qt.Orientation.Horizontal)

    def toggle_tool_panel(self):
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
        if self.focus_layout is not None:
            self.toggle_focus()
            for dock in (self.review_dock, self.surface_dock):
                dock.hide()
            self.tools_requested = True
            self.tools_compact_open = True
            self.sync_tool_panel(animate=True)
            return
        docks = self.review_dock, self.surface_dock
        if any(dock.isVisible() for dock in docks):
            for dock in docks:
                dock.hide()
            self.tools_requested = True
        else:
            self.tools_requested = self.tools.isHidden()
        self.tools_compact_open = self.tools_requested
        self.sync_tool_panel(animate=True)

    def toggle_navigation(self):
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
        if self.focus_layout is not None:
            self.toggle_focus()
            self.set_navigation(True, animate=True)
            return
        self.set_navigation(self.navigation_column.isHidden(), animate=True)

    def set_navigation(self, visible, *, animate=False):
        self.navigation_requested = visible
        self.sync_navigation(animate=animate)
        self.update_tool_scope()
        self.schedule_thumbnails()

    def _animate_nav_column(self, visible):
        if self._nav_anim is not None:
            self._nav_anim.stop()
        if not self.isVisible() or visible == self.navigation_column.isVisible():
            if visible:
                self.navigation_column.setMinimumWidth(220)
                self.navigation_column.setMaximumWidth(640)
            self.navigation_column.setVisible(visible)
            return
        anim = QPropertyAnimation(self.navigation_column, b"maximumWidth", self)
        anim.setDuration(190)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if visible:
            target = max(220, min(640, self._nav_last_width or 260))
            self.navigation_column.setMinimumWidth(0)
            self.navigation_column.setMaximumWidth(0)
            self.navigation_column.show()
            anim.setStartValue(0)
            anim.setEndValue(target)
            def finish_open():
                self.navigation_column.setMinimumWidth(220)
                self.navigation_column.setMaximumWidth(640)
                self.position_viewer_hud()
            anim.finished.connect(finish_open)
        else:
            current = self.navigation_column.width()
            if current >= 220:
                self._nav_last_width = current
            self.navigation_column.setMinimumWidth(0)
            anim.setStartValue(max(1, current))
            anim.setEndValue(0)
            def finish_close():
                self.navigation_column.hide()
                self.navigation_column.setMinimumWidth(220)
                self.navigation_column.setMaximumWidth(640)
                self.position_viewer_hud()
            anim.finished.connect(finish_close)
        self._nav_anim = anim
        anim.start()

    def _animate_rail(self, visible):
        if self._rail_anim is not None:
            self._rail_anim.stop()
        if not self.isVisible() or visible == self.navigation_shell.isVisible():
            self.navigation_shell.setMinimumWidth(46 if visible else 0)
            self.navigation_shell.setMaximumWidth(46 if visible else 0)
            self.navigation_shell.setVisible(visible)
            return
        anim = QPropertyAnimation(self.navigation_shell, b"maximumWidth", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.navigation_shell.setMinimumWidth(0)
        if visible:
            self.navigation_shell.setMaximumWidth(0)
            self.navigation_shell.show()
            anim.setStartValue(0)
            anim.setEndValue(46)
            anim.finished.connect(lambda: (self.navigation_shell.setMinimumWidth(46), self.navigation_shell.setMaximumWidth(46)))
        else:
            anim.setStartValue(self.navigation_shell.width() or 46)
            anim.setEndValue(0)
            anim.finished.connect(self.navigation_shell.hide)
        self._rail_anim = anim
        anim.start()

    def _fade_navigation_panel(self):
        widget = self.navigation.currentWidget()
        if widget is None or not self.navigation_column.isVisible():
            return
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.25)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.25)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None) if w is not None else None)
        self._nav_fade_anim = anim
        anim.start()

    def _set_hud_opacity(self, target):
        if not hasattr(self, "_hud_anim"):
            return
        self._hud_anim.stop()
        self._hud_anim.setStartValue(self._hud_opacity.opacity())
        self._hud_anim.setEndValue(target)
        self._hud_anim.start()

    def _wake_viewer_hud(self, *, sticky=False):
        if not hasattr(self, "viewer_hud") or not self.viewer_hud.isVisible():
            return
        self._set_hud_opacity(1.0)
        if sticky or self._hud_hovered or self.page_number.hasFocus() or self.hud_zoom_btn.menu().isVisible():
            self._hud_idle_timer.stop()
        else:
            self._hud_idle_timer.start()

    def _dim_viewer_hud(self):
        if not hasattr(self, "viewer_hud") or not self.viewer_hud.isVisible():
            return
        if self._hud_hovered or self.page_number.hasFocus() or self.hud_zoom_btn.menu().isVisible():
            return
        self._set_hud_opacity(0.42)

    def position_viewer_hud(self):
        hud = getattr(self, "viewer_hud", None)
        if hud is None or not hud.isVisible():
            return
        host = self.canvas
        hud.adjustSize()
        width = min(hud.sizeHint().width(), max(200, host.width() - 24))
        height = hud.sizeHint().height()
        x = max(12, (host.width() - width) // 2)
        y = max(12, host.height() - height - 18)
        hud.setGeometry(x, y, width, height)
        hud.raise_()

    def sync_navigation(self, *, animate=False):
        visible = bool(self.path and self.fullscreen_state is None and self.navigation_requested)
        if animate:
            self._animate_nav_column(visible)
        else:
            if self._nav_anim is not None:
                self._nav_anim.stop()
            if visible:
                self.navigation_column.setMinimumWidth(220)
                self.navigation_column.setMaximumWidth(640)
            self.navigation_column.setVisible(visible)
        self.navigation_toggle.setChecked(visible)
        rail = self.fullscreen_state is None and self.focus_layout is None
        if animate:
            self._animate_rail(rail)
        else:
            if self._rail_anim is not None:
                self._rail_anim.stop()
            self.navigation_shell.setMinimumWidth(46 if rail else 0)
            self.navigation_shell.setMaximumWidth(46 if rail else 0)
            self.navigation_shell.setVisible(rail)
        if hasattr(self, "viewer_hud"):
            show_hud = bool(self.path)
            was_visible = self.viewer_hud.isVisible()
            self.viewer_hud.setVisible(show_hud)
            if show_hud:
                self.position_viewer_hud()
                if not was_visible:
                    self._wake_viewer_hud()
            self.update_page_controls()
        if hasattr(self, "rail_buttons"):
            active_btn = None
            for panel, btn in self.rail_buttons.items():
                btn.setEnabled(self.job is None and (self.path is not None or panel is self.work_tab))
                is_active = visible and self.navigation.currentWidget() is panel
                btn.setChecked(is_active)
                if is_active:
                    active_btn = btn
            if hasattr(self.navigation_rail, "move_indicator"):
                self.navigation_rail.move_indicator(active_btn, animate=animate or self.isVisible())
        self.schedule_navigator()

    @staticmethod
    def reader_button_pair(first, second):
        pair = QWidget(objectName="readerGroup")
        layout = QVBoxLayout(pair)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(first)
        layout.addWidget(second)
        return pair

    def navigation_panel(self, title, *widgets):
        panel = QWidget(objectName="sidebar")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 11, 10, 10)
        header = QHBoxLayout()
        header.addWidget(QLabel(tr(title), objectName="panelLabel"), 1)
        header.addWidget(icon_button(tr("Cerrar panel"), "close", lambda: self.set_navigation(False, animate=True)))
        layout.addLayout(header)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, int(index == len(widgets) - 1))
        self.navigation.addTab(panel, tr(title))
        return panel

    def choose_navigation(self, panel, *, toggle=False, refresh=True):
        if self.path is None or self.job is not None:
            return
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
        if self.focus_layout is not None:
            self.toggle_focus()
        if toggle and self.navigation.currentWidget() is panel and self.navigation_requested:
            self.set_navigation(False, animate=True)
            return
        changed = self.navigation.currentWidget() is not panel
        self.navigation.setCurrentWidget(panel)
        self.set_navigation(True, animate=True)
        if changed:
            self._fade_navigation_panel()
        if refresh:
            self.refresh_navigation_panel()

    def refresh_navigation_panel(self):
        if self.path is None or self.job is not None or self.navigation_column.isHidden():
            return
        panel = self.navigation.currentWidget()
        if panel is self.bookmarks_panel:
            self.load_bookmarks(self.document_reader)
        elif panel is self.layers_panel:
            self.load_layer_panel()
        elif panel is self.comments_panel:
            self.open_comments()
        elif panel is self.signatures_panel:
            self.signature_explorer()

    def toggle_focus(self):
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
            if self.focus_layout is not None:
                return
        docks = self.review_dock, self.surface_dock
        if self.focus_layout is None:
            self.focus_layout = not self.navigation_column.isHidden(), [dock for dock in docks if dock.isVisible()]
            self.set_navigation(False, animate=True)
            for dock in docks:
                dock.hide()
        else:
            navigation_visible, open_docks = self.focus_layout
            self.focus_layout = None
            self.set_navigation(navigation_visible, animate=True)
            for dock in open_docks:
                dock.show()
                dock.raise_()
        self.focus_toggle.setChecked(self.focus_layout is not None)
        self.focus_toggle.setText(tr("Salir del enfoque") if self.focus_layout is not None else tr("Enfocar"))
        self.focus_toggle.setToolTip(f"{self.focus_toggle.text()} (F9)")
        self.sync_tool_panel(animate=True)

    def toggle_two_page(self, enabled=None):
        if enabled is None:
            enabled = not self.view.two_page
        for action in (self.menu_two_page, self.size_two_page_action):
            with QSignalBlocker(action):
                action.setChecked(bool(enabled))
        if hasattr(self, "hud_two_page_btn"):
            with QSignalBlocker(self.hud_two_page_btn):
                self.hud_two_page_btn.setChecked(bool(enabled))
        self.view.set_two_page(bool(enabled))

    def toggle_fullscreen(self):
        if self.fullscreen_state is None:
            if self.path is None:
                return
            docks = (self.review_dock, self.surface_dock)
            self.fullscreen_state = (self.windowState(), [dock for dock in docks if dock.isVisible()])
            for dock in docks:
                dock.hide()
            self.shell_bar.hide()
            self.menuBar().hide()
            self.showFullScreen()
        else:
            window_state, docks = self.fullscreen_state
            self.fullscreen_state = None
            self.setWindowState(window_state)
            self.shell_bar.show()
            self.menuBar().show()
            for dock in docks:
                if self.path:
                    dock.show()
                    dock.raise_()
        self.sync_navigation()
        self.sync_toolbar()
        self.sync_tool_panel()

    def escape_view(self):
        if self.find_bar.isVisible():
            self.close_find_bar()
        elif self.fullscreen_state is not None:
            self.toggle_fullscreen()
        elif self.view.copied_text.strip():
            self.view.clear_text()
        else:
            self.clear_mode()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "document_controls"):
            return
        if event.oldSize().width() >= self.compact_width > event.size().width():
            self.tools_compact_open = False
        self.sync_toolbar()
        self.sync_tool_panel()

    def sync_toolbar(self):
        has_document = bool(self.path)
        fullscreen = self.fullscreen_state is not None
        if fullscreen and not has_document:
            self.toggle_fullscreen()
            return
        for control in (self.navigation_toggle, self.tool_toggle, self.search_btn, self.save_btn,
                        self.save_copy_btn, self.close_pdf_btn, self.document_footer):
            control.setVisible(has_document)
        for control in (self.undo_btn, self.redo_btn):
            control.setVisible(has_document and self.width() >= self.compact_width)
        self.focus_toggle.setVisible(has_document and not fullscreen)
        self.fullscreen_toggle.setVisible(has_document)
        self.fullscreen_toggle.setText(tr("Salir de pantalla completa") if fullscreen else tr("Pantalla completa"))
        fullscreen_glyph = "arrows-collapse-full" if fullscreen else "maximize"
        self.fullscreen_toggle.setProperty("iconGlyph", (fullscreen_glyph, 16, False, False))
        self.fullscreen_toggle.setIcon(icon(fullscreen_glyph))
        self.fullscreen_toggle.setToolTip(tr("Salir con Esc o F11") if fullscreen else tr("Pantalla completa (F11)"))

    def eventFilter(self, watched, event):
        kind = event.type()
        if (hasattr(self, "tour_spotlight") and (self.tour_step or self.tool_tour_index is not None) and
                kind in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide,
                         QEvent.Type.LayoutRequest, QEvent.Type.EnabledChange) and isinstance(watched, QWidget) and
                not isinstance(watched, TourSpotlight) and (watched is self or self.isAncestorOf(watched))):
            self.schedule_tour_highlight()
        if watched is getattr(self, "thumbnail_viewport", None) and kind in (QEvent.Type.Resize, QEvent.Type.Show):
            self.schedule_thumbnails()
        elif watched is getattr(self, "name_label", None) and kind == QEvent.Type.Resize:
            self.elide_file_title()
        hud = getattr(self, "viewer_hud", None)
        if watched is getattr(self, "canvas", None) and kind in (QEvent.Type.Resize, QEvent.Type.Show):
            self.position_viewer_hud()
        if hud is not None and watched is hud:
            if kind == QEvent.Type.Enter:
                self._hud_hovered = True
                self._wake_viewer_hud(sticky=True)
            elif kind == QEvent.Type.Leave:
                self._hud_hovered = False
                self._wake_viewer_hud(sticky=False)
        view = getattr(self, "view", None)
        if view is not None:
            if kind == QEvent.Type.KeyPress and isinstance(watched, QWidget) and watched.window() is self:
                if self.handle_page_keys(watched, event):
                    return True
            if kind == QEvent.Type.Resize and watched is view.viewport():
                self.schedule_navigator()
                self.position_viewer_hud()
            elif kind == QEvent.Type.MouseMove and watched is view.viewport() and hud is not None and hud.isVisible():
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                if pos.y() >= view.viewport().height() - 105:
                    self._wake_viewer_hud(sticky=False)
            elif kind == QEvent.Type.WindowDeactivate and watched is self:
                view.stop_space_pan()
            elif kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) and event.key() == Qt.Key.Key_Space:
                if self.handle_space_pan(event):
                    return True
        return super().eventFilter(watched, event)

    def handle_page_keys(self, watched, event):
        key = event.key()
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                       Qt.Key.Key_Home, Qt.Key.Key_End):
            return False
        if not self.path or self.job is not None or int(event.modifiers().value) or QApplication.activePopupWidget():
            return False
        if self.view.inline_editor is not None:
            return False
        if isinstance(watched, (QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QAbstractItemView)) and watched is not self.view:
            return False
        for panel in (self.navigation, self.review_widget, self.surface_dock):
            if watched is not self.view and panel.isAncestorOf(watched):
                return False
        if key == Qt.Key.Key_Home:
            self.goto(0)
        elif key == Qt.Key.Key_End:
            self.goto(self.count - 1)
        else:
            self.goto(self.current + (-1 if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp) else 1))
        return True

    def handle_space_pan(self, event):
        if self.view.space_pan:
            if event.type() == QEvent.Type.KeyRelease and not event.isAutoRepeat():
                self.view.stop_space_pan()
            return True
        if (event.type() != QEvent.Type.KeyPress or event.isAutoRepeat() or QApplication.activeWindow() is not self or
                QApplication.activePopupWidget() is not None or
                event.modifiers() != Qt.KeyboardModifier.NoModifier or not self.view.isVisible() or
                not self.view.isEnabled()):
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox)):
            return False
        return bool((self.view.hasFocus() or self.view.viewport().underMouse()) and self.view.start_space_pan())

    def schedule_navigator(self, *_):
        if hasattr(self, "navigator_timer") and not self.navigator_timer.isActive():
            self.navigator_timer.start()

    def update_navigator(self):
        view = self.view
        frame = view.page_rect
        visible = view.mapToScene(view.viewport().rect()).boundingRect()
        clipped = not frame.isEmpty() and (frame.width() > visible.width() + 1 or frame.height() > visible.height() + 1)
        show = bool(self.path and clipped and not self.navigation_column.isHidden() and view.image_item is not None)
        self.navigator_panel.setVisible(show)
        if show:
            self.navigator_label.setText(tr("Navegador · página {0}").format(view.active_index + 1))
            self.navigator.show_position(view.image_item, frame, visible)
        else:
            self.navigator.show_position(None, QRectF(), QRectF())

    def center_from_navigator(self, point):
        page = self.view.page_rect
        self.view.centerOn(QPointF(max(page.left(), min(point.x(), page.right())),
                                   max(page.top(), min(point.y(), page.bottom()))))

    def schedule_thumbnails(self, *_):
        if self.path and self.job is None and self.pages.isVisible():
            self.thumbnail_timer.start()

    def render_visible_thumbnails(self):
        if not self.path or self.job is not None or not self.pages.isVisible():
            return
        viewport = self.pages.viewport()
        first = self.pages.indexAt(QPointF(3, 1).toPoint()).row()
        if first < 0:
            return
        pending = []
        visible = set()
        for row in range(first, self.pages.count()):
            item = self.pages.item(row)
            if self.pages.visualItemRect(item).top() >= viewport.height():
                break
            index = item.data(Qt.ItemDataRole.UserRole)
            visible.add(index)
            if index in self.thumbnail_cache:
                self.thumbnail_cache.move_to_end(index)
            else:
                pending.append(item)
        if pending:
            try:
                with pdfium_reader(self.path, password=self.document_password) as document:
                    for item in pending[:4]:
                        index = item.data(Qt.ItemDataRole.UserRole)
                        image = render_page(document, index, width=52)
                        item.setIcon(QIcon(QPixmap.fromImage(as_qimage(image))))
                        self.thumbnail_cache[index] = item
            except (OSError, ValueError, RuntimeError, IndexError):
                return
            if len(pending) > 4:
                self.schedule_thumbnails()
        for index in list(self.thumbnail_cache):
            if len(self.thumbnail_cache) <= max(48, len(visible)):
                break
            if index not in visible:
                self.thumbnail_cache.pop(index).setIcon(QIcon())

    def note(self, message):
        self.status.setText(message)
        self.status.setToolTip(message)

    def update_zoom_level(self, value):
        label = f"{value} %"
        self.zoom_level.setText(label)
        if hasattr(self, "hud_zoom_btn"):
            self.hud_zoom_btn.setText(label)
            self.position_viewer_hud()
            self._wake_viewer_hud(sticky=False)

    def apply_zoom_level(self):
        value = self.zoom_level.text().strip().removesuffix("%").strip()
        current = self.view.percent()
        if value.isdecimal() and 1 <= int(value) <= 1000 and int(value) != current:
            self.view.set_percent(int(value))
        else:
            self.update_zoom_level(current)

    def copy_text(self):
        if self.job is None:
            self.view.copy_text()

    def update_text_selection(self, selected):
        self.menu_copy_text.setEnabled(selected and self.job is None)
        if selected:
            self.note(tr("Texto seleccionado. Pulsa Ctrl+C o haz clic derecho para copiar."))

    def error(self, message):
        if isinstance(message, Exception):
            message = str(message) or type(message).__name__
        self.note(tr("La operación quedó sin aplicar."))
        QMessageBox.warning(self, APP_NAME, str(message))

    def enable_controls(self):
        active = self.job is None
        has_document = self.path is not None
        self.menu_copy_text.setEnabled(active and bool(self.view.copied_text.strip()))
        for control in self.document_controls:
            control.setEnabled(active and has_document)
        self.sync_toolbar()
        self.sync_navigation()
        self.sync_tool_panel()
        self.mark_active_work_item()
        self.open_btn.setEnabled(active)
        self.menu_open.setEnabled(active)
        self.menu_document_folder.setEnabled(active and has_document and bool(self.saved_path or self.protected_source))
        self.menu_reload.setEnabled(active and has_document and bool(self.saved_path or self.protected_source))
        self.menu_update.setEnabled(active)
        self.merge_btn.setEnabled(active)
        self.unlock_btn.setEnabled(active and self.path is not None)
        self.batch_btn.setEnabled(active)
        self.update_tool_scope()
        self.remove_btn.setEnabled(active and self.count > 1)
        self.view.setEnabled(active)
        if not active:
            self.view.stop_space_pan()
        if active:
            self.view.schedule_pages()
            self.schedule_thumbnails()
        self.review_dock.setEnabled(active or self.search_job)
        self.review_widget.setEnabled(active or self.search_job)
        self.review_list.setEnabled(active)
        self.surface_dock.setEnabled(active)
        self.tools.setEnabled(active)
        self.form_strip.setEnabled(active)
        self.signature_strip.setEnabled(active)
        self.redaction_strip.setEnabled(active)
        self.navigation.setEnabled(active)
        self.undo_btn.setEnabled(active and bool(self.undo_versions.get(self.work_key)))
        self.redo_btn.setEnabled(active and bool(self.redo_versions.get(self.work_key)))
        self.menu_undo.setEnabled(self.undo_btn.isEnabled())
        self.menu_redo.setEnabled(self.redo_btn.isEnabled())

    def scratch_path(self):
        return self.scratch / f"{uuid4().hex}.pdf"

    def load(self, path, *, name=None, dirty=False, page=0, preserve_previous=False, initial_fit=None, password=None):
        path = Path(path)
        if dirty and path != self.path and self.redaction_boxes and not preserve_previous:
            raise ValueError(tr("Guarda la copia censurada o quita las marcas antes de modificar el PDF."))
        reader = reader_for(path, allow_empty_password=True, password=password)
        count = len(reader.pages)
        page = max(0, min(page, count - 1))
        with pdfium_reader(path, password=password) as document:
            sizes = [document.get_page_size(index) for index in range(count)]
        previous = self.path
        record = (not preserve_previous and dirty and self.work_key is not None and previous and previous != path)
        if record:
            history = self.undo_versions.setdefault(self.work_key, [])
            history.append(self.history_snapshot())
            obsolete = self.redo_versions.pop(self.work_key, [])
            if len(history) > 20:
                obsolete.append(history.pop(0))
            for state in obsolete:
                if state.path.parent == self.scratch:
                    state.path.unlink(missing_ok=True)
        self.path, self.count, self.current = path, count, page
        self.document_reader = reader
        self.document_password = password
        self.update_signature_strip(reader)
        if not dirty:
            self.saved_path = path
            self.protected_source = None
        self.name = name or path.name
        self.dirty = dirty
        if previous != path or preserve_previous:
            self.redaction_boxes.clear()
        self.layer_timer.stop()
        layer_preview_path = self.layer_view_path
        self.layer_source = self.layer_view_path = None
        self.signature_cache_key = None
        self.pages.blockSignals(True)
        self.thumbnail_cache.clear()
        self.pages.clear()
        for index in range(count):
            item = QListWidgetItem(tr("Página {0}").format(index + 1))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(QSize(120, 67))
            self.pages.addItem(item)
        self.pages.setCurrentRow(page)
        self.pages.blockSignals(False)
        self.canvas.setCurrentWidget(self.view)
        self.view.set_document(path, sizes, page, keep_position=previous is not None and not preserve_previous,
                               initial_fit=initial_fit, password=password)
        if layer_preview_path:
            layer_preview_path.unlink(missing_ok=True)
        self.review_list.clear()
        self.search_result_key = None
        self.search_hits = []
        self.search_cursor = -1
        if self.review_mode == "search" and not self.review_dock.isHidden():
            self.schedule_search()
        self.refresh_surfaces()
        self.clear_mode()
        self.update_labels()
        self.enable_controls()
        QTimer.singleShot(0, self, self.refresh_navigation_panel)
        if not preserve_previous and not record and previous and previous != path and previous.parent == self.scratch:
            previous.unlink(missing_ok=True)

    def document_snapshot(self):
        return WorkDocument(self.path, self.name, self.dirty, self.current, self.saved_path, self.protected_source,
                            {index: list(boxes) for index, boxes in self.redaction_boxes.items()}, self.document_password)

    def history_snapshot(self):
        state = self.document_snapshot()
        if state.path.parent != self.scratch:
            destination = self.scratch_path()
            copyfile(state.path, destination)
            state = replace(state, path=destination)
        return state

    def undo_edit(self):
        if self.view.inline_editor:
            return
        self.restore_history(self.undo_versions, self.redo_versions, tr("Cambio deshecho."))

    def redo_edit(self):
        if self.view.inline_editor:
            return
        self.restore_history(self.redo_versions, self.undo_versions, tr("Cambio rehecho."))

    def restore_history(self, source, target, message):
        if self.job is not None:
            return
        if self.redaction_boxes:
            self.note(tr("Guarda la copia censurada o quita las marcas antes de cambiar de versión."))
            return
        history = source.get(self.work_key)
        if not history:
            return
        state = history[-1]
        try:
            outgoing = self.history_snapshot()
            self.load(state.path, name=state.name, dirty=True, page=state.page, preserve_previous=True, password=state.password)
            self.saved_path = outgoing.saved_path or state.saved_path
            self.protected_source = state.protected_source or outgoing.protected_source
            self.redaction_boxes = {i: list(boxes) for i, boxes in state.redactions.items()}
            self.reset_calibrations()
            history.pop()
            target.setdefault(self.work_key, []).append(outgoing)
            self.stash_workspace()
            self.enable_controls()
            self.note(message)
        except Exception as error:
            self.error(error)

    def reset_calibrations(self):
        document = self.work_key or self.path
        for key in [key for key in self.calibrations if key[0] == document]:
            self.calibrations.pop(key)
        self.update_measure_scale()

    def update_labels(self):
        self.setWindowTitle(f"{self.name} · {APP_NAME}" if self.name else APP_NAME)
        self.elide_file_title()
        self.name_label.setToolTip(self.name)
        self.name_label.setAccessibleName(self.name)
        self.file_state.setVisible(self.dirty)
        self.page_number.setText(str(self.current + 1))
        self.update_page_controls()
        self.update_redaction_strip()
        self.update_measure_scale()
        self.stash_workspace()
        self.sync_doc_tabs()

    def update_page_controls(self):
        prefix = "" if self.reader_in_rail else "/ "
        self.page_label.setText(f"{prefix}{self.count}" if self.count else "")
        self.page_label.setAccessibleName(tr("Páginas") + f": {self.count}")
        available = self.path is not None and self.job is None
        self.previous_page_btn.setEnabled(available and self.current > 0)
        self.next_page_btn.setEnabled(available and self.current + 1 < self.count)
        if self.path is not None and self.count:
            self.footer_page_pill.setText(tr("Página {0} de {1}").format(self.current + 1, self.count))
            self.footer_page_pill.show()
        else:
            self.footer_page_pill.hide()

    def apply_page_number(self):
        text = self.page_number.text().strip()
        if text.isdecimal():
            self.goto(int(text) - 1)
        self.page_number.setText(str(self.current + 1))

    def elide_file_title(self):
        title = self.name_label
        title.setText(title.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideMiddle, title.contentsRect().width()))

    def show_selection_actions(self, position):
        self.selection_tools.adjustSize()
        viewport = self.view.viewport()
        width, height = self.selection_tools.width(), self.selection_tools.height()
        x = max(4, min(position.x(), viewport.width() - width - 4))
        below = position.y() + 12
        y = below if below + height <= viewport.height() else max(4, position.y() - height - 12)
        self.selection_tools.move(x, y)
        self.selection_tools.show()
        self.selection_tools.raise_()

    def update_redaction_strip(self):
        count = sum(map(len, self.redaction_boxes.values()))
        self.redaction_strip.setVisible(bool(count) or self.view.mode == "redact")
        self.redaction_save_btn.setEnabled(bool(count))
        self.redaction_label.setText(
            tr("Arrastra sobre el PDF para marcar una zona.") if not count else
            (tr("1 zona pendiente") if count == 1 else tr("{0} zonas pendientes").format(count)) +
            tr(" · Los datos aún son visibles en el PDF.")
        )

    def goto(self, index):
        if not self.path or self.job is not None or not 0 <= index < self.count or index == self.current:
            return
        self.view.finish_inline()
        try:
            self.view.jump(index)
        except Exception as error:
            self.error(error)

    def visible_page_changed(self, index, coordinates):
        changed = index != self.current
        self.current, self.coordinates = index, coordinates
        self.update_signature_targets(self.document_reader.pages[index], coordinates)
        self.update_link_targets(self.document_reader.pages[index], coordinates)
        if changed:
            self._wake_viewer_hud(sticky=False)
        self.pages.blockSignals(True)
        if index != self.pages.currentRow():
            selection = QItemSelectionModel.SelectionFlag
            flags = selection.NoUpdate if len(self.pages.selectedItems()) > 1 else selection.ClearAndSelect
            self.pages.setCurrentRow(index, flags)
        self.pages.blockSignals(False)
        if changed and (self.annotation_edit or (self.view.mode or "").startswith("measure-")):
            self.clear_mode()
            self.note(tr("Vuelve a elegir la herramienta para trabajar en esta página."))
        self.detect_form(self.document_reader)
        if self.view.mode == "signature":
            self.view.mark_boxes(coordinates, signature_boxes(self.document_reader.pages[index]))
        elif self.view.mode == "redact":
            self.view.mark_boxes(coordinates, self.redaction_boxes.get(index, ()))
        else:
            self.view.mark_boxes()
        self.update_labels()

    def update_signature_strip(self, reader):
        try:
            fields = (reader.get_fields() or {}).values() if reader else ()
            count = sum(1 for field in fields if field.get("/FT") == "/Sig" and signature_value(field.get("/V")))
        except Exception:
            count = 0
        self.signature_label.setText(tr("{0} firmas digitales detectadas").format(count) if count > 1 else tr("Firma digital detectada"))
        self.signature_details_btn.setText(tr("Ver firmas") if count > 1 else tr("Ver firma"))
        self.signature_strip.setVisible(bool(count))

    def update_signature_targets(self, page, coordinates):
        targets = []
        try:
            for name, (x1, y1, x2, y2), signed in signature_widgets(page):
                if signed and x1 < x2 and y1 < y2:
                    rect = QRectF(QPointF(*coordinates.device(x1, y1)),
                                  QPointF(*coordinates.device(x2, y2))).normalized()
                    targets.append((rect, name))
        except Exception:
            pass
        self.view.signature_targets = targets

    def _resolve_link_destination(self, dest):
        reader = self.document_reader
        if reader is None or dest is None:
            return None
        try:
            if hasattr(dest, "get_object"):
                dest = dest.get_object()
            if isinstance(dest, str):
                named = reader.named_destinations.get(dest)
                if named is not None:
                    return reader.get_destination_page_number(named)
                return None
            if isinstance(dest, (list, tuple)) and dest:
                target_page = dest[0]
                if hasattr(target_page, "get_object"):
                    target_page = target_page.get_object()
                if isinstance(target_page, int):
                    return target_page if 0 <= target_page < len(reader.pages) else None
                for idx, candidate in enumerate(reader.pages):
                    if candidate is target_page or getattr(candidate, "indirect_reference", None) == getattr(dest[0], "indirect_reference", dest[0]):
                        return idx
        except Exception:
            return None
        return None

    def update_link_targets(self, page, coordinates):
        targets = []
        try:
            annots = page.get("/Annots") or ()
            if hasattr(annots, "get_object"):
                annots = annots.get_object() or ()
            for raw in annots:
                annot = raw.get_object() if hasattr(raw, "get_object") else raw
                if not isinstance(annot, dict) or annot.get("/Subtype") != "/Link":
                    continue
                box = annot.get("/Rect")
                if not box or len(box) != 4:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box)
                if x1 >= x2 or y1 >= y2:
                    continue
                target = None
                if "/Dest" in annot:
                    page_idx = self._resolve_link_destination(annot.get("/Dest"))
                    if page_idx is not None:
                        target = ("page", page_idx)
                elif "/A" in annot:
                    action = annot.get("/A")
                    if hasattr(action, "get_object"):
                        action = action.get_object()
                    if isinstance(action, dict):
                        stype = action.get("/S")
                        if stype == "/GoTo":
                            page_idx = self._resolve_link_destination(action.get("/D"))
                            if page_idx is not None:
                                target = ("page", page_idx)
                        elif stype == "/URI" and action.get("/URI"):
                            target = ("uri", str(action.get("/URI")))
                if target is not None:
                    rect = QRectF(QPointF(*coordinates.device(x1, y1)),
                                  QPointF(*coordinates.device(x2, y2))).normalized()
                    targets.append((rect, target))
        except Exception:
            pass
        self.view.link_targets = targets

    def open_pdf_link(self, target):
        if not target or self.job is not None:
            return
        kind, value = target
        if kind == "page" and isinstance(value, int) and 0 <= value < self.count:
            self.goto(value)
            self._wake_viewer_hud(sticky=False)
        elif kind == "uri" and value:
            url = QUrl(str(value))
            if url.scheme().lower() in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)

    def clear_mode(self):
        self.measure_points.clear()
        self.pending_measure = None
        self.clear_measure_marks()
        self.annotation_edit = None
        self.view.set_mode(None)
        self.update_redaction_strip()
        self.view.mark_boxes()
        self.text_btn.setChecked(False)
        self.edit_text_btn.setChecked(False)
        self.pan_btn.setChecked(False)
        self.form_btn.setChecked(False)
        self.refresh_field_tint()
        self.note(tr("Arrastra sobre el texto y pulsa Ctrl+C para copiar.") if self.path else tr("Abre un PDF o arrástralo a la ventana."))

    def clear_measure_marks(self):
        for item in self.view.measure_marks:
            self.view.scene().removeItem(item)
        self.view.measure_marks.clear()

    def measure_key(self):
        return self.work_key or self.path, self.current

    def paper_meters_per_point(self):
        unit = float(self.document_reader.pages[self.current].get("/UserUnit", 1))
        return 0.0254 * unit / 72

    @staticmethod
    def default_measure_unit():
        metric = QLocale.system().measurementSystem() == QLocale.MeasurementSystem.MetricSystem
        return "m" if metric else "ft"

    def update_measure_scale(self):
        scale = self.calibrations.get(self.measure_key())
        self.scale_label.setVisible(scale is not None)
        if scale is not None:
            implied = scale.meters_per_point / self.paper_meters_per_point()
            self.scale_label.setText(tr("Escala 1:{0:.5g} · {1}").format(implied, scale.unit))

    def begin_calibration(self, resume=None):
        if not self.path or self.job is not None:
            return
        if self.view.mode == "measure-calibrate":
            self.clear_mode()
        self.select_mode("measure-calibrate")
        self.pending_measure = resume

    def enter_page_scale(self):
        if not self.path or self.job is not None:
            return False
        paper = self.paper_meters_per_point()
        existing = self.calibrations.get(self.measure_key(), PageCalibration(100 * paper, self.default_measure_unit()))
        current = existing.meters_per_point / paper
        denominator, accepted = QInputDialog.getDouble(
            self, tr("Introducir escala"), tr("Escala 1:N. Introduce N (por ejemplo, 100 para 1:100)."),
            current, 0.001, 1_000_000, 3,
        )
        if accepted:
            self.calibrations[self.measure_key()] = PageCalibration(denominator * paper, existing.unit)
            self.measure_points.clear()
            self.clear_measure_marks()
            self.update_measure_scale()
            self.note(tr("Escala 1:{0:.5g} aplicada a esta página.").format(denominator))
        return bool(accepted)

    def start_measure(self, kind):
        if not self.path or self.job is not None:
            return
        if self.measure_key() not in self.calibrations:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("Escala de medición"))
            dialog.setText(tr("Esta página aún no tiene escala."))
            dialog.setInformativeText(tr("Para obtener medidas reales, usa una cota conocida o la escala del plano."))
            calibrate = dialog.addButton(tr("Calibrar con dos puntos"), QMessageBox.ButtonRole.AcceptRole)
            manual = dialog.addButton(tr("Introducir escala 1:N…"), QMessageBox.ButtonRole.ActionRole)
            paper = dialog.addButton(tr("Medir en papel"), QMessageBox.ButtonRole.ActionRole)
            dialog.addButton(QMessageBox.StandardButton.Cancel).setText(tr("Cancelar"))
            dialog.setDefaultButton(calibrate)
            dialog.exec()
            chosen = dialog.clickedButton()
            if chosen is calibrate:
                self.begin_calibration(kind)
                return
            if chosen is manual:
                if not self.enter_page_scale():
                    return
            elif chosen is not paper:
                return
        self.select_mode(f"measure-{kind}")

    def calibration_distance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Distancia real entre los puntos"))
        dialog.setMinimumWidth(420)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        length = QDoubleSpinBox()
        length.setDecimals(3)
        length.setRange(0.001, 10_000_000)
        length.setValue(1)
        units = QComboBox()
        for symbol, (label, _) in MEASURE_UNITS.items():
            units.addItem(f"{label} ({symbol})", symbol)
        units.setCurrentIndex(units.findData(self.default_measure_unit()))
        layout.addRow(tr("Distancia"), length)
        layout.addRow(tr("Unidad"), units)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Aplicar escala"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        return (length.value(), units.currentData()) if dialog.exec() else None

    def measure_point(self, point):
        kind = self.view.mode.removeprefix("measure-")
        self.measure_points.append(self.coordinates.at(point.x(), point.y()))
        if len(self.measure_points) == 2 and kind in ("distance", "calibrate"):
            self.finish_measure()
        else:
            self.draw_measure()

    def draw_measure(self, *, close=False, label=""):
        self.clear_measure_marks()
        pixels = [QPointF(*self.coordinates.device(*point)) for point in self.measure_points]
        scene = self.view.scene()
        pen = QPen(QColor("#3569aa"), 2)
        pen.setCosmetic(True)
        for point in pixels:
            self.view.measure_marks.append(scene.addEllipse(point.x()-4, point.y()-4, 8, 8, pen))
        for start, end in zip(pixels, pixels[1:] + (pixels[:1] if close else [])):
            self.view.measure_marks.append(scene.addLine(start.x(), start.y(), end.x(), end.y(), pen))
        if label and pixels:
            item = scene.addSimpleText(label)
            item.setBrush(QColor("#203b50"))
            item.setPos(pixels[-1] + QPointF(9, 6))
            self.view.measure_marks.append(item)

    def finish_measure(self):
        mode = self.view.mode or ""
        if not mode.startswith("measure-"):
            return
        kind = mode.removeprefix("measure-")
        minimum = 2 if kind in ("distance", "calibrate") else 3
        if len(self.measure_points) < minimum:
            self.note(tr("Marca al menos {0} puntos.").format(minimum))
            return
        key = self.measure_key()
        if kind == "calibrate":
            points = measured_value(self.measure_points, "distance", 1)
            reference = self.calibration_distance() if points > 0 else None
            if reference is not None:
                distance, unit = reference
                self.calibrations[key] = PageCalibration(distance * MEASURE_UNITS[unit][1] / points, unit)
                self.update_measure_scale()
                self.draw_measure(label=f"{QLocale.system().toString(float(distance), 'f', 3)} {unit}")
                resume, self.pending_measure = self.pending_measure, None
                if resume:
                    self.select_mode(f"measure-{resume}")
                    instructions = tr("marca dos puntos.") if resume == "distance" else tr("marca los vértices y pulsa Ctrl+Enter.")
                    self.note(tr("Escala aplicada. Ahora {0}").format(instructions))
                else:
                    self.note(tr("Escala aplicada. Ya puedes medir distancias, superficies y perímetros en esta página."))
            elif points <= 0:
                self.note(tr("Los puntos deben estar separados para calibrar."))
        else:
            calibration = self.calibrations.get(key)
            fallback_unit = "mm" if self.default_measure_unit() == "m" else "in"
            unit = calibration.unit if calibration else fallback_unit
            meters = calibration.meters_per_point if calibration else self.paper_meters_per_point()
            area = kind in ("area", "surface")
            value = measured_value(self.measure_points, "area" if area else kind, meters / MEASURE_UNITS[unit][1])
            suffix = ("²" if area else "") + ("" if calibration else tr(" en papel"))
            label = f"{QLocale.system().toString(value, 'f', 3)} {unit}{suffix}"
            if kind == "surface":
                self.save_surface(value, unit + suffix)
            else:
                self.draw_measure(close=kind != "distance", label=label)
                self.note(label)
        self.measure_points.clear()

    def build_surface_dock(self):
        dock = QDockWidget(tr("Superficies"), self)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(button("Nueva superficie", lambda: self.start_measure("surface"), glyph="plus"))
        options = QFormLayout()
        self.surface_color = QComboBox()
        self.surface_color.addItem(tr("Automático"), "")
        for label, color in ((tr("Azul"), "#4386cb"), (tr("Verde"), "#539873"), (tr("Ámbar"), "#c58c38"),
                             (tr("Morado"), "#8268af"), (tr("Rojo"), "#ba6867")):
            self.surface_color.addItem(label, color)
        self.surface_opacity = QSpinBox()
        self.surface_opacity.setRange(5, 30)
        self.surface_opacity.setValue(15)
        self.surface_opacity.setSuffix(" %")
        options.addRow("Color", self.surface_color)
        options.addRow(tr("Opacidad"), self.surface_opacity)
        layout.addLayout(options)
        self.surface_list = QListWidget()
        self.surface_list.setWordWrap(True)
        self.surface_list.itemClicked.connect(self.jump_to_surface)
        layout.addWidget(self.surface_list, 1)
        self.surface_summary = QLabel("", objectName="muted")
        layout.addWidget(self.surface_summary)
        self.remove_surface_btn = button("Quitar superficie", self.delete_surface, glyph="delete-bin")
        layout.addWidget(self.remove_surface_btn)
        dock.setWidget(panel)
        return dock

    def refresh_surfaces(self):
        self.surface_list.clear()
        if self.path:
            try:
                for page, position, name, area, unit, color in surface_records(self.document_reader):
                    measure = QLocale.system().toString(area, "f", 3)
                    item = QListWidgetItem(tr("{0}\n{1} {2} · pág. {3}").format(name, measure, unit, page + 1))
                    marker = QPixmap(12, 12)
                    marker.fill(QColor.fromRgbF(*color[:3]))
                    item.setIcon(QIcon(marker))
                    item.setData(Qt.ItemDataRole.UserRole, (page, position))
                    self.surface_list.addItem(item)
            except Exception as error:
                self.note(tr("No se pudo leer la lista de superficies: {0}").format(error))
        count = self.surface_list.count()
        self.surface_summary.setText(tr("{0} superficies").format(count) if count else tr("Aún no hay superficies."))
        self.remove_surface_btn.setEnabled(bool(count))

    def open_surfaces(self):
        if self.path is not None:
            self.refresh_surfaces()
            self.surface_dock.show()
            self.surface_dock.raise_()

    def save_surface(self, value, unit):
        if value <= 0:
            self.note(tr("Marca vértices que cierren una superficie."))
            return
        points = self.measure_points[:]
        if not self.editable():
            return
        try:
            records = list(surface_records(self.document_reader))
            labels = {row[2] for row in records}
            number = 1
            while tr("Superficie {0}").format(number) in labels:
                number += 1
            manual = self.surface_color.currentData()
            hex_color = manual or self.surface_color.itemData((number-1) % (self.surface_color.count()-1) + 1)
            color = QColor(hex_color)
            name = tr("Superficie {0}").format(number)
            destination = self.scratch_path()
            add_surface_annotation(
                self.path, destination, self.current, points, name, value, unit,
                (color.redF(), color.greenF(), color.blueF()), self.surface_opacity.value()/100,
            )
            self.load(destination, name=self.name, dirty=True, page=self.current)
            self.open_surfaces()
            self.select_mode("measure-surface")
            self.note(tr("{0} · {1} {2}. Pulsa Ctrl+Enter para cerrar la siguiente.").format(name, QLocale.system().toString(value, 'f', 3), unit))
        except Exception as error:
            self.error(error)

    def jump_to_surface(self, item):
        if self.job is not None:
            return
        page, position = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.goto(page)
            mark = self.document_reader.pages[page]["/Annots"][position].get_object()
            x1, y1, x2, y2 = map(float, mark["/Rect"])
            rect = QRectF(QPointF(*self.coordinates.device(x1, y1)),
                          QPointF(*self.coordinates.device(x2, y2))).normalized()
            self.view.ensureVisible(rect, 28, 28)
        except Exception as error:
            self.error(error)

    def delete_surface(self):
        item = self.surface_list.currentItem()
        if item is None or not self.editable():
            return
        if QMessageBox.question(self, tr("Quitar superficie"), tr("¿Quitar la superficie seleccionada del PDF?")) != QMessageBox.StandardButton.Yes:
            return
        page, position = item.data(Qt.ItemDataRole.UserRole)
        try:
            destination = self.scratch_path()
            remove_review_annotation(self.path, destination, page, position)
            self.load(destination, name=self.name, dirty=True, page=self.current)
            self.note(tr("Superficie retirada."))
        except Exception as error:
            self.error(error)

    def compare_documents(self):
        if self.job is not None:
            return
        selected = self.selected_documents()
        default = selected if len(selected) == 2 else (
            [self.work_docs[self.work_key]] if self.work_key in self.work_docs else [])
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Comparar planos"))
        dialog.resize(540, 170)
        layout = QFormLayout(dialog)
        fields = []
        for index, label in enumerate(("Original", "Revisión")):
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(20)
            combo.addItem(tr("Selecciona un PDF"), None)
            for state in self.work_docs.values():
                combo.addItem(state.name, (state.path, state.password))
                if index < len(default) and state.path == default[index].path:
                    combo.setCurrentIndex(combo.count() - 1)
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            row.addWidget(button("Examinar…", lambda field=combo: self.pick_comparison_pdf(field)))
            layout.addRow(tr(label), row)
            fields.append(combo)
        hint = QLabel(objectName="muted")
        hint.setWordWrap(True)
        layout.addRow(hint)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        submit = controls.addButton(tr("Comparar"), QDialogButtonBox.ButtonRole.AcceptRole)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addRow(controls)

        def ready(*_):
            a, b = (field.currentData() for field in fields)
            submit.setEnabled(bool(a and b and a[0].resolve() != b[0].resolve()))
            hint.setText(tr("Elige dos PDF distintos para comparar.") if a and b and not submit.isEnabled() else "")

        for field in fields:
            field.currentIndexChanged.connect(ready)
        ready()
        if not dialog.exec():
            return
        try:
            RevisionComparison(self, [field.currentData() for field in fields]).exec()
        except Exception as error:
            self.error(error)

    def pick_comparison_pdf(self, field):
        parent = field.window()
        name, _ = QFileDialog.getOpenFileName(parent, tr("Elegir PDF para comparar"), filter="PDF (*.pdf)")
        if not name:
            return
        path = Path(name).resolve()
        password = next((state.password for state in self.work_docs.values() if state.path == path), None)
        while True:
            try:
                reader_for(path, allow_empty_password=True, password=password)
                break
            except ProtectedPdf:
                password, accepted = QInputDialog.getText(parent, tr("PDF protegido"), tr("Contraseña"),
                                                          QLineEdit.EchoMode.Password)
                if not accepted:
                    return
            except Exception as error:
                QMessageBox.warning(parent, tr("Comparar planos"), f"{path.name}: {error}")
                return
        index = next((row for row in range(1, field.count()) if field.itemData(row) == (path, password)), -1)
        if index < 0:
            field.addItem(path.name, (path, password))
            index = field.count() - 1
        field.setCurrentIndex(index)

    def inspect_pdf(self):
        if not self.path:
            return
        source = self.path
        self.start_job(tr("Inspeccionando PDF…"), lambda progress: inspect_document(source, progress),
                       self.show_inspection, progress_label=tr("Inspeccionando página"))

    def show_inspection(self, pages):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Inspección del PDF"))
        dialog.resize(630, 520)
        layout = QVBoxLayout(dialog)
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("Elemento"), tr("Detalle")])
        tree.setColumnWidth(0, 265)
        for index, data in enumerate(pages, 1):
            width, height = data["size"]
            low = sum(min(x, y) < 150 for _, _, x, y in data["images"])
            warning = tr(" · {0} por debajo de 150 ppp").format(low) if low else ""
            node = QTreeWidgetItem(tree, [tr("Página {0}").format(index), f"{width:.0f} × {height:.0f} mm{warning}"])
            for count, (w, h, x, y) in enumerate(data["images"], 1):
                row = QTreeWidgetItem(node, [tr("Imagen {0} · {1} × {2} px").format(count, w, h), tr("{0:.0f} × {1:.0f} ppp").format(x, y)])
                if min(x, y) < 150:
                    row.setForeground(1, QColor("#956032"))
            for font, embedded in data["fonts"]:
                QTreeWidgetItem(node, [font, tr("Incrustada") if embedded else tr("Sin incrustar")])
        tree.expandToDepth(0)
        layout.addWidget(tree)
        layout.addWidget(button("Cerrar", dialog.accept))
        dialog.exec()

    def show_layers(self):
        self.choose_navigation(self.layers_panel)

    def load_layer_panel(self):
        if self.layer_source == self.path:
            return
        with QSignalBlocker(self.layers_list):
            self.layers_list.clear()
            try:
                layers = layer_list(self.path, password=self.document_password)
            except Exception as error:
                self.layers_list.addItem(str(error))
                return
            self.layer_source = self.path
            if not layers:
                self.layers_list.addItem(tr("Este PDF no contiene capas que se puedan mostrar u ocultar."))
                return
            self.layers_list.setToolTip(tr("La visibilidad de las capas se aplica a esta vista."))
            for name, checked, locked in layers:
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, True)
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                if locked:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    item.setToolTip(tr("Capa bloqueada en el PDF."))
                self.layers_list.addItem(item)

    def apply_layer_view(self):
        if not self.path or self.layer_source != self.path:
            return
        if self.job is not None:
            self.layer_timer.start()
            return
        items = [self.layers_list.item(index) for index in range(self.layers_list.count())]
        if not items or not items[0].data(Qt.ItemDataRole.UserRole):
            return
        visible = [item.checkState() == Qt.CheckState.Checked for item in items]
        source, password, destination = self.path, self.document_password, self.scratch_path()

        def generate(_):
            layer_preview(source, destination, visible, password=password)
            with pdfium_reader(destination) as document:
                return [document.get_page_size(index) for index in range(len(document))]

        def show(sizes):
            previous = self.layer_view_path
            self.view.set_document(destination, sizes, self.current, keep_position=True)
            self.layer_view_path = destination
            if previous:
                previous.unlink(missing_ok=True)
            self.note(tr("La visibilidad de las capas se aplica a esta vista."))

        self.start_job(tr("Actualizando capas…"), generate, show, preserve_selection=True)

    def detect_form(self, reader):
        self.form_kind = None
        self.current_fields = []
        label = ""
        try:
            if "/AcroForm" in reader.root_object:
                fields = reader.get_fields() or {}
                has_fields = any(field.get("/FT") in ("/Tx", "/Btn", "/Ch") for field in fields.values())
                if has_fields or has_xfa(reader):
                    self.form_kind = "acro"
                    self.current_fields = form_fields(reader, self.current, known=fields, visible_only=True)
                    if has_xfa(reader):
                        self.form_kind = "hybrid" if has_fields or self.current_fields else "xfa"
                        label = (tr("Formulario XFA híbrido · Haz clic en un campo para preparar una copia editable.")
                                 if self.form_kind == "hybrid" else
                                 tr("Formulario XFA · Esta versión de PDFiu necesita campos AcroForm para editarlo."))
                    elif has_signed_fields(fields):
                        label = tr("Formulario firmado · Edita sobre una copia")
                    else:
                        label = tr("Formulario PDF · Haz clic en un campo para editar.")
                    if not self.current_fields and self.form_kind != "xfa":
                        label = tr("Formulario PDF · Esta página no tiene campos editables visibles.")
        except Exception:
            self.form_kind = "unsupported"
            label = tr("Formulario PDF · PDFiu no pudo leer la definición de los campos.")
        self.form_label.setText(label)
        self.form_strip.setVisible(bool(label))
        self.tint_btn.setVisible(bool(self.current_fields))
        self.refresh_field_tint()

    def refresh_field_tint(self):
        fields = self.current_fields if self.view.mode in (None, "form") else ()
        self.view.show_fields(self.coordinates, fields, tint=self.tint_btn.isChecked())

    def select_mode(self, mode):
        if not self.path or self.job is not None:
            return
        if self.view.mode == mode:
            self.clear_mode()
            return
        self.view.set_mode(mode)
        self.measure_points.clear()
        self.clear_measure_marks()
        self.annotation_edit = None
        self.refresh_field_tint()
        self.view.mark_boxes()
        if mode == "signature":
            try:
                occupied = signature_boxes(reader_for(self.path).pages[self.current])
            except Exception as error:
                self.clear_mode()
                self.error(error)
                return
            self.view.mark_boxes(self.coordinates, occupied)
        self.text_btn.setChecked(mode == "text")
        self.edit_text_btn.setChecked(mode == "edit-text")
        self.pan_btn.setChecked(mode == "pan")
        self.form_btn.setChecked(mode == "form")
        if mode == "signature":
            self.note(tr("Dibuja el recuadro de firma en la página. Esc para cancelar."))
        elif mode == "signature-stamp":
            self.note(tr("Dibuja el recuadro donde colocar la firma visual. Esc para cancelar."))
        elif mode == "edit-text":
            self.note(tr("Haz clic en el texto que quieres cambiar. Enter aplica el cambio y Esc lo cancela."))
        elif mode.startswith("shape-"):
            self.update_shape_color()
            self.note(tr("Arrastra sobre la página para dibujar la forma. Esc para salir."))
        elif mode == "pan":
            self.note(tr("Arrastra para desplazar la página. Esc devuelve el cursor de selección."))
        elif mode.startswith("measure-"):
            self.note(tr("Marca dos puntos de distancia conocida.") if mode == "measure-calibrate" else
                      tr("Marca dos puntos.") if mode == "measure-distance" else
                      tr("Marca los vértices y pulsa Ctrl+Enter para cerrar la figura."))
        else:
            self.note(tr("Haz clic donde empieza el texto. Esc para cancelar."))

    def update_shape_color(self):
        color = QColor(self.shape_color.currentData())
        color.setAlphaF(self.shape_opacity.value() / 100)
        self.view.shape_preview_color = color
        self.view.shape_preview_width = self.shape_width.value()
        self.view.shape_preview_dashed = self.shape_dash.isChecked()
        self.view.shape_preview_filled = self.shape_fill.isChecked()

    def shape_controls(self):
        panel = QFrame(objectName="shapePanel")
        layout = QFormLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        self.shape_width = QSpinBox()
        self.shape_width.setRange(1, 12)
        self.shape_width.setValue(2)
        self.shape_width.setSuffix(" pt")
        self.shape_opacity = QSpinBox()
        self.shape_opacity.setRange(10, 100)
        self.shape_opacity.setValue(100)
        self.shape_opacity.setSuffix(" %")
        self.shape_dash = QCheckBox(tr("Línea discontinua"))
        self.shape_fill = QCheckBox(tr("Relleno suave"))
        self.shape_fill.setToolTip(tr("Solo rectángulos y óvalos"))
        for title, widget in (("Color", self.shape_color), (tr("Grosor"), self.shape_width), (tr("Opacidad"), self.shape_opacity)):
            layout.addRow(title, widget)
        layout.addRow(self.shape_dash)
        layout.addRow(self.shape_fill)
        self.shape_width.valueChanged.connect(self.update_shape_color)
        self.shape_opacity.valueChanged.connect(self.update_shape_color)
        self.shape_dash.toggled.connect(self.update_shape_color)
        self.shape_fill.toggled.connect(self.update_shape_color)
        return panel

    def save_shape(self, start, end):
        mode = self.view.mode
        self.view.set_mode(mode)
        if (start - end).manhattanLength() < 6:
            self.note(tr("Arrastra para dibujar una forma más grande."))
            return
        if self.annotation_edit:
            self.place_annotation_edit(rect=self.coordinates.box(start.x(), start.y(), end.x(), end.y()))
            return
        kind = mode.removeprefix("shape-")
        if kind in ("rectangle", "ellipse") and min(abs(start.x()-end.x()), abs(start.y()-end.y())) < 3:
            self.note(tr("La forma necesita anchura y altura."))
            return
        if not self.editable():
            return
        try:
            destination = self.scratch_path()
            color = QColor(self.shape_color.currentData())
            add_shape(self.path, destination, self.current, kind,
                      self.coordinates.at(start.x(), start.y()), self.coordinates.at(end.x(), end.y()),
                      (color.redF(), color.greenF(), color.blueF()), stroke=self.shape_width.value(),
                      opacity=self.shape_opacity.value() / 100, dashed=self.shape_dash.isChecked(),
                      filled=self.shape_fill.isChecked())
            self.load(destination, name=self.name, dirty=True, page=self.current)
            self.select_mode(mode)
            self.note(tr("Forma añadida. Dibuja otra o pulsa Esc."))
        except Exception as error:
            self.error(error)

    def can_leave(self):
        if self.redaction_boxes:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle(tr("Censura pendiente"))
            dialog.setText(tr("«{0}» tiene zonas marcadas sin aplicar.").format(self.name))
            dialog.setInformativeText(tr("El PDF original aún contiene los datos. Puedes crear una copia censurada o descartar las marcas."))
            save = dialog.addButton(tr("Guardar copia censurada…"), QMessageBox.ButtonRole.ActionRole)
            discard = dialog.addButton(tr("Descartar marcas"), QMessageBox.ButtonRole.DestructiveRole)
            cancel = dialog.addButton(tr("Seguir en el PDF"), QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
            dialog.exec()
            if dialog.clickedButton() is save:
                self.save_redaction()
                return False
            if dialog.clickedButton() is not discard:
                return False
        if not self.dirty:
            return True
        choices = QMessageBox.StandardButton
        destination = self.regular_save_target()
        message = (tr("¿Guardar los cambios en «{0}» antes de cerrar?\n{1}").format(destination.name, destination.parent)
                   if destination else tr("«{0}» tiene cambios pendientes. ¿Guardar una copia antes de cerrar?").format(self.name))
        answer = QMessageBox.question(self, tr("Guardar cambios"), message,
                                      choices.Save | choices.Discard | choices.Cancel, choices.Save)
        return answer == choices.Discard or (answer == choices.Save and self.save(confirmed_target=destination))

    def stash_workspace(self):
        if self.work_key is None or self.path is None:
            return
        previous = self.work_docs.get(self.work_key)
        state = self.document_snapshot()
        self.work_docs[self.work_key] = state
        self.sync_secondary_views(self.work_key, state)
        self.persist_recovery()
        for index in range(self.work_list.count()):
            item = self.work_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == self.work_key:
                if previous is None or previous.name != state.name or previous.dirty != state.dirty or bool(previous.redactions) != bool(state.redactions):
                    item.setText(state.name + ("  •" if state.dirty or state.redactions else ""))
                hint = tr("\nCensura pendiente") if state.redactions else ""
                item.setToolTip(str(state.saved_path or state.path) + hint)
                break

    def new_work_document(self, path, *, name=None, dirty=False, page=0, saved_path=None, protected_source=None, password=None):
        self.view.finish_inline()
        self.stash_workspace()
        existing = self.work_key
        self.work_key = None
        try:
            initial_fit = "width" if self.preferences.value("vista/ajuste_inicial", "page") == "width" else True
            self.load(path, name=name, dirty=dirty, page=page, preserve_previous=True, initial_fit=initial_fit, password=password)
        except Exception:
            self.work_key = existing
            raise
        if dirty:
            self.saved_path = saved_path
            self.protected_source = protected_source
        item = self.register_work_document(self.document_snapshot())
        self.work_key = item.data(Qt.ItemDataRole.UserRole)
        self.work_list.setCurrentItem(item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.enable_controls()

    def register_work_document(self, state):
        key = uuid4().hex
        self.work_docs[key] = state
        self.persist_recovery()
        item = QListWidgetItem()
        item.setIcon(icon("file", 16))
        item.setData(Qt.ItemDataRole.UserRole, key)
        item.setText(state.name + ("  •" if state.dirty else ""))
        item.setToolTip(str(state.saved_path or state.path))
        item.setCheckState(Qt.CheckState.Unchecked)
        self.work_list.addItem(item)
        return item

    def persist_recovery(self):
        try:
            self.recovery.write(self.work_docs.values())
        except OSError:
            self.note(tr("No se pudo actualizar la copia de recuperación."))

    def recover_interrupted_work(self):
        sessions = list(interrupted_sessions(self.scratch.parent))
        if not sessions or self.job is not None:
            return
        count = sum(len(records) for _, records in sessions)
        if QMessageBox.question(
            self, tr("Recuperar cambios"),
            tr("Se encontraron {0} PDF con cambios pendientes. ¿Abrir las copias de recuperación?").format(count),
        ) != QMessageBox.StandardButton.Yes:
            return
        recovered = 0
        for manifest, records in sessions:
            remaining = []
            for record in records:
                source = Path(record["path"])
                try:
                    path = source
                    if record["dirty"]:
                        path = self.scratch_path()
                        copyfile(source, path)
                        # A recovered edit is saved as a copy so it cannot overwrite later work.
                        self.new_work_document(path, name=record["name"], dirty=True, page=int(record["page"]),
                                               protected_source=Path(record["saved_path"]) if record["saved_path"] else None)
                    else:
                        options = dict(name=record["name"], page=int(record["page"]))
                        try:
                            self.new_work_document(path, **options)
                        except ProtectedPdf:
                            if not self.open_protected(path, **options):
                                remaining.append(record)
                                continue
                    self.redaction_boxes = {int(page): boxes for page, boxes in record["redactions"].items()}
                    self.update_redaction_strip()
                    self.stash_workspace()
                    recovered += 1
                except (OSError, ValueError, TypeError, KeyError):
                    remaining.append(record)
            try:
                retain_unrecovered(manifest, remaining)
            except OSError:
                pass
        self.note(tr("{0} PDF recuperados.").format(recovered))

    def sync_workspace_checks(self):
        checked = Qt.CheckState.Checked
        unchecked = Qt.CheckState.Unchecked
        with QSignalBlocker(self.work_list):
            for row in range(self.work_list.count()):
                item = self.work_list.item(row)
                item.setCheckState(checked if item.isSelected() else unchecked)
        self.update_tool_scope()

    def mark_active_work_item(self):
        with QSignalBlocker(self.work_list):
            for row in range(self.work_list.count()):
                item = self.work_list.item(row)
                active = item.data(Qt.ItemDataRole.UserRole) == self.work_key
                font = item.font()
                if font.bold() != active:
                    font.setBold(active)
                    item.setFont(font)

    def change_workspace_check(self, item):
        checked = item.checkState() == Qt.CheckState.Checked
        if item.isSelected() != checked:
            item.setSelected(checked)

    def activate_work_item(self, item):
        if self.job is not None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == self.work_key:
            return
        self.view.finish_inline()
        self.stash_workspace()
        state = self.work_docs[key]
        active = self.work_key
        self.work_key = None
        try:
            self.load(state.path, name=state.name, dirty=state.dirty, page=state.page, preserve_previous=True, password=state.password)
            self.saved_path, self.protected_source = state.saved_path, state.protected_source
            self.redaction_boxes = {index: list(boxes) for index, boxes in state.redactions.items()}
            self.work_key = key
            self.update_redaction_strip()
            self.update_measure_scale()
            self.enable_controls()
        except Exception as error:
            self.work_key = active
            self.error(error)

    def work_context(self, point):
        item = self.work_list.itemAt(point)
        if item is None:
            return
        menu = QMenu(self)
        if item.isSelected() and len(self.work_list.selectedItems()) > 1:
            menu.addAction(tr("Mostrar herramientas para la selección"), self.show_selection_tools)
            menu.addAction(tr("Quitar seleccionados de la mesa"), self.remove_selected_work_documents)
            menu.exec(self.work_list.viewport().mapToGlobal(point))
            menu.deleteLater()
            return
        save = menu.addAction(tr("Guardar"))
        copy = menu.addAction(tr("Guardar como…"))
        menu.addSeparator()
        move = menu.addAction(tr("Mover PDF a otra ventana"))
        close = menu.addAction(tr("Quitar de la mesa de trabajo"))
        chosen = menu.exec(self.work_list.viewport().mapToGlobal(point))
        if chosen is close:
            self.close_work_document(item)
        elif chosen is move:
            self.move_to_new_window(item)
        elif chosen in (save, copy):
            self.activate_work_item(item)
            if self.work_key == item.data(Qt.ItemDataRole.UserRole):
                self.save(as_copy=chosen is copy)
        menu.deleteLater()

    def show_new_window(self, window):
        self.secondary_windows.add(window)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        windows = self.secondary_windows
        window.destroyed.connect(lambda *_: windows.discard(window))
        screens = QApplication.screens()
        if len(screens) > 1 and self.screen() in screens:
            screen = screens[(screens.index(self.screen()) + 1) % len(screens)]
            space = screen.availableGeometry()
            window.resize(min(window.width(), space.width()), min(window.height(), space.height()))
            window.move(space.center() - window.rect().center())
        else:
            window.move(self.pos() + QPoint(32, 32))
        window.show()
        window.raise_()
        window.activateWindow()

    def sync_doc_tabs(self):
        with QSignalBlocker(self.doc_tabs):
            while self.doc_tabs.count():
                self.doc_tabs.removeTab(0)
            active_index = -1
            for row in range(self.work_list.count()):
                item = self.work_list.item(row)
                key = item.data(Qt.ItemDataRole.UserRole)
                state = self.work_docs.get(key)
                if state is None:
                    continue
                is_current = key == self.work_key
                dirty = self.dirty if is_current else state.dirty
                label = f"• {state.name}" if dirty else state.name
                idx = self.doc_tabs.addTab(label)
                self.doc_tabs.setTabData(idx, key)
                self.doc_tabs.setTabToolTip(idx, str(state.saved_path or state.path))
                close_btn = QPushButton(objectName="tabClose")
                close_btn.setFixedSize(18, 18)
                close_btn.setProperty("iconGlyph", ("close", 11, False, False))
                close_btn.setIcon(icon("close", 11))
                close_btn.setIconSize(QSize(11, 11))
                close_btn.setToolTip(tr("Cerrar pestaña"))
                close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                close_btn.clicked.connect(lambda _=False, k=key: self.close_doc_tab_by_key(k))
                self.doc_tabs.setTabButton(idx, QTabBar.ButtonPosition.RightSide, close_btn)
                if is_current:
                    active_index = idx
            if active_index >= 0:
                self.doc_tabs.setCurrentIndex(active_index)
        self.doc_tab_strip.setVisible(self.doc_tabs.count() > 0)

    def _work_item_for_key(self, key):
        for row in range(self.work_list.count()):
            item = self.work_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                return item
        return None

    def activate_doc_tab(self, index):
        if index < 0 or self.job is not None:
            return
        key = self.doc_tabs.tabData(index)
        if key == self.work_key:
            return
        item = self._work_item_for_key(key)
        if item is not None:
            self.activate_work_item(item)

    def close_doc_tab(self, index):
        if index < 0 or self.job is not None:
            return
        self.close_doc_tab_by_key(self.doc_tabs.tabData(index))

    def close_doc_tab_by_key(self, key):
        if self.job is not None:
            return
        item = self._work_item_for_key(key)
        if item is not None:
            self.close_work_document(item)
            self.sync_doc_tabs()

    def detach_doc_tab(self, index, global_pos):
        if index < 0 or self.job is not None:
            return
        key = self.doc_tabs.tabData(index)
        item = self._work_item_for_key(key)
        if item is not None:
            self.move_to_new_window(item, position=global_pos - QPoint(120, 28))
            self.sync_doc_tabs()

    def doc_tab_context(self, position):
        index = self.doc_tabs.tabAt(position)
        if index < 0 or self.job is not None:
            return
        key = self.doc_tabs.tabData(index)
        item = self._work_item_for_key(key)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction(tr("Mover PDF a otra ventana"), lambda: (self.move_to_new_window(item), self.sync_doc_tabs()))
        if key == self.work_key:
            menu.addAction(tr("Abrir otra vista del PDF"), self.open_secondary_view)
            if self.saved_path or self.protected_source:
                menu.addAction(tr("Abrir carpeta del archivo"), self.open_document_folder)
        menu.addSeparator()
        menu.addAction(tr("Cerrar pestaña"), lambda: self.close_doc_tab(index))
        menu.exec(self.doc_tabs.mapToGlobal(position))

    def new_window(self):
        self.show_new_window(PDFiu())

    def open_secondary_view(self):
        if self.work_key is None or self.job is not None:
            return
        self.view.finish_inline()
        key = self.work_key
        window = QMainWindow()
        window.resize(900, 720)
        view = ContinuousPageView()
        window.setCentralWidget(view)
        page = QSpinBox()
        page.setMinimum(1)
        page.setAccessibleName(tr("Número de página"))
        page.valueChanged.connect(lambda value: view.jump(value - 1))

        def current_page(index, _):
            with QSignalBlocker(page):
                page.setValue(index + 1)

        view.active_page_changed.connect(current_page)
        status = window.statusBar()
        status.addPermanentWidget(button("Página anterior", lambda: page.setValue(page.value() - 1), glyph="chevron-left"))
        status.addPermanentWidget(page)
        status.addPermanentWidget(button("Página siguiente", lambda: page.setValue(page.value() + 1), glyph="chevron-right"))
        status.addPermanentWidget(button("Alejar", lambda: view.zoom(.8), glyph="minus"))
        status.addPermanentWidget(button("Ajustar página", view.fit_page))
        status.addPermanentWidget(button("Acercar", lambda: view.zoom(1.25), glyph="plus"))
        close = QAction(window)
        close.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Close))
        close.triggered.connect(window.close)
        window.addAction(close)
        views = self.document_views.setdefault(key, {})
        views[window] = (view, page)
        window.destroyed.connect(lambda *_: views.pop(window, None))
        self.show_new_window(window)
        self.sync_secondary_views(key, self.document_snapshot())

    def sync_secondary_views(self, key, state, *, force=False):
        views = self.document_views.get(key)
        if not views:
            return
        title = tr("{0} · Segunda vista").format(state.name)
        status = tr("Segunda vista · Solo lectura")
        if state.redactions:
            status = tr("Segunda vista · Censura pendiente en la ventana principal")
        pending = [(window, view, page) for window, (view, page) in views.items()
                   if force or view.source != state.path or view.password != state.password]
        if pending:
            with pdfium_reader(state.path, password=state.password) as document:
                sizes = [document.get_page_size(index) for index in range(len(document))]
            for _, view, page in pending:
                first = view.active_index is None
                index = min(state.page if first else view.active_index, len(sizes) - 1)
                with QSignalBlocker(page):
                    page.setMaximum(len(sizes))
                view.set_document(state.path, sizes, index, keep_position=not first,
                                  initial_fit=True if first else None, password=state.password)
                with QSignalBlocker(page):
                    page.setValue(index + 1)
        for window in views:
            window.setWindowTitle(title)
            window.statusBar().showMessage(status)

    def close_secondary_views(self, key):
        for window in list(self.document_views.pop(key, {})):
            window.close()

    def move_to_new_window(self, item=None, *, position=None):
        if self.job is not None:
            return
        if item is not None:
            self.activate_work_item(item)
            if self.work_key != item.data(Qt.ItemDataRole.UserRole):
                return
        if self.work_key is None:
            return
        self.view.finish_inline()
        window = PDFiu()

        def relocate(state):
            if state.path.parent != self.scratch:
                return state
            copied = window.scratch_path()
            copyfile(state.path, copied)
            return replace(state, path=copied)

        try:
            state = relocate(self.document_snapshot())
            undo = [relocate(entry) for entry in self.undo_versions.get(self.work_key, ())]
            redo = [relocate(entry) for entry in self.redo_versions.get(self.work_key, ())]
            window.new_work_document(state.path, name=state.name, dirty=state.dirty, page=state.page,
                                     saved_path=state.saved_path, protected_source=state.protected_source, password=state.password)
            key = window.work_key
            window.redaction_boxes = state.redactions
            window.undo_versions[key], window.redo_versions[key] = undo, redo
            window.calibrations = {(key, page): scale for (doc, page), scale in self.calibrations.items()
                                   if doc == self.work_key}
            window.update_labels()
            window.enable_controls()
            window.navigation.setCurrentIndex(1)
        except Exception as error:
            window.temp.cleanup()
            window.deleteLater()
            self.error(error)
            return
        self.show_new_window(window)
        if position is not None:
            window.move(position)
        self.remove_active_document()
        self.sync_doc_tabs()

    def close_work_document(self, item=None):
        if self.job is not None:
            return False
        if item is not None:
            self.activate_work_item(item)
            if self.work_key != item.data(Qt.ItemDataRole.UserRole):
                return False
        if not self.path:
            return False
        self.view.finish_inline()
        if not self.can_leave():
            return False
        self.remove_active_document()
        return True

    def remove_selected_work_documents(self):
        if self.job is not None:
            return
        for item in self.work_list.selectedItems():
            key = item.data(Qt.ItemDataRole.UserRole)
            state = self.work_docs[key]
            if key != self.work_key and not state.dirty and not state.redactions:
                self.remove_workspace_entry(key, self.work_list.row(item))
            elif not self.close_work_document(item):
                break
        self.work_list.setFocus()

    def remove_active_document(self):
        key = self.work_key
        row = next((i for i in range(self.work_list.count())
                    if self.work_list.item(i).data(Qt.ItemDataRole.UserRole) == key), 0)
        self.stash_workspace()
        self.work_key = None
        self.path = self.saved_path = self.protected_source = self.document_password = None
        self.document_reader = self.coordinates = None
        self.count = self.current = 0
        self.name = ""
        self.dirty = False
        self.current_fields = []
        self.form_kind = None
        self.redaction_boxes.clear()
        self.clear_mode()
        self.view.reset_document()
        self.update_signature_strip(None)
        self.form_strip.hide()
        self.thumbnail_cache.clear()
        self.pages.clear()
        self.review_list.clear()
        self.bookmark_tree.clear()
        self.refresh_surfaces()
        self.canvas.setCurrentWidget(self.empty_state)
        self.remove_workspace_entry(key, row)
        if self.work_list.count():
            next_item = self.work_list.item(min(row, self.work_list.count() - 1))
            self.work_list.setCurrentItem(next_item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.activate_work_item(next_item)
        else:
            for dock in (self.review_dock, self.surface_dock):
                dock.hide()
        self.update_labels()
        self.enable_controls()

    def remove_workspace_entry(self, key, row):
        state = self.work_docs.pop(key, None)
        if state is None:
            return
        self.close_secondary_views(key)
        self.persist_recovery()
        obsolete = [state.path, *(entry.path for entry in self.undo_versions.pop(key, [])),
                    *(entry.path for entry in self.redo_versions.pop(key, []))]
        for scale in [scale for scale in self.calibrations if scale[0] == key]:
            self.calibrations.pop(scale)
        self.work_list.takeItem(row)
        for path in set(obsolete):
            if path.parent == self.scratch and not any(entry.path == path for entry in self.work_docs.values()):
                path.unlink(missing_ok=True)

    def selected_documents(self):
        self.view.finish_inline()
        self.stash_workspace()
        items = sorted(self.work_list.selectedItems(), key=self.work_list.row)
        return [self.work_docs[item.data(Qt.ItemDataRole.UserRole)] for item in items]

    def batch_selection_count(self):
        if self.navigation.currentWidget() is not self.work_tab:
            return 0
        count = len(self.work_list.selectedItems())
        return count if count > 1 else 0

    def show_selection_tools(self):
        if self.focus_layout is not None:
            self.toggle_focus()
        for dock in (self.review_dock, self.surface_dock):
            dock.hide()
        self.tools_requested = True
        self.tools_compact_open = True
        self.sync_tool_panel()

    def update_workspace_hint(self):
        count = self.batch_selection_count()
        if count:
            self.work_hint.setText(tr("{0} PDF marcados.").format(count) if self.tools.isHidden() else "")
        else:
            self.work_hint.setText(tr("Marca varios PDF para trabajar en lote."))

    def update_tool_scope(self):
        count = self.batch_selection_count()
        self.update_workspace_hint()
        scope = tr("{0} PDF seleccionados").format(count) if count else self.name
        self.tool_scope.setText(tr("Aplicar a: {0}").format(scope))
        self.tool_scope.setToolTip(scope)
        self.tool_scope.setVisible(bool(self.path))
        for _, tool in self.tool_library:
            compatible = tool in self.batch_tools
            self.mark_batch_tool(tool, bool(count and compatible))
            available = bool(self.path) or tool in (self.merge_btn, self.batch_btn)
            tool.setEnabled(self.job is None and available and (not count or compatible))
        for favorite, original in self.favorite_controls.values():
            self.mark_batch_tool(favorite, bool(original.property("batchTool")))
            favorite.setEnabled(original.isEnabled())
        self.update_tour_selection()

    @staticmethod
    def mark_batch_tool(tool, enabled):
        if bool(tool.property("batchTool")) != enabled:
            tool.setProperty("batchTool", enabled)
            tool.style().unpolish(tool)
            tool.style().polish(tool)

    def run_workspace_batch(self, selected, title, suffix, operation, *, directory=None,
                            skip_reason="No se generó una copia.", extension="pdf", editable_sources=False):
        if self.job is not None or not selected:
            return
        signed = self.signed_inputs((state.path for state in selected), ignore_unreadable=True) if editable_sources else set()
        if signed and not self.confirm_unsigned_copy(batch=True):
            return
        if directory is None:
            directory = QFileDialog.getExistingDirectory(self, tr("Guardar copias en"))
        if not directory:
            return
        entries = [(state.path, state.name) for state in selected]
        pending_redactions = {state.path for state in selected if state.redactions}

        def process(source, output, name):
            if source in pending_redactions:
                raise ValueError(tr("Hay zonas pendientes de censurar."))
            if source in signed:
                with TemporaryDirectory(dir=self.scratch) as folder:
                    copy = Path(folder) / source.name
                    unlock_pdf(source, copy, remove_signatures=True)
                    result = operation(copy, output, name)
            else:
                result = operation(source, output, name)
            check_cancellation()
            return result

        def done(result):
            saved, skipped, failures, cancelled = result
            if extension == "pdf":
                for path in saved:
                    self.register_work_document(WorkDocument(path, path.name, saved_path=path))
            summary = (tr("{0} de {1} PDF guardados.").format(len(saved), len(selected)) if extension == "pdf" else
                       tr("{0} {1} · {2} PDF seleccionados.").format(len(saved), tr("archivo guardado") if len(saved) == 1 else tr("archivos guardados"), len(selected)))
            self.note(summary)
            details = [f"{name}: {error}" for name, error in failures]
            details.extend(f"{name}: {skip_reason}" for name in skipped)
            details.extend(f"{name}: {tr('Sin procesar por cancelación.')}" for name in cancelled)
            self.show_workspace_batch_result(title, summary, directory, saved, details)

        self.start_job(
            f"{title}…",
            lambda progress: workspace_batch_copies(entries, directory, suffix, process, progress, extension=extension),
            done, progress_label=tr("Procesando PDF"), cancellable=True,
        )

    def show_workspace_batch_result(self, title, summary, directory, saved, details):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(540, 320)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(summary, objectName="resultHeading"))
        location = QLabel(str(directory), objectName="muted")
        location.setTextFormat(Qt.TextFormat.PlainText)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setWordWrap(True)
        layout.addWidget(location)
        results = QListWidget()
        results.setAccessibleName(tr("Resultados de la operación"))
        results.setWordWrap(True)
        results.addItems([tr("Guardado · {0}").format(path.name) for path in saved])
        results.addItems([tr("Pendiente · {0}").format(detail) for detail in details])
        layout.addWidget(results, 1)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.button(QDialogButtonBox.StandardButton.Close).setText(tr("Cerrar"))
        controls.rejected.connect(dialog.reject)
        open_folder = controls.addButton(tr("Abrir carpeta"), QDialogButtonBox.ButtonRole.ActionRole)
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))))
        layout.addWidget(controls)
        dialog.exec()

    def unlock_workspace(self):
        documents = self.selected_documents()
        signed = self.signed_inputs((state.path for state in documents), ignore_unreadable=True)
        if signed and not self.confirm_unsigned_copy(batch=True):
            return
        self.run_workspace_batch(
            documents, tr("Desbloquear PDF"), "_unlocked",
            lambda source, output, _: unlock_pdf(source, output, skip_unprotected=True, remove_signatures=source in signed),
            skip_reason=tr("El archivo ya estaba desbloqueado."),
        )

    def ocr_workspace(self):
        selected = self.selected_documents()
        if not selected:
            return
        model = self.choose_ocr_language()
        if model:
            def apply_ocr(source, output, _):
                ocr_document(source, output, RUNTIME / "tessdata", model, check_cancellation)

            self.run_workspace_batch(
                selected, tr("Reconocer texto (OCR)"), "OCR",
                apply_ocr,
                skip_reason=tr("No se encontró texto nuevo."),
                editable_sources=True,
            )

    def note_workspace(self):
        selected = self.selected_documents()
        if not selected:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Añadir nota a {0} PDF").format(len(selected)))
        dialog.setMinimumWidth(480)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        note = QPlainTextEdit()
        note.setPlaceholderText(tr("Escribe la nota que quieres añadir a los PDF."))
        pages = QLineEdit("1")
        pages.setPlaceholderText(tr("Vacío para todas · por ejemplo, 1,3-5"))
        layout.addRow(note)
        layout.addRow(tr("Páginas en cada PDF"), pages)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        apply = buttons.button(QDialogButtonBox.StandardButton.Ok)
        apply.setText(tr("Continuar…"))
        apply.setEnabled(False)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        note.textChanged.connect(lambda: apply.setEnabled(bool(note.toPlainText().strip())))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            text, expression = note.toPlainText().strip(), pages.text()
            self.run_workspace_batch(
                selected, tr("Añadir nota"), tr("con nota"),
                lambda source, output, _: add_batch_note(source, output, expression, text),
                editable_sources=True,
            )

    def open_dialog(self):
        if self.job is not None:
            return
        remember = self.preferences.value("archivos/recordar_carpeta", True, type=bool)
        initial = self.preferences.value("archivos/ultima_carpeta", "") if remember else ""
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Abrir uno o varios PDF"), initial, filter="PDF (*.pdf)")
        if paths and remember:
            self.preferences.setValue("archivos/ultima_carpeta", str(Path(paths[0]).parent))
        for path in paths:
            self.open_path(path)

    def open_path(self, path, *, remember_recent=True):
        if self.job is not None:
            return
        path = Path(path).resolve()
        self.view.finish_inline()
        self.stash_workspace()
        for index in range(self.work_list.count()):
            item = self.work_list.item(index)
            state = self.work_docs[item.data(Qt.ItemDataRole.UserRole)]
            if path in (state.path.resolve(), state.saved_path, state.protected_source):
                self.work_list.setCurrentItem(item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                self.activate_work_item(item)
                if remember_recent and self.work_key == item.data(Qt.ItemDataRole.UserRole):
                    self.remember_recent_file(path)
                return
        try:
            self.new_work_document(path)
            if self.document_reader.is_encrypted:
                self.note(tr("PDF protegido. Usa Proteger → Desbloquear PDF para crear una copia editable."))
        except ProtectedPdf:
            if not self.open_protected(path):
                return
        except Exception as error:
            self.error(error)
            return
        if remember_recent:
            self.remember_recent_file(path)

    def open_protected(self, path, **options):
        prompt = tr("Introduce la contraseña para abrir el PDF en modo lectura.")
        while True:
            password, accepted = QInputDialog.getText(self, tr("PDF protegido"), prompt, QLineEdit.EchoMode.Password)
            if not accepted:
                return False
            try:
                self.new_work_document(path, password=password, **options)
                self.note(tr("PDF protegido abierto en modo lectura."))
                return True
            except ProtectedPdf as error:
                prompt = str(error)
            except Exception as error:
                self.error(error)
                return False

    def unlock_dialog(self):
        if self.batch_selection_count():
            self.unlock_workspace()
            return
        if not self.path or self.job is not None:
            return
        signed = pdf_has_signatures(self.document_reader)
        if not self.document_reader.is_encrypted and not signed:
            self.note(tr("Este PDF ya está desbloqueado. Pulsa Guardar para conservar la copia.") if self.protected_source
                      else tr("Este PDF ya está desbloqueado."))
            return
        if signed and not self.confirm_unsigned_copy():
            return
        source, page = self.path, self.current
        password = self.document_password or ""
        original = self.protected_source or self.saved_path or source
        destination = self.scratch_path()

        def done(_):
            self.load_editable_copy(destination, original, page, signed=signed)

        self.start_job(tr("Desbloqueando PDF…"), lambda _: unlock_pdf(source, destination, password, remove_signatures=signed), done)

    def confirm_unsigned_copy(self, *, batch=False):
        message = (
            tr("Las copias de los PDF firmados perderán sus firmas digitales. Se conservarán los originales. ¿Continuar?")
            if batch else tr("La copia editable perderá las firmas digitales. Se conservará el PDF firmado original. ¿Continuar?")
        )
        choice = QMessageBox.question(self, tr("Crear copia editable"), message,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return choice == QMessageBox.StandardButton.Yes

    def load_editable_copy(self, destination, original, page, *, signed):
        self.load(destination, name=f"{original.stem}_unlocked.pdf", dirty=True, page=page)
        self.protected_source = original
        self.stash_workspace()
        self.note(tr("Copia editable sin firmas. Pulsa Guardar para conservarla.") if signed else
                  tr("PDF desbloqueado. Pulsa Guardar para conservar una copia."))

    def signed_inputs(self, paths, *, ignore_unreadable=False):
        signed = set()
        for path in paths:
            try:
                if Path(path).resolve() == self.path and self.document_reader is not None:
                    if pdf_has_signatures(self.document_reader):
                        signed.add(path)
                    continue
                reader = reader_for(path, allow_empty_password=True)
                if pdf_has_signatures(reader):
                    signed.add(path)
            except Exception as error:
                if not ignore_unreadable:
                    self.error(f"{Path(path).name}: {error}")
                    return None
        return signed

    def dragEnterEvent(self, event):
        if self.job is None and PageList.pdf_paths(event.mimeData()) and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = PageList.pdf_paths(event.mimeData())
        if not paths or self.job is not None or not event.possibleActions() & Qt.DropAction.CopyAction:
            event.ignore()
            return
        for path in paths:
            self.open_path(path)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def save_as(self, title, name, extension):
        path, _ = QFileDialog.getSaveFileName(self, title, name, f"{extension.upper()} (*.{extension})",
                                               options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return None
        result = Path(path)
        if result.suffix.lower() != f".{extension}":
            result = Path(f"{result}.{extension}")
        return result if self.confirm_overwrite(result) else None

    def confirm_overwrite(self, path):
        choices = QMessageBox.StandardButton
        return not path.exists() or QMessageBox.question(
            self, tr("Sustituir archivo"), tr("¿Guardar los cambios sobre «{0}»?\n{1}").format(path.name, path.parent),
            choices.Yes | choices.No, choices.No,
        ) == choices.Yes

    def regular_save_target(self):
        if self.saved_path is None:
            return None
        if self.protected_source and self.saved_path.resolve() == self.protected_source.resolve():
            return None
        return self.saved_path

    def save(self, *, as_copy=False, confirmed_target=None):
        if not self.path or self.job is not None:
            return False
        self.view.finish_inline()
        if not self.dirty and not as_copy:
            self.note(tr("El PDF ya está guardado. Las marcas de censura requieren una copia censurada.")
                      if self.redaction_boxes else tr("El PDF ya está guardado."))
            return True
        destination = None if as_copy else self.regular_save_target()
        if not destination:
            suggested = self.name if not as_copy else tr("{0} - copia.pdf").format(Path(self.name).stem)
            folder = self.saved_path.parent if self.saved_path else self.preferences.value("archivos/ultima_carpeta", "")
            initial = Path(folder) / suggested if folder else Path(suggested)
            destination = self.save_as(tr("Guardar PDF como"), str(initial), "pdf")
        if not destination:
            return False
        if self.protected_source and self.protected_source.resolve() == destination.resolve():
            self.error(tr("Elige otro nombre para conservar el PDF original."))
            return False
        try:
            if self.path.resolve() != destination.resolve():
                with atomic_output(destination) as temporary:
                    copyfile(self.path, temporary)
            pending = self.redaction_boxes.copy()
            self.load(destination, page=self.current, password=self.document_password)
            self.redaction_boxes = pending
            self.update_labels()
            self.note(tr("PDF guardado. La censura sigue pendiente.") if pending else tr("PDF guardado."))
            if self.tour_step == 4 and self.work_key == self.tour_result_key:
                self.tour_destination = destination
                self.set_tour_step(5)
            return True
        except Exception as error:
            self.error(error)
            return False

    def start_job(self, label, callback, result, *, preserve_selection=False, progress_label=None, cancellable=False):
        self.view.zoom_render.stop()
        self.view.scroll_render.stop()
        if not preserve_selection:
            self.clear_mode()
        self.note(label)
        self.progress_label = progress_label
        self.progress.setRange(0, 0)
        self.progress.show()
        self.job = Job(callback, result, self, cancellable=cancellable)
        self.cancel_job_btn.setVisible(cancellable)
        self.cancel_job_btn.setEnabled(cancellable)
        self.job.progress.connect(self.show_progress)
        self.job.finished.connect(self.finish_job)
        self.enable_controls()
        self.job.start()

    def cancel_job(self):
        if self.job is not None and self.job.cancellable:
            self.job.requestInterruption()
            self.cancel_job_btn.setEnabled(False)
            self.note(tr("Cancelando en cuanto termine el paso actual…"))

    def show_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        if self.progress_label and (self.job is None or not self.job.isInterruptionRequested()):
            self.note(tr("{0} {1} de {2}…").format(self.progress_label, done, total))

    def finish_job(self):
        job = self.job
        self.job = None
        self.search_job = False
        self.progress.hide()
        self.cancel_job_btn.hide()
        self.enable_controls()
        try:
            if job.cancelled:
                self.note(tr("Operación cancelada."))
            elif job.failure:
                self.clear_mode()
                self.error(job.failure)
            else:
                job.callback(job.result)
        except Exception as error:
            self.error(error)
        finally:
            job.deleteLater()
            if self.search_pending is not None:
                jump, self.search_pending = self.search_pending, None
                QTimer.singleShot(0, self, lambda: self.run_search(jump=jump))

    def merge_dialog(self, paths=None):
        if self.job is not None:
            return
        selected = self.selected_documents()
        names = {str(state.path): state.name for state in selected}
        if paths is None:
            if self.batch_selection_count():
                paths = [str(state.path) for state in selected]
            elif self.path:
                paths = [str(self.path)]
                names[str(self.path)] = self.name
        dialog = MergeDialog(self, paths or [], names)
        if self.tour_step == 3:
            TourSpotlight(dialog).follow_button(dialog.accept_button)
        if paths is None:
            dialog.add_files()
        if not dialog.exec():
            return
        destination = self.scratch_path()
        inputs = dialog.paths()
        signed = self.signed_inputs(inputs)
        if signed is None or (signed and not self.confirm_unsigned_copy(batch=True)):
            return
        with_index = dialog.with_index.isChecked()

        def done(_):
            self.new_work_document(destination, name=tr("Documentos unidos.pdf"), dirty=True)
            combined_paths = {Path(path).resolve() for path in inputs}
            pending = 0
            for row in range(self.work_list.count() - 1, -1, -1):
                key = self.work_list.item(row).data(Qt.ItemDataRole.UserRole)
                state = self.work_docs[key]
                if key == self.work_key or state.path.resolve() not in combined_paths:
                    continue
                if state.dirty or state.redactions:
                    pending += 1
                    continue
                self.remove_workspace_entry(key, row)
            self.note(tr("PDFs unidos. Los originales con cambios pendientes siguen en la mesa.") if pending else
                      tr("PDFs unidos. Pulsa Guardar para conservar el resultado."))
            if self.tour_step in (2, 3) and len(inputs) == 2 and combined_paths == set(self.tour_paths):
                self.tour_result_key = self.work_key
                self.set_tour_step(4)

        self.start_job(
            tr("Uniendo PDFs…"),
            lambda _: merge(inputs, destination, with_index=with_index, names=names, remove_signatures=bool(signed)),
            done,
        )

    def sheet_layout_dialog(self):
        batch = self.selected_documents() if self.batch_selection_count() else []
        if not batch and (not self.editable() or self.redaction_boxes):
            if self.redaction_boxes:
                self.note(tr("Guarda la copia censurada o quita las marcas antes de colocar las páginas."))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Varias páginas por hoja · {0} PDF").format(len(batch)) if batch else tr("Varias páginas por hoja"))
        dialog.setMinimumWidth(380)
        form = QFormLayout(dialog)
        layout = QComboBox()
        for label, grid in (
            (tr("4 por hoja (2 × 2)"), (2, 2)), (tr("2 por hoja (2 × 1)"), (2, 1)),
            (tr("6 por hoja (2 × 3)"), (2, 3)), (tr("9 por hoja (3 × 3)"), (3, 3)),
            (tr("16 por hoja (4 × 4)"), (4, 4)), (tr("Todo el PDF en una hoja"), None),
            (tr("Cuadrícula personalizada"), "custom"),
        ):
            layout.addItem(label, grid)
        columns, rows = QSpinBox(), QSpinBox()
        for dimension in (columns, rows):
            dimension.setRange(1, 20)
            dimension.setValue(2)
        form.addRow(tr("Distribución"), layout)
        form.addRow(tr("Columnas"), columns)
        form.addRow(tr("Filas"), rows)
        paper = QComboBox()
        for name, size in (("A4", (595.28, 841.89)), ("A3", (841.89, 1190.55)), (tr("Carta"), (612, 792))):
            paper.addItem(name, size)
        orientation = QComboBox()
        orientation.addItems([tr("Vertical"), tr("Horizontal")])
        form.addRow(tr("Papel"), paper)
        form.addRow(tr("Orientación"), orientation)
        preview = QLabel(objectName="muted")
        form.addRow(preview)
        hint = QLabel(tr("Crea una copia para imprimir. Las anotaciones y los campos interactivos quedan en el original."),
                      objectName="muted")
        hint.setWordWrap(True)
        form.addRow(hint)

        def chosen_grid():
            return (columns.value(), rows.value()) if layout.currentData() == "custom" else layout.currentData()

        def update_preview():
            custom = layout.currentData() == "custom"
            form.setRowVisible(columns, custom)
            form.setRowVisible(rows, custom)
            if not batch:
                grid = chosen_grid()
                capacity = grid[0] * grid[1] if grid else self.count
                sheets = (self.count + capacity - 1) // capacity
                preview.setText(tr("{0} páginas → {1} {2}").format(self.count, sheets, tr("hoja") if sheets == 1 else tr("hojas")))

        preview.setVisible(not batch)
        layout.currentIndexChanged.connect(update_preview)
        columns.valueChanged.connect(update_preview)
        rows.valueChanged.connect(update_preview)
        update_preview()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Crear PDF"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if not dialog.exec():
            return
        size = tuple(paper.currentData())
        if orientation.currentIndex() == 1:
            size = size[::-1]
        grid = chosen_grid()
        if batch:
            self.run_workspace_batch(
                batch, tr("Varias páginas por hoja"), tr("varias páginas por hoja"),
                lambda source, output, _: pages_per_sheet(source, output, size, grid, lambda *_: None),
                editable_sources=True,
            )
        else:
            source, output = self.path, self.scratch_path()
            name = tr("{0} - varias páginas por hoja.pdf").format(Path(self.name).stem)
            self.start_job(
                tr("Colocando páginas en hojas…"),
                lambda progress: pages_per_sheet(source, output, size, grid, progress),
                lambda _: self.new_work_document(output, name=name, dirty=True),
                progress_label=tr("Colocando página"),
            )

    def open_default_apps(self):
        if not QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")):
            self.note(tr("Abre Configuración de Windows → Aplicaciones → Aplicaciones predeterminadas y busca .pdf."))

    def start_recipe(self):
        selected = self.selected_documents()
        inputs = [(state.path, state.name) for state in selected]
        if not inputs:
            paths, _ = QFileDialog.getOpenFileNames(self, tr("Elegir archivos del expediente"), filter="PDF (*.pdf)")
            inputs = [(Path(path), Path(path).name) for path in paths]
        if not inputs:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Proceso de expediente"))
        dialog.setMinimumWidth(500)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        presets = dict(self.preferences.value("expediente/recetas", {}) or {})
        profiles = QComboBox()
        profiles.addItems([tr("Sin plantilla"), *sorted(presets)])
        ocr = QCheckBox(tr("Reconocer texto en páginas escaneadas"))
        ocr.setChecked(True)
        language = QComboBox()
        language.addItems([tr("Español + inglés"), tr("Español"), tr("Inglés")])
        numbering = QCheckBox(tr("Numerar al pie de página"))
        numbering.setChecked(True)
        signing = QCheckBox(tr("Elegir recuadros y certificado al terminar"))
        layout.addRow(tr("Receta"), profiles)
        layout.addRow("1 · OCR", ocr)
        layout.addRow(tr("Idiomas"), language)
        layout.addRow(tr("2 · Numeración"), numbering)
        layout.addRow(tr("3 · Firma"), signing)
        layout.addRow(QLabel(tr("{0} PDF seleccionados. Los resultados se guardan como copias.").format(len(inputs))))

        def apply_profile(name):
            if name in presets:
                read_ocr, model, read_numbering, read_signing = presets[name]
                ocr.setChecked(bool(read_ocr))
                language.setCurrentIndex(int(model))
                numbering.setChecked(bool(read_numbering))
                signing.setChecked(bool(read_signing))

        def save_profile():
            name, ok = QInputDialog.getText(dialog, tr("Guardar receta"), tr("Nombre"))
            name = name.strip()
            if not ok or not name or name == tr("Sin plantilla"):
                return
            presets[name] = [ocr.isChecked(), language.currentIndex(), numbering.isChecked(), signing.isChecked()]
            self.preferences.setValue("expediente/recetas", presets)
            self.preferences.sync()
            if profiles.findText(name) < 0:
                profiles.addItem(name)
            profiles.setCurrentText(name)

        profiles.currentTextChanged.connect(apply_profile)
        layout.addRow(button("Guardar como receta…", save_profile))
        decisions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        decisions.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Continuar"))
        decisions.accepted.connect(dialog.accept)
        decisions.rejected.connect(dialog.reject)
        layout.addRow(decisions)
        if not dialog.exec():
            return
        use_ocr, use_numbering, use_signature = ocr.isChecked(), numbering.isChecked(), signing.isChecked()
        if not (use_ocr or use_numbering):
            if use_signature:
                self.batch_dialog([str(path) for path, _ in inputs], {str(path): name for path, name in inputs})
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Carpeta para las copias preparadas"))
        if not folder:
            return
        model = ("spa+eng", "spa", "eng")[language.currentIndex()]

        def done(paths):
            for path in paths:
                self.register_work_document(WorkDocument(path, path.name, saved_path=path))
            self.note(tr("{0} PDF preparados.").format(len(paths)))
            if use_signature:
                self.batch_dialog([str(path) for path in paths])

        self.start_job(tr("Preparando expediente…"), lambda progress: prepare_recipe(
            inputs, folder, RUNTIME / "tessdata", model, use_ocr, use_numbering, progress,
        ), done, progress_label=tr("Preparando PDF"))

    def editable(self):
        if self.job is not None or not self.path:
            return False
        self.view.finish_inline()
        try:
            signed = pdf_has_signatures(self.document_reader)
            if signed or self.document_reader.is_encrypted:
                if signed and not self.confirm_unsigned_copy():
                    return False
                original = self.protected_source or self.saved_path or self.path
                destination = self.scratch_path()
                unlock_pdf(self.path, destination, self.document_password or "", remove_signatures=signed)
                self.load_editable_copy(destination, original, self.current, signed=signed)
            return True
        except Exception as error:
            self.error(error)
            return False

    def reorder_pages(self, indices, position):
        selected = set(indices)
        remaining = [index for index in range(self.count) if index not in selected]
        start = position - bisect_left(indices, position)
        order = remaining[:start] + indices + remaining[start:]
        if order == list(range(self.count)):
            return
        if self.rewrite(order, start):
            for index in range(start, start + len(indices)):
                self.pages.item(index).setSelected(True)

    def select_pdfs_to_insert(self):
        if not self.path or self.job is not None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Insertar PDF después de la página actual"), filter="PDF (*.pdf)")
        if paths:
            self.insert_documents(self.current + 1, [(Path(path), None) for path in paths])

    def insert_documents(self, position, sources):
        if not self.path or self.job is not None:
            return
        self.view.finish_inline()
        if self.redaction_boxes:
            self.note(tr("Guarda la copia censurada o quita las marcas antes de cambiar las páginas."))
            return
        signed = self.signed_inputs(path for path, _ in sources)
        if signed is None or (signed and not self.confirm_unsigned_copy(batch=True)):
            return
        target_signed = pdf_has_signatures(self.document_reader)
        if target_signed and not self.confirm_unsigned_copy():
            return
        source, name = self.path, self.name
        rework = target_signed or self.document_reader.is_encrypted
        original = self.protected_source or self.saved_path or source
        password = self.document_password or ""
        destination = self.scratch_path()

        def insert(_):
            if not rework:
                return insert_pages(source, destination, position, sources, remove_signatures=bool(signed))
            with TemporaryDirectory(dir=self.scratch) as folder:
                editable_source = Path(folder) / "editable.pdf"
                unlock_pdf(source, editable_source, password, remove_signatures=target_signed)
                return insert_pages(editable_source, destination, position, sources, remove_signatures=bool(signed))

        def finished(count):
            if rework:
                self.load_editable_copy(destination, original, position, signed=target_signed)
            else:
                self.load(destination, name=name, dirty=True, page=position)
            self.reset_calibrations()
            for index in range(position, position + count):
                self.pages.item(index).setSelected(True)
            self.pages.scrollToItem(self.pages.item(position))
            self.note(tr("1 página insertada. Pulsa Ctrl+Z para deshacer.") if count == 1 else
                      tr("{0} páginas insertadas. Pulsa Ctrl+Z para deshacer.").format(count))

        self.start_job(tr("Insertando páginas…"), insert, finished)

    def rewrite(self, order, page, rotate=None):
        if not self.editable():
            return False
        if self.redaction_boxes:
            self.note(tr("Guarda la copia censurada o quita las marcas antes de cambiar las páginas."))
            return False
        try:
            destination = self.scratch_path()
            edit_pages(self.path, destination, order, rotate_index=rotate)
            self.load(destination, name=self.name, dirty=True, page=page)
            self.reset_calibrations()
            return True
        except Exception as error:
            self.error(error)
            return False

    def rotate_page(self):
        self.rewrite(list(range(self.count)), self.current, rotate=self.current)

    def remove_page(self):
        if self.count > 1:
            order = [index for index in range(self.count) if index != self.current]
            self.rewrite(order, min(self.current, len(order) - 1))

    def extract_page(self):
        if not self.editable():
            return
        destination = self.save_as(tr("Extraer página"), tr("{0} - página {1}.pdf").format(Path(self.name).stem, self.current + 1), "pdf")
        if destination:
            if self.path.resolve() == destination.resolve():
                self.error(tr("Elige un nombre distinto del PDF abierto."))
                return
            try:
                edit_pages(self.path, destination, [self.current])
                self.note(tr("Página extraída."))
            except Exception as error:
                self.error(error)

    def organize_pages_grid(self):
        if self.path is None or self.job is not None or not self.editable():
            return
        dialog = OrganizePagesDialog(self.path, self.count, password=self.document_password, parent=self)
        if not dialog.exec():
            return
        order, rotations = dialog.result_plan()
        if order == list(range(self.count)) and not rotations:
            return
        try:
            destination = self.scratch_path()
            edit_pages(self.path, destination, order, rotations=rotations)
            self.load(destination, name=self.name, dirty=True, page=0)
            self.note(tr("Páginas organizadas. Pulsa Ctrl+Z para deshacer."))
        except Exception as error:
            self.error(error)

    def split_current_pdf(self):
        if self.path is None or self.job is not None:
            return
        folder = self.saved_path.parent if self.saved_path else Path(self.preferences.value("archivos/ultima_carpeta", str(Path.home())))
        dialog = SplitDialog(self.count, Path(self.name).stem, folder, self)
        if not dialog.exec():
            return
        out_dir = Path(dialog.folder.text().strip())
        if not str(out_dir):
            return
        every = dialog.every.value()
        stem = dialog.prefix.text().strip() or Path(self.name).stem
        source = self.path
        password = self.document_password

        def done(created):
            self.note(tr("PDF dividido en {0} archivo(s).").format(len(created)))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

        self.start_job(
            tr("Dividiendo PDF…"),
            lambda progress: split_pdf(source, out_dir, every=every, stem=stem, password=password, progress=progress),
            done,
            progress_label=tr("Creando archivo"),
        )

    def extract_range(self):
        if not self.editable():
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr("Extraer páginas"))
        dialog.setLabelText(tr("Páginas o rangos, como 1,3-5,8"))
        dialog.setOkButtonText(tr("Aceptar"))
        dialog.setCancelButtonText(tr("Cancelar"))
        if not dialog.exec() or not dialog.textValue().strip():
            return
        try:
            indices = page_range(dialog.textValue(), self.count)
            source = self.path
            destination = self.output_copy(tr("Guardar páginas extraídas"), tr("páginas extraídas"))
            if destination:
                quantity = tr("Se guardaron {0} páginas").format(len(indices)) if len(indices) > 1 else tr("Se guardó 1 página")
                self.start_job(tr("Extrayendo páginas…"), lambda _: edit_pages(source, destination, list(indices)),
                               lambda _: self.note(tr("{0} en {1}.").format(quantity, destination.name)))
        except Exception as error:
            self.error(error)

    def output_copy(self, title, suffix):
        destination = self.save_as(title, f"{Path(self.name).stem} - {suffix}.pdf", "pdf")
        if destination and any(path and path.resolve() == destination.resolve()
                               for path in (self.path, self.saved_path, self.protected_source)):
            self.error(tr("Elige un nombre distinto para conservar el original."))
            return None
        return destination

    def compress_pdf(self, previous=None):
        if not self.path or self.job is not None:
            return
        dialog = CompressDialog(self, previous=previous)
        decision = dialog.exec()
        if not decision:
            return
        source = self.path
        label = dialog.profile_label()
        settings = dialog.current_settings()
        if decision == QDialog.DialogCode.Accepted:
            self.calculate_compression(label, settings)
            return
        options = self.compression_parameters(settings)
        password = self.document_password
        self.start_job(tr("Estimando el tamaño…"), lambda _: estimate_compression(source, password=password, **options),
                       lambda result: self.show_compression_estimate(label, settings, result))

    @staticmethod
    def compression_parameters(settings):
        lossless = bool(settings.get("lossless", False))
        return {
            "quality": None if lossless else int(settings.get("quality", 82)),
            "dpi": None if (lossless or not settings.get("downsample", True)) else int(settings.get("dpi", 150)),
            "compact": False if lossless else bool(settings.get("compact", True)),
            "grayscale": False if lossless else bool(settings.get("grayscale", False)),
            "strip_bloat": bool(settings.get("strip_bloat", True)),
            "clean_metadata": bool(settings.get("clean_metadata", False)),
        }

    def show_compression_estimate(self, profile, settings, result):
        before, estimate, sampled_pages, total_pages = result
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Estimación de compresión"))
        savings = (before - estimate) / before
        if before == estimate:
            dialog.setText(tr("{0} · Sin ahorro apreciable en la estimación").format(file_size_label(before)))
        else:
            dialog.setText(tr("{0} → ≈ {1} · Ahorro estimado {2:.0%}").format(file_size_label(before), file_size_label(estimate), savings))
        dialog.setInformativeText(
            tr("{0}. Se tienen en cuenta las imágenes del PDF y se mide su colocación en hasta {1} de {2} páginas. El tamaño final puede variar.").format(profile, sampled_pages, total_pages)
        )
        compress = dialog.addButton(tr("Comprimir ahora"), QMessageBox.ButtonRole.AcceptRole)
        change = dialog.addButton(tr("Cambiar perfil"), QMessageBox.ButtonRole.ActionRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        cancel.setText(tr("Cerrar"))
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is compress:
            self.calculate_compression(profile, settings)
        elif dialog.clickedButton() is change:
            self.compress_pdf(settings)

    def calculate_compression(self, profile, settings):
        if not self.editable():
            return
        source, temporary = self.path, self.scratch_path()
        options = self.compression_parameters(settings)
        def done(result):
            self.show_compression_result(temporary, profile, settings, result)

        self.start_job(tr("Comprimiendo PDF…"), lambda progress: compress_copy(
            source, temporary, fast=False, allow_larger=True, progress=progress, **options,
        ), done, cancellable=True)

    def show_compression_result(self, temporary, profile, settings, result):
        before, after, images, resized = result
        difference = before - after
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Tamaño de la copia comprimida"))
        dialog.setText(f"{file_size_label(before)} → {file_size_label(after)} · {profile}")
        ratio = abs(difference) / before
        if difference > 0:
            comparison = tr("Ahorro del {0:.1%}.").format(ratio)
        elif resized == 0:
            comparison = (tr("El perfil no produjo un archivo más pequeño. No se redujo ninguna imagen: quizá ya cumple el límite o usa un formato que PDFiu conserva."))
        else:
            comparison = (tr("Se redujeron algunas imágenes, pero el ahorro no compensó el tamaño del resto del PDF. PDFiu descartó la copia de prueba."))
        dialog.setInformativeText(tr("{0}\nImágenes optimizadas en la prueba: {1} · Redimensionadas: {2}").format(comparison, images, resized))
        save = dialog.addButton(tr("Guardar copia…"), QMessageBox.ButtonRole.AcceptRole)
        preview = dialog.addButton(tr("Comparar al 100 %…"), QMessageBox.ButtonRole.ActionRole) if difference > 0 else None
        change = dialog.addButton(tr("Cambiar perfil"), QMessageBox.ButtonRole.ActionRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        cancel.setText(tr("Cancelar"))
        save.setEnabled(difference > 0)
        dialog.setDefaultButton(save if difference > 0 else change)
        try:
            while True:
                dialog.exec()
                choice = dialog.clickedButton()
                if preview is not None and choice is preview:
                    try:
                        CompressionPreview(self, self.path, temporary, self.current).exec()
                    except Exception as error:
                        self.error(error)
                    continue
                if choice is not save:
                    break
                destination = self.output_copy(tr("Guardar copia comprimida"), tr("comprimido"))
                if destination:
                    with atomic_output(destination) as output:
                        copyfile(temporary, output)
                    self.note(tr("Copia comprimida guardada · Ahorro del {0:.1%}.").format(ratio))
                    return
        finally:
            temporary.unlink(missing_ok=True)
        if choice is change:
            self.compress_pdf(settings)

    def protect_pdf(self):
        if not self.editable():
            return
        mode = QLineEdit.EchoMode.Password
        password, accepted = QInputDialog.getText(self, tr("Proteger PDF"), tr("Contraseña de apertura"), mode)
        if not accepted or not password:
            return
        confirmation, accepted = QInputDialog.getText(self, tr("Proteger PDF"), tr("Repite la contraseña"), mode)
        if not accepted:
            return
        if password != confirmation:
            self.error(tr("Las contraseñas no coinciden."))
            return
        destination = self.output_copy(tr("Guardar copia protegida"), tr("protegido"))
        if destination:
            source = self.path
            self.start_job(tr("Protegiendo PDF…"), lambda _: protect_copy(source, destination, password),
                           lambda _: self.note(tr("Copia protegida guardada en {0}.").format(destination.name)))

    def handle_rectangle(self, rect):
        if self.view.mode == "redact":
            if rect.width() > 1 and rect.height() > 1:
                box = self.coordinates.box(rect.left(), rect.top(), rect.right(), rect.bottom())
                self.redaction_boxes.setdefault(self.current, []).append(box)
            self.refresh_redaction_marks()
        elif self.view.mode == "signature-stamp":
            self.stamp_rect(rect)
        else:
            self.sign_rect(rect)

    def start_visual_signature(self):
        if not self.path or self.job is not None or not self.editable():
            return
        last_path = str(self.preferences.value("firma/ultima_imagen", "") or "")
        remove_white = self.preferences.value("firma/quitar_fondo", True, type=bool)
        dialog = VisualSignatureDialog(self, initial_path=last_path, remove_white=remove_white)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.stamp_path:
            return
        self.preferences.setValue("firma/ultima_imagen", dialog.stamp_path)
        self.preferences.setValue("firma/quitar_fondo", dialog.remove_white.isChecked())
        self.preferences.sync()
        self.pending_stamp = (dialog.stamp_path, dialog.remove_white.isChecked())
        self.select_mode("signature-stamp")

    def stamp_rect(self, rect):
        if not self.pending_stamp or rect.width() < 4 or rect.height() < 4:
            self.note(tr("Dibuja un recuadro más amplio para la firma visual."))
            return
        if not self.editable():
            return
        stamp_path, remove_white = self.pending_stamp
        box = self.coordinates.box(rect.left(), rect.top(), rect.right(), rect.bottom())
        page = self.current
        self.clear_mode()
        try:
            destination = self.scratch_path()
            add_signature_stamp(
                self.path, destination, page, box, stamp_path, remove_white=remove_white,
            )
            self.load(destination, name=self.name, dirty=True, page=page)
            self.note(tr("Firma visual colocada. Pulsa Ctrl+Z para deshacer o Guardar para conservar los cambios."))
        except Exception as error:
            self.error(error)

    def start_redaction(self):
        if not self.path or self.job is not None:
            return
        self.clear_mode()
        self.view.set_mode("redact")
        self.refresh_redaction_marks()
        self.note(tr("Pulsa Esc para dejar de marcar zonas."))

    def refresh_redaction_marks(self):
        self.view.mark_boxes(self.coordinates, self.redaction_boxes.get(self.current, ()))
        self.update_redaction_strip()
        self.stash_workspace()

    def clear_redaction_page(self):
        self.redaction_boxes.pop(self.current, None)
        if self.view.mode == "redact":
            self.refresh_redaction_marks()
        else:
            self.update_labels()

    def save_redaction(self):
        if not self.path or self.job is not None or not self.redaction_boxes:
            self.note(tr("Marca las zonas que quieres censurar antes de guardar."))
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Guardar copia censurada"))
        dialog.setText(tr("Se borrarán las zonas marcadas. Las demás páginas conservarán el texto y los vectores."))
        dialog.setInformativeText(
            tr("Solo las páginas con marcas se convierten en imágenes. Puedes recuperar su texto con OCR. La copia omite formularios, anotaciones, marcadores y adjuntos.")
        )
        image = dialog.addButton(tr("Censurar sin OCR"), QMessageBox.ButtonRole.ActionRole)
        searchable = dialog.addButton(tr("Con texto seleccionable (OCR)"), QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel).setText(tr("Cancelar"))
        dialog.setDefaultButton(searchable)
        dialog.exec()
        selected = dialog.clickedButton()
        if selected not in (image, searchable):
            return
        destination = self.output_copy(tr("Guardar copia censurada"), tr("censurado"))
        if destination:
            source = self.path
            password = self.document_password or ""
            signed = pdf_has_signatures(self.document_reader)
            protected = self.document_reader.is_encrypted
            if signed and not self.confirm_unsigned_copy():
                return
            boxes = {page: tuple(items) for page, items in self.redaction_boxes.items()}
            use_ocr = selected is searchable

            def redact(path, progress):
                if use_ocr:
                    return redact_searchable_copy(path, destination, boxes, RUNTIME / "tessdata", "spa+eng", progress)
                redact_copy(path, destination, boxes, progress)
                return None

            def process(progress):
                if signed or protected:
                    with TemporaryDirectory(dir=self.scratch) as folder:
                        editable = Path(folder) / "editable.pdf"
                        unlock_pdf(source, editable, password, remove_signatures=signed)
                        return redact(editable, progress)
                return redact(source, progress)

            def done(recognized):
                self.redaction_boxes.clear()
                self.update_labels()
                self.register_work_document(WorkDocument(destination, destination.name, saved_path=destination))
                suffix = "" if recognized is None else tr(" · OCR en {0} páginas").format(recognized)
                self.note(tr("Copia censurada guardada{0}.").format(suffix))

            self.start_job(tr("Creando copia censurada…"), process, done,
                           progress_label=tr("Borrando zonas y reconociendo texto") if use_ocr else tr("Procesando página"),
                           cancellable=True)

    def show_review(self, mode):
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
        if self.focus_layout is not None:
            self.toggle_focus()
        self.review_mode = mode
        self.search_hits = []
        self.search_cursor = -1
        self.view.set_search_ranges({})
        self.review_dock.setWindowTitle(tr("Buscar texto") if mode == "search" else tr("Anotaciones"))
        self.query.setVisible(mode == "search")
        self.search_accents.setVisible(mode == "search")
        self.search_advanced.setVisible(mode == "search")
        self.search_run_btn.setVisible(mode == "search")
        self.search_summary.setVisible(mode == "search")
        self.comment_filter.setVisible(mode == "comments")
        self.comment_kind_filter.setVisible(mode == "comments")
        self.comment_summary.setVisible(mode == "comments")
        self.delete_comment_btn.setVisible(mode == "comments")
        self.annotation_menu.setVisible(mode == "comments")
        self.review_list.clear()
        self.update_search_page_button(None)
        self.search_result_key = None
        self.search_summary.setText(tr("Escribe para buscar en el PDF."))
        if mode == "comments":
            self.review_dock.hide()
            if self.review_widget.parent() is not self.comments_panel:
                self.review_dock.setWidget(None)
                self.comments_panel.layout().addWidget(self.review_widget, 1)
            self.review_widget.show()
            self.choose_navigation(self.comments_panel, refresh=False)
        else:
            if self.review_dock.widget() is not self.review_widget:
                self.review_dock.setWidget(self.review_widget)
            self.review_widget.show()
            self.review_dock.show()
            self.review_dock.raise_()
            if self.navigation.currentWidget() is self.comments_panel:
                self.navigation.setCurrentWidget(self.pages_panel)

    def clear_search_marks_if_closed(self, visible):
        if not visible and self.review_dock.isHidden():
            self.view.set_search_ranges({})

    def _search_active(self):
        return (self.review_mode == "search" and not self.review_dock.isHidden()) or self.find_bar.isVisible()

    def _current_search_key(self):
        return (self.path, self.query.text().strip(), self.search_accents.isChecked(), self.search_advanced.isChecked())

    def sync_find_input(self, text):
        if self.query.text() != text:
            with QSignalBlocker(self.query):
                self.query.setText(text)
        self.schedule_search()

    def sync_find_accents(self, checked):
        if self.search_accents.isChecked() != checked:
            with QSignalBlocker(self.search_accents):
                self.search_accents.setChecked(checked)
        self.schedule_search()

    def open_search(self, *, use_selection=True):
        if self.path is None or self.job is not None:
            return
        if self.fullscreen_state is not None:
            self.toggle_fullscreen()
        self.find_bar.show()
        selected = " ".join(self.view.copied_text.split())[:160] if use_selection and self.view.copied_text.strip() else ""
        initial = selected or self.query.text()
        with QSignalBlocker(self.find_input):
            self.find_input.setText(initial)
        if selected:
            with QSignalBlocker(self.query):
                self.query.setText(selected)
        with QSignalBlocker(self.find_accents_btn):
            self.find_accents_btn.setChecked(self.search_accents.isChecked())
        self.find_input.setFocus()
        self.find_input.selectAll()
        if self.find_input.text().strip():
            self.schedule_search()

    def select_all_text(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextBrowser)) and focus is not self.view:
            focus.selectAll()
            return
        if self.path and self.job is None and not self.view.mode:
            self.view.select_all_text()

    def step_doc_tab(self, delta):
        count = self.doc_tabs.count()
        if count > 1 and self.job is None:
            self.doc_tabs.setCurrentIndex((self.doc_tabs.currentIndex() + delta) % count)

    def show_view_context_menu(self, global_pos):
        if not self.path or self.job is not None:
            return
        menu = QMenu(self)
        has_selection = bool(self.view.copied_text.strip())
        if has_selection:
            menu.addAction(tr("Copiar texto"), self.copy_text)
            menu.addAction(tr("Resaltar"), self.highlight_selection)
            menu.addAction(tr("Subrayar"), lambda: self.highlight_selection(underline=True))
            menu.addAction(tr("Buscar texto seleccionado"), lambda: self.open_search(use_selection=True))
            menu.addSeparator()
        if not self.view.mode:
            menu.addAction(tr("Seleccionar todo"), self.select_all_text)
            menu.addSeparator()
        menu.addAction(tr("Acercar"), lambda: self.view.zoom(1.25))
        menu.addAction(tr("Alejar"), lambda: self.view.zoom(0.8))
        menu.addAction(tr("Tamaño real (100 %)"), lambda: self.view.set_percent(100))
        menu.addAction(tr("Ajustar página"), self.view.fit_page)
        menu.addAction(tr("Ajustar ancho"), self.view.fit_width)
        menu.addSeparator()
        menu.addAction(tr("Buscar texto"), lambda: self.open_search(use_selection=False))
        menu.exec(global_pos)

    def open_search_panel(self):
        if self.path is None or self.job is not None:
            return
        if self.review_mode != "search" or self.review_dock.isHidden():
            self.show_review("search")
        self.query.setFocus()
        self.query.selectAll()
        if self.query.text().strip():
            self.run_search(jump=False)

    def close_find_bar(self):
        self.find_bar.hide()
        self.find_count.setText("")
        if self.review_dock.isHidden() or self.review_mode != "search":
            self.view.set_search_ranges({})
            self.search_hits = []
            self.search_cursor = -1

    def schedule_search(self, *_):
        self.search_pending = None
        self.search_result_key = None
        self.search_hits = []
        self.search_cursor = -1
        self.review_list.clear()
        self.view.set_search_ranges({})
        if self.search_job and self.job is not None:
            self.job.requestInterruption()
        self.search_timer.stop()
        if not self._search_active():
            return
        if self.find_input.text() != self.query.text():
            with QSignalBlocker(self.find_input):
                self.find_input.setText(self.query.text())
        if self.find_accents_btn.isChecked() != self.search_accents.isChecked():
            with QSignalBlocker(self.find_accents_btn):
                self.find_accents_btn.setChecked(self.search_accents.isChecked())
        if self.query.text().strip():
            self.search_timer.start()
        else:
            self.search_summary.setText(tr("Escribe para buscar en el PDF."))
            self.find_count.setText("")

    def run_search(self, *, jump=True):
        self.search_timer.stop()
        term = self.query.text().strip()
        if self.path is None or not term or not self._search_active():
            return
        if self.job is not None:
            self.search_pending = jump
            return
        source = self.path
        match_accents = self.search_accents.isChecked()
        password = self.document_password
        advanced = self.search_advanced.isChecked()
        key = (source, term, match_accents, advanced)
        if advanced:
            try:
                SearchQuery(term)
            except SearchSyntaxError as error:
                self.search_summary.setText(str(error))
                self.find_count.setText(tr("Error"))
                return
        if self.search_result_key == key:
            if jump and self.search_hits:
                self.step_search(1)
            return
        self.review_list.clear()

        self.search_summary.setText(tr("Buscando texto…"))
        self.find_count.setText("…")

        def show_matches(results):
            if results is None or not self._search_active():
                return
            if key != self._current_search_key():
                return
            self.search_result_key = key
            self.search_hits = sorted((result.page, start, length) for result in results for start, length in result.ranges)
            self.view.set_search_ranges({result.page: result.ranges for result in results if result.ranges})
            for result in results:
                first = result.excerpts[0] if result.excerpts else None
                self.review_list.addItem(search_result_item(result.page, first, count=result.count))
            total_hits = len(self.search_hits)
            count = tr("{0} página(s) · {1} coincidencia(s)").format(len(results), sum(result.count for result in results))
            status = count if results else tr("Sin coincidencias. Aplica OCR si el documento está escaneado.")
            self.note(status)
            self.search_summary.setText(status)
            self.find_count.setText(f"0 / {total_hits}" if total_hits else tr("0 resultados"))
            if results and jump:
                if self.search_hits:
                    self.search_cursor = -1
                    self.step_search(1)
                elif self.review_list.count():
                    self.review_list.setCurrentRow(0)

        def search(progress):
            job = QThread.currentThread()
            interrupted = job.isInterruptionRequested
            results = search_advanced_document(source, term, progress, match_accents=match_accents,
                                               interrupted=interrupted, password=password, advanced=advanced)
            return None if interrupted() else results

        self.search_job = True
        self.start_job(tr("Buscando texto…"), search,
                       show_matches, progress_label=tr("Buscando en página"))

    def step_search(self, direction):
        if self.job is not None:
            return
        if not self._search_active() or not self.search_hits:
            self.open_search()
            return
        size = len(self.search_hits)
        if self.search_cursor < 0:
            near = bisect_left(self.search_hits, (self.current, -1, -1))
            self.search_cursor = (near - (direction < 0)) % size
        else:
            self.search_cursor = (self.search_cursor + direction) % size
        self.find_count.setText(f"{self.search_cursor + 1} / {size}")
        page, start, length = self.search_hits[self.search_cursor]
        for row in range(self.review_list.count()):
            item = self.review_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole)[0] == page:
                with QSignalBlocker(self.review_list):
                    self.review_list.setCurrentRow(row)
                self.update_search_page_button(item)
                break
        self.select_search_hit(page, start, length)

    def select_search_hit(self, page, start, length):
        self.goto(page)
        if self.current != page:
            return
        hit = (page, start, length)
        cursor = bisect_left(self.search_hits, hit)
        if cursor < len(self.search_hits) and self.search_hits[cursor] == hit:
            self.search_cursor = cursor
        self.clear_mode()
        self.view.show_text_match(start, length)
        if self.search_cursor >= 0:
            self.search_summary.setText(tr("{0} de {1} coincidencias").format(self.search_cursor + 1, len(self.search_hits)))

    def update_search_page_button(self, item, *_):
        count = item.data(SEARCH_PAGE_COUNT_ROLE) if item is not None else None
        self.search_page_btn.setVisible(self.review_mode == "search" and bool(count and count > 1))

    def open_search_page(self):
        item = self.review_list.currentItem()
        if self.job is not None or not item or not self.search_result_key:
            return
        source, term, match_accents, advanced = self.search_result_key
        password = self.document_password
        page = item.data(Qt.ItemDataRole.UserRole)[0]

        def show(results):
            if not results or not results[0].excerpts:
                return
            result = results[0]
            dialog = QDialog(self)
            dialog.setWindowTitle(tr("Coincidencias de la página {0}").format(page + 1))
            dialog.resize(555, 455)
            layout = QVBoxLayout(dialog)
            if result.count > len(result.excerpts):
                layout.addWidget(QLabel(tr("Se muestran las primeras {0} de {1} coincidencias.").format(
                    len(result.excerpts), result.count)))
            matches = QListWidget()
            matches.setItemDelegate(SearchResultDelegate(matches))
            for excerpt in result.excerpts:
                matches.addItem(search_result_item(page, excerpt))
            matches.setCurrentRow(0)
            matches.itemActivated.connect(dialog.accept)
            layout.addWidget(matches)
            choices = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            choices.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Ir a la coincidencia"))
            choices.accepted.connect(dialog.accept)
            choices.rejected.connect(dialog.reject)
            layout.addWidget(choices)
            if dialog.exec() and matches.currentItem():
                self.open_review_result(matches.currentItem())

        self.start_job(tr("Buscando texto…"),
                       lambda progress: search_advanced_document(source, term, progress, match_accents=match_accents,
                                                                 page_index=page, password=password, advanced=advanced),
                       show, preserve_selection=True)

    def open_comments(self):
        if self.path is None or self.job is not None:
            return
        self.show_review("comments")
        try:
            self.comment_records = list(review_annotations(self.path, password=self.document_password))
            kinds = sorted({kind for _, _, kind, _ in self.comment_records})
            with QSignalBlocker(self.comment_filter):
                self.comment_filter.clear()
            with QSignalBlocker(self.comment_kind_filter):
                self.comment_kind_filter.clear()
                self.comment_kind_filter.addItem(tr("Todos los tipos"), "")
                for kind in kinds:
                    self.comment_kind_filter.addItem(kind, kind)
            self.apply_comment_filter()
            if not self.comment_records:
                self.note(tr("Este PDF no tiene anotaciones de revisión."))
        except Exception as error:
            self.error(error)

    def annotation_accent_color(self, kind):
        key = kind.lower()
        if "nota" in key or "note" in key:
            return "#d97706"
        if "resalt" in key or "highlight" in key:
            return "#ca8a04"
        if "subray" in key or "underline" in key or "tach" in key or "strike" in key:
            return "#2563eb"
        if "texto" in key or "text" in key:
            return "#0d9488"
        return "#7c3aed"

    def apply_comment_filter(self):
        if self.review_mode != "comments":
            return
        query = self.comment_filter.text().strip().lower()
        selected_kind = self.comment_kind_filter.currentData() or ""
        self.review_list.clear()
        total = len(self.comment_records)
        shown = 0
        for page, position, kind, text in self.comment_records:
            if selected_kind and kind != selected_kind:
                continue
            if query and query not in kind.lower() and query not in (text or "").lower() and query not in str(page + 1):
                continue
            item = QListWidgetItem(tr("Pág. {0} · {1}").format(page + 1, kind))
            item.setData(Qt.ItemDataRole.UserRole, [page, position])
            item.setData(
                ANNOTATION_CARD_ROLE,
                {
                    "page_label": tr("Pág. {0}").format(page + 1),
                    "kind": kind,
                    "color": self.annotation_accent_color(kind),
                    "text": text or "",
                    "empty_label": tr("Sin texto adicional"),
                },
            )
            if text:
                item.setToolTip(text)
            self.review_list.addItem(item)
            shown += 1
        if not total:
            self.comment_summary.setText(tr("Este PDF no tiene anotaciones de revisión."))
        elif shown == total:
            self.comment_summary.setText(tr("{0} anotación(es) en el documento.").format(total))
        else:
            self.comment_summary.setText(tr("Mostrando {0} de {1} anotaciones.").format(shown, total))
        has_items = bool(self.review_list.count())
        self.delete_comment_btn.setEnabled(has_items)
        self.annotation_menu.setEnabled(has_items)

    def open_review_result(self, item):
        if self.job is not None:
            return
        page, *detail = item.data(Qt.ItemDataRole.UserRole)
        if self.review_mode == "search":
            try:
                if detail:
                    self.select_search_hit(page, *detail)
                else:
                    self.goto(page)
                    self.view.clear_text()
            except Exception as error:
                self.error(error)
        else:
            self.goto(page)
            if detail and self.coordinates is not None and self.current == page:
                try:
                    annotation = self.document_reader.pages[page].annotations[detail[0]].get_object()
                    left, bottom, right, top = map(float, annotation["/Rect"])
                    self.view.centerOn(QPointF(*self.coordinates.device((left + right) / 2, (bottom + top) / 2)))
                except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                    pass

    def delete_comment(self):
        item = self.review_list.currentItem()
        if not item or not self.editable():
            return
        if QMessageBox.question(self, tr("Eliminar anotación"), tr("¿Eliminar la anotación seleccionada?")) != QMessageBox.StandardButton.Yes:
            return
        page, position = item.data(Qt.ItemDataRole.UserRole)
        try:
            destination = self.scratch_path()
            remove_review_annotation(self.path, destination, page, position)
            self.load(destination, name=self.name, dirty=True, page=self.current)
            self.note(tr("Anotación eliminada. Guarda el PDF para conservar el cambio."))
        except Exception as error:
            self.error(error)

    def start_annotation_edit(self, resize):
        item = self.review_list.currentItem()
        if self.review_mode != "comments" or item is None or not self.editable():
            return
        page, position = item.data(Qt.ItemDataRole.UserRole)
        try:
            mark = reader_for(self.path).pages[page]["/Annots"][position].get_object()
            shape = mark.get("/Subtype")
            if shape not in ("/Text", "/Line", "/Square", "/Circle") or (resize and shape == "/Text"):
                self.note(tr("Puedes mover notas y formas. El cambio de tamaño se aplica a formas."))
                return
            self.goto(page)
            self.clear_mode()
            self.view.set_mode("shape-ellipse" if resize and shape == "/Circle" else
                               "shape-rectangle" if resize else "move-annotation")
            self.annotation_edit = page, position
            self.refresh_field_tint()
            self.view.mark_boxes(self.coordinates, chosen=tuple(map(float, mark["/Rect"])))
            self.note(tr("Dibuja el nuevo recuadro de la forma.") if resize else tr("Haz clic donde quieres situar el centro de la anotación."))
        except Exception as error:
            self.error(error)

    def place_annotation_edit(self, **geometry):
        page, position = self.annotation_edit
        try:
            destination = self.scratch_path()
            change_annotation_box(self.path, destination, page, position, **geometry)
            self.load(destination, name=self.name, dirty=True, page=page)
            self.note(tr("Anotación actualizada."))
        except Exception as error:
            self.error(error)

    def copy_page(self):
        if self.job is not None or not self.path:
            return
        try:
            with pdfium_reader(self.path, password=self.document_password) as document:
                image = render_page(document, self.current, dpi=200)
            QApplication.clipboard().setImage(as_qimage(image))
            self.note(tr("Página copiada. Pégala en Word con Ctrl+V."))
        except Exception as error:
            self.error(error)

    def toggle_signature_details(self, visible):
        self.signature_info.setVisible(visible)
        self.signature_details_toggle.setText(tr("Ocultar detalles") if visible else tr("Ver detalles"))

    def populate_signatures_list(self, select_field=None):
        query = self.signature_filter.text().strip().casefold() if hasattr(self, "signature_filter") else ""
        self.signatures_list.clear()
        total = len(self.signature_data)
        shown = 0
        target_row = 0
        for index, signature in enumerate(self.signature_data):
            haystack = " ".join(str(signature.get(k) or "") for k in ("name", "identifier", "organization", "field_name", "signed_at")).casefold()
            if query and query not in haystack:
                continue
            integrity = signature.get("integrity")
            valid_now = signature.get("valid_now")
            if integrity is False:
                color, status = "#dc2626", tr("Alterada")
            elif integrity is True and valid_now is True:
                color, status = "#16a34a", tr("Íntegra · Vigente")
            elif integrity is True and valid_now is False:
                color, status = "#d97706", tr("Íntegra · Caducada")
            elif integrity is True:
                color, status = "#0284c7", tr("Íntegra")
            else:
                color, status = "#64748b", tr("Sin comprobar")
            date_label = str(signature.get("signed_at") or "").split(" ")[0]
            body = signature["name"]
            if signature.get("identifier"):
                body = f'{body}\n{signature["identifier"]}'
            item = QListWidgetItem(body)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setData(ANNOTATION_CARD_ROLE, {
                "color": color,
                "kind": status,
                "page_label": date_label,
                "text": body,
            })
            item.setToolTip(f'{signature["name"]} ({signature["field_name"]})\n{signature.get("signed_at") or ""}')
            self.signatures_list.addItem(item)
            if select_field and signature["field_name"] == select_field:
                target_row = shown
            shown += 1
        if total == 0:
            self.signature_summary.setText(tr("Sin firmas"))
            self.signature_info.setPlainText(tr("Este PDF no contiene firmas digitales incrustadas."))
        elif shown == 0:
            self.signature_summary.setText(tr("0 de {0} firmas").format(total))
            self.signature_info.setPlainText(tr("Ninguna firma coincide con el filtro."))
        else:
            self.signature_summary.setText(
                tr("{0} firmas").format(total) if shown == total else tr("{0} de {1} firmas").format(shown, total)
            )
            self.signatures_list.setCurrentRow(target_row)

    def signature_explorer(self, field_name=None):
        if self.job is not None or not self.path:
            return
        source = self.path
        password = self.document_password
        self.choose_navigation(self.signatures_panel, refresh=False)

        def show(signatures):
            self.signature_cache_key = source
            self.signature_data = signatures
            self.populate_signatures_list(select_field=field_name)

        if self.signature_cache_key == source:
            if field_name:
                for row in range(self.signatures_list.count()):
                    item = self.signatures_list.item(row)
                    idx = item.data(Qt.ItemDataRole.UserRole)
                    if idx is not None and self.signature_data[idx]["field_name"] == field_name:
                        self.signatures_list.setCurrentRow(row)
                        break
            return
        if self.signature_strip.isHidden():
            show([])
            return
        self.signatures_list.clear()
        self.signature_summary.setText("")
        self.signature_info.setPlainText(tr("Leyendo firmas del PDF…"))

        def inspect(_):
            from pdf_sign import inspect_pdf_signatures
            return inspect_pdf_signatures(source, password=password)

        self.start_job(
            tr("Leyendo firmas del PDF…"),
            inspect,
            show,
            preserve_selection=True,
        )

    def show_signature_details(self, item):
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else -1
        if isinstance(index, int) and 0 <= index < len(self.signature_data):
            self.signature_info.setHtml(signature_details_html(self.signature_data[index]))
            self.signature_info.verticalScrollBar().setValue(0)

    def jump_to_signature(self, item):
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else -1
        if self.job is not None or not isinstance(index, int) or not 0 <= index < len(self.signature_data):
            return
        name = self.signature_data[index]["field_name"]
        for page, source in enumerate(self.document_reader.pages):
            match = next((box for field, box, signed in signature_widgets(source) if signed and field == name), None)
            if match:
                self.goto(page)
                left, bottom, right, top = match
                if self.coordinates is not None and self.current == page:
                    self.view.centerOn(QPointF(*self.coordinates.device((left + right) / 2, (bottom + top) / 2)))
                break

    def export_actions(self):
        formats = (("Word (.docx)", "docx"), ("Excel (.xlsx)", "xlsx"), ("CSV (.csv)", "csv"),
                   ("Markdown (.md)", "md"), (tr("Texto (.txt)"), "txt"))
        return [(f"{name}…", lambda kind=kind: self.export_pdf(kind)) for name, kind in formats] + [
            (tr("Imagen PNG…"), lambda: self.export_pdf("png")),
            (tr("PDF/A (archivo)…"), self.export_pdf_archive),
            (tr("Copiar página como imagen"), self.copy_page),
        ]

    def update_export_menu(self, menu):
        single_only = not self.batch_selection_count()
        for action in menu.actions()[-2:]:
            action.setVisible(single_only)

    def export_pdf(self, kind):
        if not self.path or self.job is not None:
            return
        batch = self.selected_documents() if self.batch_selection_count() else []
        if kind == "png" and not batch:
            self.save_png()
            return
        self.view.finish_inline()
        format_name = {"docx": "Word", "xlsx": "Excel", "csv": "CSV", "md": "Markdown", "txt": tr("texto"), "png": "PNG"}[kind]
        current_page = self.current
        dialog = QDialog(self)
        title = tr("Exportar a {0}").format(format_name)
        dialog.setWindowTitle(tr("{0} · {1} PDF").format(title, len(batch)) if batch else title)
        dialog.setMinimumWidth(480)
        layout = QFormLayout(dialog)
        sources = [state.name for state in batch] if batch else [self.name]
        scope = QLabel("\n".join(sources[:3]))
        if len(sources) > 3:
            scope.setText(tr("{0}\ny {1} más").format(scope.text(), len(sources) - 3))
        scope.setTextFormat(Qt.TextFormat.PlainText)
        scope.setWordWrap(True)
        scope.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        scope.setToolTip("\n".join(sources))
        layout.addRow(tr("Aplicar a"), scope)
        page_scope = QComboBox()
        page_scope.addItem(tr("Todas las páginas de cada PDF") if batch else tr("Todo el documento ({0})").format(self.count), "all")
        if not batch:
            page_scope.addItem(tr("Página actual ({0})").format(current_page + 1), "current")
        page_scope.addItem(tr("Rango personalizado"), "range")
        layout.addRow(tr("Páginas"), page_scope)
        pages = QLineEdit()
        pages.setPlaceholderText(tr("Por ejemplo, 1,3-5"))
        layout.addRow(tr("Rango"), pages)
        layout.setRowVisible(pages, False)

        def update_scope():
            custom = page_scope.currentData() == "range"
            layout.setRowVisible(pages, custom)
            if custom:
                pages.setFocus()
            QTimer.singleShot(0, dialog.adjustSize)

        page_scope.currentIndexChanged.connect(update_scope)
        word_mode = QComboBox()
        word_mode.addItem(tr("Con formato"), True)
        word_mode.addItem(tr("Texto y tablas básicos"), False)
        if kind == "docx":
            layout.addRow(tr("Modo de Word"), word_mode)
        ocr = QCheckBox(tr("Reconocer texto con OCR"))
        language = QComboBox()
        for label, code in ((tr("Español"), "spa"), (tr("Inglés"), "eng"), (tr("Español e inglés"), "spa+eng")):
            language.addItem(label, code)
        language.setCurrentIndex(2)
        unruled = QCheckBox(tr("Buscar columnas de texto alineadas"))
        if kind in ("docx", "md", "txt"):
            ocr.setChecked(True)
            ocr.toggled.connect(language.setEnabled)
            layout.addRow(tr("Páginas sin texto"), ocr)
            layout.addRow(tr("Idioma del OCR"), language)
            description = {
                "docx": tr("Conserva estilos, colores, imágenes y tablas. La distribución se aproxima al PDF. Sin texto editable, la página se incluye como imagen."),
                "md": (tr("Guarda un archivo Markdown por PDF.") if batch else
                       tr("Extrae texto y tablas y abre una vista previa para copiar o guardar el resultado.")),
                "txt": tr("Exporta el texto en UTF-8."),
            }[kind]
        elif kind == "png":
            description = tr("Guarda una imagen por página a 144 ppp. El nombre incluye el número de página original.")
        else:
            layout.addRow(tr("Tablas sin bordes"), unruled)
            description = tr("Extrae las tablas detectadas. Si vienen de un escaneo, aplica primero el OCR.")
        hint = QLabel(description, objectName="muted")
        hint.setWordWrap(True)
        hint.setMinimumHeight(45)
        layout.addRow(hint)
        if kind == "docx":
            def update_word_mode():
                formatted = word_mode.currentData()
                layout.setRowVisible(ocr, not formatted)
                layout.setRowVisible(language, not formatted)
                hint.setText(description if formatted else tr("Exporta texto y tablas editables con el formato básico de Word."))
                QTimer.singleShot(0, dialog.adjustSize)

            word_mode.currentIndexChanged.connect(update_word_mode)
            update_word_mode()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        next_step = tr("Elegir carpeta…") if batch else tr("Vista previa") if kind == "md" else tr("Elegir dónde guardar…")
        proceed = buttons.button(QDialogButtonBox.StandardButton.Ok)
        proceed.setText(next_step)
        proceed.setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        selected = None

        def accept_pages():
            nonlocal selected
            try:
                scope = page_scope.currentData()
                if scope == "range" and not pages.text().strip():
                    raise ValueError(tr("Escribe las páginas que quieras exportar."))
                if not batch:
                    selected = ([current_page] if scope == "current" else
                                page_range(pages.text() if scope == "range" else "", self.count))
            except ValueError as error:
                QMessageBox.warning(dialog, tr("Páginas"), str(error))
                return
            dialog.accept()

        buttons.accepted.connect(accept_pages)
        if not dialog.exec():
            return
        initial = self.saved_path.parent if self.saved_path else Path(self.name).parent
        title = Path(self.name).stem
        suggested_path = str(initial / f"{title}.{kind}")
        source = self.path
        formatted = kind == "docx" and word_mode.currentData()
        tessdata = RUNTIME / "tessdata" if ocr.isChecked() and not formatted else None
        language_code, detect_unruled = language.currentData(), unruled.isChecked()
        if batch:
            expression = pages.text() if page_scope.currentData() == "range" else ""

            def convert(source, destination, name):
                count = len(reader_for(source, allow_empty_password=True).pages)
                indices = page_range(expression, count)
                if kind == "png":
                    outputs = []
                    digits = max(3, len(str(count)))
                    with pdfium_reader(source) as document:
                        for index in indices:
                            check_cancellation()
                            staged = destination.with_name(f"{destination.stem}-{index}.png")
                            render_page(document, index, dpi=144).save(staged, "PNG")
                            outputs.append((staged, tr("{0} - página {1:0{2}d}.png").format(Path(name).stem, index + 1, digits)))
                    return outputs
                if kind == "md":
                    markdown, _ = markdown_from_pdf(source, Path(name).stem, indices, check_cancellation,
                                                   tessdata=tessdata, language=language_code)
                    destination.write_text(markdown, encoding="utf-8")
                else:
                    export_document(source, destination, kind, indices, check_cancellation, tessdata=tessdata,
                                    language=language_code, unruled=detect_unruled, formatted=formatted)

            self.run_workspace_batch(batch, tr("Exportar a {0}").format(format_name), tr("convertido"), convert, extension=kind)
            return
        if kind == "md":
            self.start_job(
                tr("Preparando Markdown…"),
                lambda progress: markdown_from_pdf(
                    source, title, selected, progress, tessdata=tessdata, language=language_code
                ),
                lambda result: self.preview_markdown(suggested_path, *result),
                preserve_selection=True,
                progress_label=tr("Preparando Markdown. Página"), cancellable=True,
            )
            return
        destination = self.save_as(tr("Exportar a {0}").format(format_name), suggested_path, kind)
        if not destination:
            return

        def finished(skipped):
            self.note(tr("Exportado a {0} · {1}").format(format_name, destination.name))
            if skipped:
                preview = ", ".join(map(str, skipped[:15])) + ("…" if len(skipped) > 15 else "")
                missing = tr("sin tablas detectadas") if kind in ("xlsx", "csv") else tr("sin texto reconocible")
                QMessageBox.information(
                    self, tr("Exportación completada"), tr("Se guardó {0}.\nPáginas {1}: {2}.").format(destination.name, missing, preview)
                )

        self.start_job(
            tr("Exportando a {0}…").format(format_name),
            lambda progress: export_document(source, destination, kind, selected, progress,
                                              tessdata=tessdata, language=language_code, unruled=detect_unruled,
                                              formatted=formatted),
            finished,
            preserve_selection=True,
            progress_label=tr("Exportando a {0}. Página").format(format_name), cancellable=True,
        )

    def preview_markdown(self, suggested_path, markdown, skipped):
        self.note(tr("Vista previa de Markdown lista."))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Vista previa de Markdown"))
        dialog.resize(800, 620)
        layout = QVBoxLayout(dialog)
        if skipped:
            numbers = ", ".join(map(str, skipped[:15])) + ("…" if len(skipped) > 15 else "")
            label = QLabel(tr("Páginas sin texto reconocible: {0}").format(numbers), objectName="muted")
            label.setWordWrap(True)
            layout.addWidget(label)
        tabs = QTabWidget()
        preview = QTextBrowser()
        preview.setOpenLinks(False)
        features = QTextDocument.MarkdownFeature
        preview.document().setMarkdown(markdown, features.MarkdownDialectGitHub | features.MarkdownNoHTML)
        source = QPlainTextEdit()
        source.setReadOnly(True)
        source.setPlainText(markdown)
        tabs.addTab(preview, tr("Vista previa"))
        tabs.addTab(source, "Markdown")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Cerrar"))
        buttons.rejected.connect(dialog.reject)
        copy = buttons.addButton(tr("Copiar Markdown"), QDialogButtonBox.ButtonRole.ActionRole)
        save = buttons.addButton(tr("Guardar .md…"), QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        def copy_markdown():
            QApplication.clipboard().setText(markdown)
            copy.setText(tr("Copiado"))

        def save_markdown():
            destination = self.save_as(tr("Guardar Markdown"), suggested_path, "md")
            if not destination:
                return
            try:
                with atomic_output(destination) as temporary:
                    temporary.write_text(markdown, encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(dialog, tr("Guardar Markdown"), str(error))
                return
            self.note(tr("Exportado a Markdown · {0}").format(destination.name))
            dialog.accept()

        copy.clicked.connect(copy_markdown)
        save.clicked.connect(save_markdown)
        dialog.exec()

    def save_png(self):
        if not self.path or self.job is not None:
            return
        destination = self.save_as(tr("Guardar PNG"), tr("{0} - página {1}.png").format(Path(self.name).stem, self.current + 1), "png")
        if destination:
            try:
                with pdfium_reader(self.path, password=self.document_password) as document:
                    image = render_page(document, self.current, dpi=200)
                with atomic_output(destination) as temporary:
                    image.save(temporary, format="PNG", dpi=(200, 200))
                self.note(tr("Página guardada como PNG."))
            except Exception as error:
                self.error(error)

    def text_point(self, point):
        if self.view.mode == "move-annotation" and self.annotation_edit:
            self.place_annotation_edit(center=self.coordinates.at(point.x(), point.y()))
            return
        if (self.view.mode or "").startswith("measure-"):
            self.measure_point(point)
            return
        if self.view.mode == "edit-text":
            self.edit_page_text(point)
            return
        if self.view.mode == "note":
            self.add_note(point)
            return
        if self.view.mode == "form":
            self.edit_form_field(point)
            return
        self.clear_mode()
        text, accepted = QInputDialog.getMultiLineText(self, tr("Añadir texto"), tr("Texto:"))
        if not accepted or not text.strip():
            return
        size, accepted = QInputDialog.getInt(self, tr("Tamaño de texto"), tr("Puntos:"), 12, 6, 72)
        if not accepted or not self.editable():
            return
        try:
            destination = self.scratch_path()
            add_text(self.path, destination, self.current, self.coordinates, (point.x(), point.y()), text, size)
            self.load(destination, name=self.name, dirty=True, page=self.current)
        except Exception as error:
            self.error(error)

    def edit_page_text(self, point):
        try:
            block = text_block_at(self.path, self.current, *self.coordinates.at(point.x(), point.y()),
                                  password=self.document_password)
            if not block:
                self.note(tr("No hay texto editable en ese punto. Si es una imagen escaneada, puedes anotar o añadir texto."))
                return
            index = self.current

            def save(value):
                if not self.editable():
                    return
                try:
                    destination = self.scratch_path()
                    replace_text_block(self.path, destination, index, block, value)
                    self.load(destination, name=self.name, dirty=True, page=index)
                    self.select_mode("edit-text")
                    self.note(tr("Texto guardado en el borrador. Revisa el espacio con el texto vecino."))
                except Exception as error:
                    self.error(error)

            self.view.edit_existing_text(block, self.coordinates, save)
        except Exception as error:
            self.error(error)

    def toggle_bookmarks(self):
        self.choose_navigation(self.bookmarks_panel, toggle=True)

    def load_bookmarks(self, reader):
        self.bookmark_tree.clear()

        def populate(parent, entries):
            last = parent
            for entry in entries:
                if isinstance(entry, list):
                    populate(last, entry)
                    continue
                target = reader.get_destination_page_number(entry)
                item = QTreeWidgetItem(parent, [str(entry.title)])
                if target is not None and target >= 0:
                    item.setData(0, Qt.ItemDataRole.UserRole, target)
                last = item

        try:
            populate(self.bookmark_tree, reader.outline)
            self.load_structure(reader)
        except Exception as error:
            QTreeWidgetItem(self.bookmark_tree, [tr("No se pudo leer toda la estructura: {0}").format(error)])
        if not self.bookmark_tree.topLevelItemCount():
            QTreeWidgetItem(self.bookmark_tree, [tr("El PDF no tiene marcadores ni etiquetas")])
        self.bookmark_tree.expandToDepth(0)

    def load_structure(self, reader):
        root = reader.root_object.get("/StructTreeRoot")
        if root is None:
            return
        tree = QTreeWidgetItem(self.bookmark_tree, [tr("Etiquetas del documento")])
        page_numbers = {page.indirect_reference.idnum: index for index, page in enumerate(reader.pages)
                        if page.indirect_reference is not None}
        seen = set()

        def visit(parent, value, page_index=None, depth=0):
            if value is None or depth > 50 or len(seen) >= 8000:
                return None
            node = value.get_object()
            if isinstance(node, list):
                first = None
                for child in node:
                    target = visit(parent, child, page_index, depth + 1)
                    if first is None:
                        first = target
                return first
            if not isinstance(node, dict):
                return page_index
            if id(node) in seen:
                return None
            seen.add(id(node))
            page = node.get("/Pg")
            if page is not None:
                page_index = page_numbers.get(getattr(page, "idnum", None), page_index)
            role = node.get("/S")
            item = parent
            if role:
                title = node.get("/T") or node.get("/Alt")
                item = QTreeWidgetItem(parent, [f"{str(role)[1:]} · {title}" if title else str(role)[1:]])
            child_page = visit(item, node.get("/K"), page_index, depth + 1)
            destination = page_index if page_index is not None else child_page
            if item is not parent and destination is not None:
                item.setData(0, Qt.ItemDataRole.UserRole, destination)
            return destination

        visit(tree, root)

    def open_bookmark(self, item, column):
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if target is not None:
            self.goto(target)

    def highlight_selection(self, *, underline=False):
        if not self.view.text_marks:
            self.note(tr("Selecciona el texto que quieres resaltar."))
            return
        boxes = []
        for mark in self.view.text_marks:
            rect = mark.rect()
            boxes.append(self.coordinates.box(rect.left(), rect.top(), rect.right(), rect.bottom()))
        self.write_annotation(boxes, underline=underline)

    def start_note(self):
        if self.path and self.job is None:
            self.clear_mode()
            self.view.set_mode("note")
            self.note(tr("Haz clic en la posición de la nota."))

    def add_note(self, point):
        self.clear_mode()
        note, accepted = QInputDialog.getMultiLineText(self, tr("Añadir nota"), tr("Nota"))
        if accepted and note.strip():
            x, y = self.coordinates.at(point.x(), point.y())
            self.write_annotation([(x, y - 18, x + 18, y)], note.strip())

    def write_annotation(self, boxes, note=None, *, underline=False):
        if not self.editable():
            return
        try:
            destination = self.scratch_path()
            add_review_annotation(self.path, destination, self.current, boxes, note, underline=underline)
            self.load(destination, name=self.name, dirty=True, page=self.current)
        except Exception as error:
            self.error(error)

    def header_footer(self, *, numbering=False):
        workspace = self.selected_documents() if self.batch_selection_count() else []
        batch = bool(workspace)
        if batch:
            sources = [state.path for state in workspace]
        elif not self.editable():
            return
        dialog = QDialog(self)
        title = tr("Numerar páginas") if numbering else tr("Encabezado o pie de página")
        dialog.setWindowTitle(tr("{0} · {1} PDF").format(title, len(sources)) if batch else title)
        dialog.resize(520 if not numbering else 410, 340 if not numbering else 285)
        layout = QFormLayout(dialog)
        if numbering:
            first_number = QSpinBox()
            first_number.setRange(1, 1000000)
            first_number.setValue(1)
            first_number.setToolTip(tr("Número de la primera página incluida en el rango"))
            layout.addRow(tr("Número inicial"), first_number)
        else:
            text = HeaderEditor()
            layout.addRow(text)
        pages = QLineEdit()
        pages.setPlaceholderText(tr("Todas · por ejemplo, 1,3-5,8"))
        if batch:
            pages.setToolTip(tr("Se usa el mismo intervalo en cada PDF."))
        position = QComboBox()
        position.addItems([tr("Pie"), tr("Encabezado")])
        alignment = QComboBox()
        alignment.addItems([tr("Izquierda"), tr("Centro"), tr("Derecha")])
        alignment.setCurrentIndex(1)
        settings = []
        for label, minimum, maximum, initial in (
            (tr("Margen lateral"), 0, 500, 36), (tr("Margen vertical"), 0, 500, 24), (tr("Tamaño"), 6, 96, 10),
        ):
            setting = QSpinBox()
            setting.setRange(minimum, maximum)
            setting.setSuffix(" pt")
            setting.setValue(initial)
            settings.append((label, setting))
        for label, widget in [(tr("Páginas"), pages), (tr("Posición"), position), (tr("Alineación"), alignment), *settings]:
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Aplicar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        preview = buttons.addButton(tr("Vista previa"), QDialogButtonBox.ButtonRole.ActionRole)
        layout.addRow(buttons)

        def settings_for(name=None):
            label = "{página}" if numbering else text.formatted_lines()
            return (label, position.currentIndex() == 1, ("left", "center", "right")[alignment.currentIndex()],
                    *(setting.value() for _, setting in settings), name, first_number.value() if numbering else None)

        def show_preview():
            source = Path(sources[0]) if batch else self.path
            working = self.scratch_path()
            try:
                count = len(reader_for(source).pages)
                index = page_range(pages.text(), count)[0]
                add_header_footer(source, working, [index], *settings_for(None if batch else self.name))
                with pdfium_reader(working) as doc:
                    image = render_page(doc, index, width=540)
                viewer = QDialog(dialog)
                viewer.setWindowTitle(tr("Vista previa · página {0}").format(index + 1))
                content = QVBoxLayout(viewer)
                label = QLabel()
                label.setPixmap(QPixmap.fromImage(as_qimage(image)).scaled(
                    540, 620, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                content.addWidget(label)
                content.addWidget(button("Cerrar", viewer.accept))
                viewer.exec()
            except Exception as error:
                QMessageBox.warning(dialog, tr("Vista previa"), str(error))
            finally:
                working.unlink(missing_ok=True)

        preview.clicked.connect(show_preview)
        while dialog.exec():
            try:
                settings_values = settings_for(None if batch else self.name)
                if batch:
                    output = QFileDialog.getExistingDirectory(self, tr("Guardar copias en"))
                    if not output:
                        continue
                    expression = pages.text()
                    def apply_to_document(source, destination, name):
                        indices = page_range(expression, len(reader_for(source).pages))
                        values = (*settings_values[:-2], name, settings_values[-1])
                        add_header_footer(source, destination, indices, *values)

                    self.run_workspace_batch(workspace, title, "numerado" if numbering else tr("con encabezado o pie"),
                                             apply_to_document, directory=output, editable_sources=True)
                    return
                indices = page_range(pages.text(), self.count)
                destination = self.scratch_path()
                add_header_footer(self.path, destination, indices, *settings_values)
                self.load(destination, name=self.name, dirty=True, page=self.current)
                self.note(tr("{0} página(s) numeradas.").format(len(indices)) if numbering else tr("Texto añadido en {0} página(s).").format(len(indices)))
                return
            except Exception as error:
                self.error(error)

    def list_form_fields(self):
        try:
            if not self.prepare_form():
                return
            fields = {field.name: field for field in form_fields(reader_for(self.path), self.current)}
            if not fields:
                self.note(tr("Esta página no tiene campos AcroForm editables."))
                return
            name, accepted = QInputDialog.getItem(self, tr("Formulario"), tr("Campo de esta página"), list(fields), 0, False)
            if accepted:
                self.apply_form_field(fields[name])
        except Exception as error:
            self.error(error)

    def finalize_form(self, freeze):
        verb = tr("Fijar respuestas") if freeze else tr("Vaciar formulario")
        question = (tr("¿Convertir los campos y sus respuestas en contenido fijo de las páginas?") if freeze else
                    tr("¿Borrar las respuestas de todos los campos editables del documento?"))
        if QMessageBox.question(self, verb, question) != QMessageBox.StandardButton.Yes:
            return
        try:
            if not self.prepare_form():
                return
            destination = self.scratch_path()
            operation = flatten_form if freeze else clear_form
            operation(self.path, destination)
            self.load(destination, name=self.name, dirty=True, page=self.current)
            self.note(tr("Respuestas fijadas. Guarda el PDF para conservarlas.") if freeze else tr("Formulario vaciado."))
        except Exception as error:
            self.error(error)

    def start_form(self):
        if self.view.mode == "form":
            self.clear_mode()
            return
        try:
            if not self.current_fields:
                self.clear_mode()
                self.note(tr("Esta página no tiene campos AcroForm editables."))
                return
            self.view.set_mode("form")
            self.form_btn.setChecked(True)
            self.text_btn.setChecked(False)
            self.view.mark_boxes()
            self.tint_btn.setChecked(True)
            self.refresh_field_tint()
            self.note(tr("Haz clic en un campo resaltado para rellenarlo."))
        except Exception as error:
            self.clear_mode()
            self.error(error)

    def prepare_form(self):
        if not self.editable():
            return False
        if not has_xfa(reader_for(self.path)):
            return True
        if self.form_kind == "xfa":
            self.note(tr("Este PDF usa XFA y no tiene campos AcroForm que PDFiu pueda editar."))
            return False
        question = (tr("Este formulario incluye XFA y PDFiu puede intentar usar sus campos AcroForm. La copia conserva los campos compatibles y pierde la lógica dinámica XFA. Conserva el original si un trámite exige el formato XFA. ¿Preparar la copia?"))
        if QMessageBox.question(self, tr("Formulario híbrido"), question) != QMessageBox.StandardButton.Yes:
            return False
        original = self.saved_path or self.path
        destination = self.scratch_path()
        convert_hybrid_form(self.path, destination)
        self.load(destination, name=tr("{0} - formulario editable.pdf").format(Path(self.name).stem), dirty=True, page=self.current)
        self.protected_source = original
        return True

    def edit_form_field(self, point):
        x, y = self.coordinates.at(point.x(), point.y())
        try:
            field = next((item for item in self.current_fields
                          if min(item.box[0], item.box[2]) <= x <= max(item.box[0], item.box[2])
                          and min(item.box[1], item.box[3]) <= y <= max(item.box[1], item.box[3])), None)
            if field is None:
                return
            self.apply_form_field(field)
        except Exception as error:
            self.error(error)

    def apply_form_field(self, field):
        manual = self.view.mode == "form"
        if field.kind == "/Ch" and field.flags & (1 << 21):
            value, accepted = self.form_multiple_values(field)
            if accepted:
                self.save_field_value(field, value, manual)
        elif field.kind == "/Btn" and not field.flags & (1 << 15) and len(field.options) == 2:
            values = {value for _, value in field.options}
            if "/Off" in values:
                value = next(iter(values - {"/Off"})) if field.value in ("", "/Off") else "/Off"
                self.save_field_value(field, value, manual)
            else:
                self.view.edit_inline(field, self.coordinates, lambda value: self.save_field_value(field, value, manual))
        else:
            self.view.edit_inline(field, self.coordinates, lambda value: self.save_field_value(field, value, manual))
            self.note(tr("Escribe en el campo. Enter guarda el cambio y Esc lo cancela.")
                      if not field.flags & (1 << 12) else
                      tr("Escribe en el campo. Ctrl+Enter guarda el cambio y Esc lo cancela."))

    def save_field_value(self, field, value, manual):
        try:
            if not self.prepare_form():
                return
            field = next((current for current in self.current_fields if current.name == field.name), None)
            if field is None:
                self.note(tr("No se encontró ese campo en la copia editable."))
                return
            destination = self.scratch_path()
            fill_form(self.path, destination, field, value)
            self.load(destination, name=self.name, dirty=True, page=self.current)
            if manual:
                self.start_form()
            self.note(tr("Campo actualizado. Guarda el PDF para conservar el cambio."))
        except Exception as error:
            self.error(error)

    def form_multiple_values(self, field):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Seleccionar varias opciones"))
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(QLabel(field.name))
        choices = QListWidget()
        choices.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for label, value in field.options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            choices.addItem(item)
            item.setSelected(value in field.value if isinstance(field.value, tuple) else value == field.value)
        layout.addWidget(choices)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        accepted = dialog.exec()
        return [item.data(Qt.ItemDataRole.UserRole) for item in choices.selectedItems()], accepted

    def choose_ocr_language(self):
        models = {tr("Español + inglés"): "spa+eng", tr("Español"): "spa", tr("Inglés"): "eng"}
        language, accepted = QInputDialog.getItem(self, "OCR", tr("Idiomas del documento"), list(models), 0, False)
        return models[language] if accepted else None

    def run_ocr(self):
        if self.batch_selection_count():
            self.ocr_workspace()
            return
        if not self.path or self.job is not None:
            return
        scopes = [tr("Documento completo"), tr("Solo la página actual")]
        scope, ok = QInputDialog.getItem(self, "OCR", tr("Páginas a reconocer"), scopes, 0, False)
        if not ok:
            return
        model = self.choose_ocr_language()
        if not model or not self.editable():
            return
        source, destination, page = self.path, self.scratch_path(), self.current
        indices = None if scope == scopes[0] else (page,)

        def done(count):
            if count:
                self.load(destination, name=self.name, dirty=True, page=page)
                self.note(tr("OCR aplicado a {0} {1}.").format(count, tr("página") if count == 1 else tr("páginas")))
            else:
                self.note(tr("No se encontró texto nuevo en páginas sin capa de texto."))

        self.start_job(
            tr("Iniciando OCR…"), lambda progress: ocr_document(source, destination, RUNTIME / "tessdata", model, progress, indices=indices),
            done, progress_label=tr("Reconociendo página"), cancellable=True,
        )

    def sign_rect(self, rectangle):
        box = self.coordinates.box(rectangle.left(), rectangle.top(), rectangle.right(), rectangle.bottom())
        source, page = self.path, self.current
        try:
            reader = reader_for(source)
            validate_signature_box(reader.pages[page], box)
            all_pages = False
            if len(reader.pages) > 1:
                scope = QMessageBox(self)
                scope.setWindowTitle(tr("Páginas a firmar"))
                scope.setText(tr("¿Dónde quieres aplicar el recuadro que dibujaste en la página {0}?").format(page + 1))
                scope.setInformativeText(tr("PDFiu crea una firma digital por página. Windows puede pedir el PIN más de una vez."))
                current = scope.addButton(tr("Solo esta página"), QMessageBox.ButtonRole.AcceptRole)
                every = scope.addButton(tr("Las {0} páginas").format(len(reader.pages)), QMessageBox.ButtonRole.ActionRole)
                scope.addButton(QMessageBox.StandardButton.Cancel)
                scope.setDefaultButton(current)
                scope.exec()
                selected = scope.clickedButton()
                if selected not in (current, every):
                    self.view.set_mode("signature")
                    return
                all_pages = selected is every
            positions = signature_plan(reader, page, box, all_pages=all_pages)
        except ValueError as error:
            self.view.set_mode("signature")
            self.note(str(error))
            return

        def choose(credentials):
            destination = self.output_copy(tr("Guardar PDF firmado"), tr("firmado"))
            if not destination:
                self.clear_mode()
                return
            def sign(progress):
                from pdf_sign import sign_document_pages
                sign_document_pages(source, destination, positions, progress, **credentials)

            def done(_):
                self.new_work_document(destination, page=page)
                self.note(tr("PDF guardado con {0} firma(s) nueva(s).").format(len(positions)))

            self.start_job(tr("Firmando PDF… Si Windows lo solicita, introduce el PIN."), sign, done,
                           preserve_selection=True, progress_label=tr("Aplicando firma"))

        self.choose_certificate(choose, preserve_selection=True)

    def sign_workspace(self):
        selected = self.selected_documents()
        if not selected:
            self.note(tr("Selecciona los PDF en la mesa. Usa Ctrl o Mayús para marcar varios."))
            return
        self.batch_dialog([str(state.path) for state in selected],
                          {str(state.path): state.name for state in selected})

    def batch_dialog(self, sources=None, names=None):
        if self.job is not None:
            return
        self.view.finish_inline()
        if sources is None:
            sources, _ = QFileDialog.getOpenFileNames(self, tr("Elegir PDFs para firmar"), filter="PDF (*.pdf)")
        if not sources:
            return
        dialog = BatchDialog(self, sources, names)
        if not dialog.exec():
            return
        placements = dialog.placements()

        def choose(credentials):
            directory = QFileDialog.getExistingDirectory(self, tr("Carpeta para los PDFs firmados"))
            if not directory:
                return

            def done(paths):
                for path in paths:
                    self.register_work_document(WorkDocument(path, path.name, saved_path=path))
                self.note(tr("{0} PDF firmados. Carpeta: {1}").format(len(paths), directory))
                QMessageBox.information(self, tr("Lote firmado"), tr("Se guardaron {0} PDF en:\n{1}").format(len(paths), directory))

            def sign(progress):
                from pdf_sign import sign_batch
                return sign_batch(placements, directory, progress, names=names, **credentials)

            self.start_job(
                tr("Firmando lote…"), sign,
                done, progress_label=tr("Aplicando firma"),
            )

        self.choose_certificate(choose)

    def choose_certificate(self, callback, *, preserve_selection=False):
        def choose(result):
            identities, warning = result
            dialog = CertificateDialog(self, identities, warning)
            if dialog.exec():
                callback(dict(identity=dialog.identity, pfx=dialog.pfx, password=dialog.password))
            else:
                self.clear_mode()

        def identities(_):
            if sys.platform != "win32":
                return [], tr("En este sistema, firma con un certificado .p12 o .pfx.")
            try:
                from pdf_sign import windows_cert
                return windows_cert("list"), None
            except (OSError, ValueError, TimeoutError) as error:
                return [], str(error)

        self.start_job(tr("Buscando certificados de Windows…"), identities, choose, preserve_selection=preserve_selection)

    def closeEvent(self, event):
        if self.job is not None:
            self.note(tr("Espera a que termine la operación antes de cerrar."))
            event.ignore()
            return
        self.view.finish_inline()
        self.stash_workspace()
        for index in range(self.work_list.count()):
            item = self.work_list.item(index)
            key = item.data(Qt.ItemDataRole.UserRole)
            if not (self.work_docs[key].dirty or self.work_docs[key].redactions):
                continue
            self.work_list.setCurrentItem(item)
            self.activate_work_item(item)
            if self.work_key != key or not self.can_leave():
                event.ignore()
                return
        if self.work_key is not None or self.can_leave():
            self.view.clear_text()
            self.view.zoom_render.stop()
            self.view.scroll_render.stop()
            self.thumbnail_timer.stop()
            if self.update_job is not None:
                self.update_job.quit()
                self.update_job.wait(500)
                self.update_job = None
            for key in list(self.document_views):
                self.close_secondary_views(key)
            self.temp.cleanup()
            event.accept()
        else:
            event.ignore()


def read_explorer_selection(token):
    if len(token) != 32 or UUID(hex=token).hex != token:
        raise ValueError(tr("Windows envió una selección de PDF no válida."))
    selection = Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "shell" / f"{token}.txt"
    try:
        paths = [Path(line) for line in selection.read_text(encoding="utf-8").splitlines()]
    finally:
        selection.unlink(missing_ok=True)
    if not paths or any(not path.is_absolute() or path.suffix.lower() != ".pdf" or not path.is_file()
                        for path in paths):
        raise ValueError(tr("Selecciona archivos PDF que estén disponibles en el Explorador."))
    return [str(path) for path in paths]


class PDFiuApplication(QApplication):
    """Handle macOS Finder 'Open With' / double-click FileOpen events safely."""

    def __init__(self, argv):
        super().__init__(argv)
        self._window = None
        self._pending_files = []

    def attach_window(self, window):
        self._window = window
        pending, self._pending_files = self._pending_files, []
        for path in pending:
            self._open_file(path)

    def _open_file(self, path):
        if self._window is None:
            self._pending_files.append(path)
            return
        if Path(path).suffix.lower() == ".pdf":
            self._window.open_path(path)
            self._window.raise_()
            self._window.activateWindow()

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                self._open_file(path)
                return True
        return super().event(event)


def main():
    setup_logging(APP_NAME, APP_VERSION)
    if WINDOWS_BUNDLE:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        create_mutex.restype = wintypes.HANDLE
        # Inno Setup shares this mutex with older installations.
        if not create_mutex(None, False, r"Local\PDFiu.Setup.AA1A6AE8"):
            raise ctypes.WinError(ctypes.get_last_error())

    application = PDFiuApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setWindowIcon(brand_icon())
    application.setStyle("Fusion")
    window = PDFiu(show_startup=True)
    apply_theme(application, window.preferences.value("apariencia/tema", "system"))
    window.show()
    window.startup.finish(window)
    window.startup = None
    application.attach_window(window)
    QTimer.singleShot(0, window, window.recover_interrupted_work)
    QTimer.singleShot(3000, window, window.schedule_update_check)
    if len(sys.argv) == 3 and sys.argv[1] == "--combine-selection" and sys.platform == "win32":
        def combine_selection():
            try:
                paths = read_explorer_selection(sys.argv[2])
            except (OSError, ValueError):
                window.error(tr("No se pudo leer la selección. Vuelve a seleccionar los PDF en el Explorador."))
                return
            window.merge_dialog(paths)

        QTimer.singleShot(0, combine_selection)
    elif len(sys.argv) >= 2:
        for arg in sys.argv[1:]:
            if Path(arg).suffix.lower() == ".pdf":
                window.open_path(arg)
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())
