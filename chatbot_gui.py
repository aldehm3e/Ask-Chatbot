import html
import os
import subprocess
import sys
import time

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ask_chatbot import APP_NAME, APP_VERSION, DEFAULT_MODEL
from ask_chatbot.icon import create_app_icon
from ask_chatbot.localization import LANG_AR, LANG_EN, tr
from ask_chatbot.ollama_client import (
    build_run_command,
    creation_flags,
    list_installed_models,
    ollama_available,
)
from ask_chatbot.pdf_processing import extract_pdf_files, format_extracted_text
from ask_chatbot.prompts import MAX_HISTORY_TURNS, build_prompt
from ask_chatbot.response_cleaning import clean_model_response, clean_partial_model_response
from ask_chatbot.retrieval import format_sources_for_display, representative_chunks, retrieve_relevant_chunks


def set_windows_app_id(app_id):
    if sys.platform != "win32":
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


class QuestionTextEdit(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.NoModifier:
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PdfExtractionWorker(QThread):
    progress = pyqtSignal(str)
    extraction_finished = pyqtSignal(object)

    def __init__(self, file_paths, use_ocr=False, ocr_language="eng", parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self.use_ocr = use_ocr
        self.ocr_language = ocr_language

    def run(self):
        def report(file_name, page_number, page_count):
            self.progress.emit(f"{file_name}: page {page_number} of {page_count}")

        result = extract_pdf_files(
            self.file_paths,
            use_ocr=self.use_ocr,
            ocr_language=self.ocr_language,
            progress_callback=report,
        )
        self.extraction_finished.emit(result)


class ModelListWorker(QThread):
    models_ready = pyqtSignal(object, object)

    def run(self):
        try:
            models, error = list_installed_models()
        except Exception as exc:
            models, error = [], str(exc)
        self.models_ready.emit(models, error)


class OllamaStreamWorker(QThread):
    partial_ready = pyqtSignal(str)
    response_ready = pyqtSignal(str, bool)

    def __init__(self, prompt, model_name, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.model_name = model_name
        self.process = None
        self._stopping = False

    def stop(self):
        self._stopping = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass

    def run(self):
        if not ollama_available():
            self.response_ready.emit(
                "Error: Ollama was not found. Please install Ollama and make sure it is in your PATH.",
                True,
            )
            return

        output_parts = []
        try:
            self.process = subprocess.Popen(
                build_run_command(self.model_name),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags(),
                bufsize=1,
            )

            if self.process.stdin:
                self.process.stdin.write(self.prompt)
                self.process.stdin.close()

            last_emit = 0.0
            while True:
                char = self.process.stdout.read(1) if self.process.stdout else ""
                if char:
                    output_parts.append(char)
                    now = time.monotonic()
                    if now - last_emit > 0.08:
                        partial = clean_partial_model_response("".join(output_parts))
                        if partial:
                            self.partial_ready.emit(partial)
                        last_emit = now
                    continue

                if self.process.poll() is not None:
                    break

            stderr = self.process.stderr.read() if self.process.stderr else ""
            return_code = self.process.wait()

            if self._stopping:
                self.response_ready.emit("Stopped.", True)
                return

            if return_code != 0:
                error = stderr.strip() or "Ollama exited without an error message."
                self.response_ready.emit(f"Error running Ollama: {error}", True)
                return

            response = clean_model_response("".join(output_parts))
            if not response:
                response = self.retry_without_reasoning()

            if response:
                self.response_ready.emit(response, response.startswith("Error:"))
            else:
                self.response_ready.emit("Error: The AI returned an empty final answer. Please try asking again.", True)
        except Exception as exc:
            if self._stopping:
                self.response_ready.emit("Stopped.", True)
            else:
                self.response_ready.emit(f"Error running Ollama: {exc}", True)

    def retry_without_reasoning(self):
        retry_prompt = (
            f"{self.prompt}\n\n"
            "The previous model output did not include a usable final answer. "
            "Reply now with a concise final answer only, without reasoning tags."
        )
        try:
            result = subprocess.run(
                build_run_command(self.model_name),
                input=retry_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags(),
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return "Error: Ollama took more than 5 minutes to respond."

        if result.returncode != 0:
            error = result.stderr.strip() or "Ollama exited without an error message."
            return f"Error running Ollama: {error}"

        return clean_model_response(result.stdout)


class TextDialog(QDialog):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 620)

        layout = QVBoxLayout(self)
        text_view = QTextEdit()
        text_view.setReadOnly(True)
        text_view.setPlainText(text)
        layout.addWidget(text_view)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)


class ChatbotApp(QMainWindow):
    def __init__(self, app_icon=None):
        super().__init__()
        self.app_icon = app_icon or create_app_icon()
        self.language = LANG_EN
        self.extraction_result = None
        self.document_chunks = []
        self.chat_history = []
        self.pending_question = ""
        self.pending_answer = ""
        self.pending_sources = []
        self.ollama_worker = None
        self.pdf_worker = None
        self.model_worker = None

        self.setWindowIcon(self.app_icon)
        self.setMinimumSize(980, 660)

        self.build_ui()
        self.create_menu_bar()
        self.apply_language()
        self.apply_styles()
        self.render_chat()
        self.refresh_models()

    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.upload_button = QPushButton()
        self.upload_button.clicked.connect(self.upload_pdf)
        top_bar.addWidget(self.upload_button)

        self.clear_docs_button = QPushButton()
        self.clear_docs_button.clicked.connect(self.clear_documents)
        top_bar.addWidget(self.clear_docs_button)

        self.ocr_checkbox = QCheckBox()
        top_bar.addWidget(self.ocr_checkbox)

        self.ocr_lang_label = QLabel()
        top_bar.addWidget(self.ocr_lang_label)

        self.ocr_lang_input = QLineEdit("eng")
        self.ocr_lang_input.setMaximumWidth(90)
        self.ocr_lang_input.setToolTip("Examples: eng, ara, eng+ara")
        top_bar.addWidget(self.ocr_lang_input)

        top_bar.addStretch(1)

        self.model_label = QLabel()
        top_bar.addWidget(self.model_label)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(210)
        self.model_combo.addItem(DEFAULT_MODEL)
        top_bar.addWidget(self.model_combo)

        self.refresh_models_button = QPushButton()
        self.refresh_models_button.clicked.connect(self.refresh_models)
        top_bar.addWidget(self.refresh_models_button)

        root.addLayout(top_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        self.documents_label = QLabel()
        left_layout.addWidget(self.documents_label)

        self.documents_list = QListWidget()
        self.documents_list.itemDoubleClicked.connect(self.open_document_item)
        left_layout.addWidget(self.documents_list, 2)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        left_layout.addWidget(self.summary_label)

        self.show_text_button = QPushButton()
        self.show_text_button.clicked.connect(self.show_extracted_text)
        left_layout.addWidget(self.show_text_button)

        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.update_source_results)
        left_layout.addWidget(self.search_box)

        self.sources_label = QLabel()
        left_layout.addWidget(self.sources_label)

        self.sources_list = QListWidget()
        self.sources_list.itemDoubleClicked.connect(self.open_source_item)
        left_layout.addWidget(self.sources_list, 3)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setOpenExternalLinks(False)
        right_layout.addWidget(self.chat_browser, 1)

        self.question_box = QuestionTextEdit()
        self.question_box.setMinimumHeight(92)
        self.question_box.setMaximumHeight(150)
        self.question_box.submitted.connect(self.ask_chatbot)
        right_layout.addWidget(self.question_box)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.ask_button = QPushButton()
        self.ask_button.clicked.connect(self.ask_chatbot)
        action_row.addWidget(self.ask_button)

        self.stop_button = QPushButton()
        self.stop_button.clicked.connect(self.stop_generation)
        self.stop_button.setEnabled(False)
        action_row.addWidget(self.stop_button)

        self.copy_last_button = QPushButton()
        self.copy_last_button.clicked.connect(self.copy_last_answer)
        action_row.addWidget(self.copy_last_button)

        self.export_chat_button = QPushButton()
        self.export_chat_button.clicked.connect(self.export_chat)
        action_row.addWidget(self.export_chat_button)

        self.clear_chat_button = QPushButton()
        self.clear_chat_button.clicked.connect(self.clear_chat)
        action_row.addWidget(self.clear_chat_button)

        action_row.addStretch(1)
        right_layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([290, 690])

        root.addWidget(splitter, 1)

        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self.status_label)

        self.setCentralWidget(central)

    def create_menu_bar(self):
        self.file_menu = self.menuBar().addMenu("File")
        self.export_action = QAction("", self)
        self.export_action.triggered.connect(self.export_chat)
        self.file_menu.addAction(self.export_action)

        self.clear_chat_action = QAction("", self)
        self.clear_chat_action.triggered.connect(self.clear_chat)
        self.file_menu.addAction(self.clear_chat_action)

        language_menu = self.menuBar().addMenu("")
        self.language_menu = language_menu
        self.english_action = QAction("", self)
        self.english_action.setCheckable(True)
        self.english_action.triggered.connect(lambda: self.set_language(LANG_EN))
        language_menu.addAction(self.english_action)

        self.arabic_action = QAction("", self)
        self.arabic_action.setCheckable(True)
        self.arabic_action.triggered.connect(lambda: self.set_language(LANG_AR))
        language_menu.addAction(self.arabic_action)

        help_menu = self.menuBar().addMenu("Help")
        self.help_menu = help_menu
        self.about_action = QAction("", self)
        self.about_action.setShortcut("F1")
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def apply_language(self):
        self.setWindowTitle(tr(self.language, "window_title"))
        self.upload_button.setText(tr(self.language, "upload"))
        self.clear_docs_button.setText(tr(self.language, "clear_docs"))
        self.show_text_button.setText(tr(self.language, "show_text"))
        self.ask_button.setText(tr(self.language, "ask"))
        self.stop_button.setText(tr(self.language, "stop"))
        self.copy_last_button.setText(tr(self.language, "copy_last"))
        self.export_chat_button.setText(tr(self.language, "export_chat"))
        self.clear_chat_button.setText(tr(self.language, "clear_chat"))
        self.ocr_checkbox.setText(tr(self.language, "ocr"))
        self.ocr_lang_label.setText(tr(self.language, "ocr_lang"))
        self.model_label.setText(tr(self.language, "model"))
        self.refresh_models_button.setText(tr(self.language, "refresh_models"))
        self.documents_label.setText(tr(self.language, "documents"))
        self.sources_label.setText(tr(self.language, "sources"))
        self.search_box.setPlaceholderText(tr(self.language, "search"))
        self.question_box.setPlaceholderText(tr(self.language, "question_placeholder"))
        self.export_action.setText(tr(self.language, "export_chat"))
        self.clear_chat_action.setText(tr(self.language, "clear_chat"))
        self.file_menu.setTitle("File" if self.language == LANG_EN else "ملف")
        self.language_menu.setTitle(tr(self.language, "language"))
        self.english_action.setText(tr(self.language, "english"))
        self.arabic_action.setText(tr(self.language, "arabic"))
        self.about_action.setText(tr(self.language, "about"))
        self.help_menu.setTitle("Help" if self.language == LANG_EN else "مساعدة")
        self.english_action.setChecked(self.language == LANG_EN)
        self.arabic_action.setChecked(self.language == LANG_AR)

        direction = Qt.RightToLeft if self.language == LANG_AR else Qt.LeftToRight
        self.setLayoutDirection(direction)
        self.chat_browser.setLayoutDirection(direction)
        self.question_box.setLayoutDirection(direction)
        self.render_chat()
        self.update_summary_label()
        if not self.status_label.text():
            self.status_label.setText(tr(self.language, "ready"))

    def apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f6f7f9;
                color: #20242a;
                font-size: 10pt;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #b8c0cc;
                border-radius: 5px;
                padding: 7px 10px;
            }
            QPushButton:hover {
                background: #eef4ff;
                border-color: #7ea2d9;
            }
            QPushButton:disabled {
                color: #8a919c;
                background: #eceff3;
            }
            QLineEdit, QTextEdit, QTextBrowser, QListWidget, QComboBox {
                background: #ffffff;
                border: 1px solid #c8ced8;
                border-radius: 5px;
                padding: 5px;
            }
            QLabel {
                color: #20242a;
            }
            QProgressBar {
                background: #ffffff;
                border: 1px solid #c8ced8;
                border-radius: 5px;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: #2457A6;
            }
            """
        )

    def set_language(self, language):
        self.language = language
        self.apply_language()
        self.status_label.setText(tr(self.language, "ready"))

    def refresh_models(self):
        if self.model_worker and self.model_worker.isRunning():
            return
        self.refresh_models_button.setEnabled(False)
        self.model_worker = ModelListWorker(self)
        self.model_worker.models_ready.connect(self.finish_refresh_models)
        self.model_worker.start()

    def finish_refresh_models(self, models, error):
        current = self.model_combo.currentText() or DEFAULT_MODEL
        self.model_combo.clear()
        for model in models or [DEFAULT_MODEL]:
            self.model_combo.addItem(model)

        index = self.model_combo.findText(current)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

        self.refresh_models_button.setEnabled(True)
        if error:
            self.status_label.setText(error)
        else:
            self.status_label.setText(f"{len(models)} Ollama model(s) available.")
        self.model_worker = None

    def upload_pdf(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select PDF Files", "", "PDF Files (*.pdf)")
        if not file_paths:
            return

        self.set_busy(True, tr(self.language, "extracting"))
        self.chat_history = []
        self.pending_question = ""
        self.pending_answer = ""
        self.pending_sources = []
        self.render_chat()

        ocr_language = self.ocr_lang_input.text().strip() or "eng"
        self.pdf_worker = PdfExtractionWorker(file_paths, self.ocr_checkbox.isChecked(), ocr_language, self)
        self.pdf_worker.progress.connect(self.on_pdf_progress)
        self.pdf_worker.extraction_finished.connect(self.on_pdf_finished)
        self.pdf_worker.start()

    def on_pdf_progress(self, message):
        self.status_label.setText(message)

    def on_pdf_finished(self, result):
        self.extraction_result = result
        self.document_chunks = result.chunks
        self.pdf_worker = None
        self.set_busy(False, tr(self.language, "ready"))
        self.rebuild_document_list()
        self.update_summary_label()
        self.update_source_results(self.search_box.text())

        if result.total_chars:
            status = (
                f"Loaded {result.file_count} file(s), {result.total_pages} page(s), "
                f"{result.total_chars} extracted character(s), {len(result.chunks)} chunk(s)."
            )
        else:
            status = "No selectable text was found. Try OCR for scanned or image-only PDFs."

        if result.errors:
            status += " Some files/pages reported problems."
        self.status_label.setText(status)

    def set_busy(self, busy, message):
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        self.upload_button.setEnabled(not busy)
        self.clear_docs_button.setEnabled(not busy)
        self.ask_button.setEnabled(not busy and self.ollama_worker is None)
        self.question_box.setEnabled(not busy and self.ollama_worker is None)
        self.status_label.setText(message)

    def rebuild_document_list(self):
        self.documents_list.clear()
        if not self.extraction_result:
            return

        for summary in self.extraction_result.files:
            label = (
                f"{summary.file_name}\n"
                f"{summary.page_count} page(s) | {summary.extracted_chars} chars | {summary.chunk_count} chunks"
            )
            if summary.ocr_chars:
                label += f" | OCR {summary.ocr_chars} chars"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, summary)
            self.documents_list.addItem(item)

    def update_summary_label(self):
        if not self.extraction_result:
            self.summary_label.setText(tr(self.language, "empty_chat"))
            return

        result = self.extraction_result
        summary = (
            f"Files: {result.file_count}\n"
            f"Pages: {result.total_pages}\n"
            f"Characters: {result.total_chars}\n"
            f"Chunks: {len(result.chunks)}"
        )
        if result.ocr_requested:
            availability = "available" if result.ocr_available else "not found"
            summary += f"\nOCR: {availability}"
        if result.errors:
            summary += f"\nProblems: {len(result.errors)}"
        self.summary_label.setText(summary)

    def update_source_results(self, query):
        self.sources_list.clear()
        if not self.document_chunks:
            return

        query = query.strip()
        if query:
            results = retrieve_relevant_chunks(query, self.document_chunks, limit=12)
            chunks = [item.chunk for item in results]
        else:
            chunks = self.document_chunks[:30]

        for chunk in chunks:
            preview = " ".join(chunk.text.split())[:170]
            label = f"{chunk.file_name}, page {chunk.page_number}, chunk {chunk.chunk_index}\n{preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, chunk)
            self.sources_list.addItem(item)

    def open_document_item(self, item):
        summary = item.data(Qt.UserRole)
        if not summary:
            return

        errors = "\n".join(summary.errors) if summary.errors else "No problems reported."
        text = (
            f"File: {summary.file_name}\n"
            f"Path: {summary.path}\n"
            f"Pages: {summary.page_count}\n"
            f"Extracted characters: {summary.extracted_chars}\n"
            f"OCR characters: {summary.ocr_chars}\n"
            f"Chunks: {summary.chunk_count}\n\n"
            f"Problems:\n{errors}"
        )
        TextDialog(summary.file_name, text, self).exec_()

    def open_source_item(self, item):
        chunk = item.data(Qt.UserRole)
        if not chunk:
            return
        title = f"{chunk.file_name} - page {chunk.page_number}, chunk {chunk.chunk_index}"
        TextDialog(title, chunk.text, self).exec_()

    def clear_documents(self):
        self.extraction_result = None
        self.document_chunks = []
        self.documents_list.clear()
        self.sources_list.clear()
        self.search_box.clear()
        self.update_summary_label()
        self.status_label.setText(tr(self.language, "ready"))

    def show_extracted_text(self):
        if not self.document_chunks:
            QMessageBox.information(self, APP_NAME, tr(self.language, "no_text"))
            return
        TextDialog("Extracted Text", format_extracted_text(self.document_chunks), self).exec_()

    def ask_chatbot(self):
        if self.ollama_worker is not None:
            self.status_label.setText("Still thinking. Stop the current answer or wait for it to finish.")
            return

        user_question = self.question_box.toPlainText().strip()
        if not user_question:
            self.status_label.setText("Please enter a question.")
            return

        model_name = self.model_combo.currentText().strip() or DEFAULT_MODEL
        retrieved = retrieve_relevant_chunks(user_question, self.document_chunks, limit=6)
        if not retrieved and self.document_chunks:
            retrieved = representative_chunks(self.document_chunks, limit=6)
        self.pending_sources = format_sources_for_display(retrieved)
        self.pending_question = user_question
        self.pending_answer = tr(self.language, "thinking")

        prompt = build_prompt(
            user_question,
            retrieved_chunks=retrieved,
            chat_history=self.chat_history,
            has_documents=bool(self.document_chunks),
        )

        self.question_box.clear()
        self.render_chat()
        self.start_generation(prompt, model_name)

    def start_generation(self, prompt, model_name):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.ask_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.question_box.setEnabled(False)
        self.status_label.setText(tr(self.language, "thinking"))

        self.ollama_worker = OllamaStreamWorker(prompt, model_name, self)
        self.ollama_worker.partial_ready.connect(self.on_partial_response)
        self.ollama_worker.response_ready.connect(self.on_response_finished)
        self.ollama_worker.start()

    def stop_generation(self):
        if self.ollama_worker is not None:
            self.ollama_worker.stop()
            self.status_label.setText("Stopping...")

    def on_partial_response(self, partial):
        self.pending_answer = partial
        self.render_chat(scroll_to_bottom=True)

    def on_response_finished(self, response, is_error):
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.ask_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.question_box.setEnabled(True)

        if self.pending_question and not is_error:
            self.chat_history.append({"role": "user", "content": self.pending_question, "sources": self.pending_sources})
            self.chat_history.append({"role": "assistant", "content": response, "sources": self.pending_sources})
            if len(self.chat_history) > MAX_HISTORY_TURNS * 2:
                self.chat_history = self.chat_history[-MAX_HISTORY_TURNS * 2 :]
            self.pending_question = ""
            self.pending_answer = ""
            self.pending_sources = []
            self.status_label.setText(tr(self.language, "ready"))
        else:
            self.pending_answer = response
            self.status_label.setText(response)

        self.ollama_worker = None
        self.render_chat(scroll_to_bottom=True)
        self.question_box.setFocus()

    def render_chat(self, scroll_to_bottom=False):
        direction = "rtl" if self.language == LANG_AR else "ltr"
        align = "right" if self.language == LANG_AR else "left"
        parts = [
            "<html><head><style>",
            "body { font-family: Segoe UI, Arial, sans-serif; color: #20242a; background: #ffffff; }",
            ".msg { margin: 0 0 14px 0; padding: 10px 12px; border-left: 3px solid #c8ced8; }",
            ".user { background: #f4f8ff; border-color: #2457A6; }",
            ".assistant { background: #f7fbf8; border-color: #31A36F; }",
            ".role { font-weight: 600; margin-bottom: 6px; }",
            ".content { white-space: pre-wrap; line-height: 1.45; }",
            ".sources { margin-top: 8px; color: #5c6675; font-size: 9pt; }",
            ".empty { color: #687282; padding: 16px 4px; }",
            "</style></head>",
            f"<body dir='{direction}' style='text-align:{align};'>",
        ]

        if not self.chat_history and not self.pending_question:
            parts.append(f"<div class='empty'>{html.escape(tr(self.language, 'empty_chat'))}</div>")

        for message in self.chat_history:
            parts.append(self.render_message(message))

        if self.pending_question:
            parts.append(
                self.render_message(
                    {"role": "user", "content": self.pending_question, "sources": self.pending_sources}
                )
            )
            parts.append(
                self.render_message(
                    {"role": "assistant", "content": self.pending_answer or tr(self.language, "thinking"), "sources": self.pending_sources}
                )
            )

        parts.append("</body></html>")
        self.chat_browser.setHtml("".join(parts))
        if scroll_to_bottom:
            QTimer.singleShot(0, self.scroll_chat_to_bottom)
            QTimer.singleShot(50, self.scroll_chat_to_bottom)

    def render_message(self, message):
        role = message.get("role", "")
        css_class = "user" if role == "user" else "assistant"
        label = "You" if role == "user" else "Chatbot"
        if self.language == LANG_AR:
            label = "أنت" if role == "user" else "المساعد"

        content = html.escape(message.get("content", ""))
        sources = message.get("sources") or []
        sources_html = ""
        if role == "assistant" and sources:
            source_text = html.escape(" | ".join(sources))
            sources_html = f"<div class='sources'>Sources: {source_text}</div>"

        return (
            f"<div class='msg {css_class}'>"
            f"<div class='role'>{html.escape(label)}</div>"
            f"<div class='content'>{content}</div>"
            f"{sources_html}"
            f"</div>"
        )

    def scroll_chat_to_bottom(self):
        scrollbar = self.chat_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def copy_last_answer(self):
        for message in reversed(self.chat_history):
            if message.get("role") == "assistant":
                QApplication.clipboard().setText(message.get("content", ""))
                self.status_label.setText("Last answer copied.")
                return
        self.status_label.setText("No answer to copy yet.")

    def export_chat(self):
        if not self.chat_history:
            self.status_label.setText("No chat to export yet.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Export Chat", "ask_chatbot_chat.txt", "Text Files (*.txt)")
        if not file_path:
            return

        lines = []
        for message in self.chat_history:
            label = "You" if message.get("role") == "user" else "Chatbot"
            lines.append(f"{label}:\n{message.get('content', '')}")
            if message.get("role") == "assistant" and message.get("sources"):
                lines.append("Sources: " + " | ".join(message["sources"]))
            lines.append("")

        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("\n".join(lines).strip() + "\n")
            self.status_label.setText(f"Chat exported to {file_path}")
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not export chat: {exc}")

    def clear_chat(self):
        self.chat_history = []
        self.pending_question = ""
        self.pending_answer = ""
        self.pending_sources = []
        self.render_chat()
        self.status_label.setText(tr(self.language, "ready"))

    def show_about_dialog(self):
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle(tr(self.language, "about"))
        about_dialog.setWindowIcon(self.app_icon)
        about_dialog.setIconPixmap(self.app_icon.pixmap(80, 80))
        about_dialog.setTextFormat(Qt.PlainText)
        about_dialog.setText(f"{APP_NAME} V{APP_VERSION}")
        about_dialog.setInformativeText(
            "by Eng. Abdulrahman Alsaedi\n"
            "Islamic University of Medina\n\n"
            "A local PDF question-answering chatbot powered by Ollama."
        )
        about_dialog.setStandardButtons(QMessageBox.Ok)
        about_dialog.exec_()

    def closeEvent(self, event):
        if self.ollama_worker is not None:
            self.ollama_worker.stop()
            self.ollama_worker.wait(2000)
        if self.model_worker is not None and self.model_worker.isRunning():
            self.model_worker.wait(9000)
        if self.pdf_worker is not None and self.pdf_worker.isRunning():
            self.pdf_worker.wait(2000)
        super().closeEvent(event)


if __name__ == "__main__":
    set_windows_app_id("chatbot.app.v1.6")
    app = QApplication(sys.argv)
    app_icon = create_app_icon()
    app.setWindowIcon(app_icon)
    window = ChatbotApp(app_icon)
    window.show()
    sys.exit(app.exec_())
