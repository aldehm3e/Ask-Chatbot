import os
import re
import shutil
import subprocess
import sys

import fitz  # PyMuPDF for PDF processing
from PyQt5.QtCore import QPoint, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QLabel,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


ANSI_ESCAPE_RE = re.compile(r"[\x1b\x9b\u2039]\[[0-?]*[ -/]*[@-~]")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
MAX_HISTORY_TURNS = 8


def set_windows_app_id(app_id):
    if sys.platform != "win32":
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def create_app_icon():
    """Creates a local PDF/chat icon without requiring an image file."""
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    background = QPainterPath()
    background.addRoundedRect(8, 8, 112, 112, 24, 24)
    painter.fillPath(background, QColor("#2457A6"))

    document = QPainterPath()
    document.moveTo(38, 24)
    document.lineTo(78, 24)
    document.lineTo(96, 42)
    document.lineTo(96, 94)
    document.quadTo(96, 102, 88, 102)
    document.lineTo(38, 102)
    document.quadTo(30, 102, 30, 94)
    document.lineTo(30, 32)
    document.quadTo(30, 24, 38, 24)
    painter.fillPath(document, QColor("#FFFFFF"))

    fold = QPainterPath()
    fold.moveTo(78, 24)
    fold.lineTo(96, 42)
    fold.lineTo(82, 42)
    fold.quadTo(78, 42, 78, 38)
    fold.closeSubpath()
    painter.fillPath(fold, QColor("#CFE0FF"))

    painter.setPen(QPen(QColor("#2457A6"), 5, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(44, 54, 78, 54)
    painter.drawLine(44, 68, 82, 68)
    painter.drawLine(44, 82, 66, 82)

    bubble = QPainterPath()
    bubble.addRoundedRect(58, 70, 48, 34, 12, 12)
    bubble.moveTo(72, 100)
    bubble.lineTo(62, 112)
    bubble.lineTo(84, 102)
    painter.fillPath(bubble, QColor("#31C48D"))

    painter.setPen(QPen(QColor("#FFFFFF"), 5, Qt.SolidLine, Qt.RoundCap))
    painter.drawPoint(QPoint(72, 87))
    painter.drawPoint(QPoint(84, 87))
    painter.drawPoint(QPoint(96, 87))

    painter.end()
    return QIcon(pixmap)


def clean_model_response(text):
    """Removes model reasoning tags and terminal control characters."""
    text = ANSI_ESCAPE_RE.sub("", text)
    text = THINK_BLOCK_RE.sub("", text)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    text = CONTROL_CHAR_RE.sub("", text)
    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if lines and line:
            previous_word = re.search(r"(\w{1,16})$", lines[-1], flags=re.UNICODE)
            first_word = re.match(r"(\w{1,32})", line, flags=re.UNICODE)
            if (
                previous_word
                and first_word
                and first_word.group(1).casefold().startswith(previous_word.group(1).casefold())
                and first_word.group(1).casefold() != previous_word.group(1).casefold()
            ):
                lines[-1] = lines[-1][: -len(previous_word.group(1))].rstrip()
        lines.append(line)
    return "\n".join(lines).strip()


class QuestionTextEdit(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.NoModifier:
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class OllamaWorker(QThread):
    """Runs the local Ollama command without freezing the PyQt window."""

    response_ready = pyqtSignal(str)

    def __init__(self, prompt, parent=None):
        super().__init__(parent)
        self.prompt = prompt

    def run(self):
        self.response_ready.emit(self.run_ollama(self.prompt))

    @staticmethod
    def call_ollama(prompt):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        return subprocess.run(
            ["ollama", "run", "deepseek-r1:1.5b"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=300,
        )

    def run_ollama(self, prompt):
        if not shutil.which("ollama"):
            return "Error: Ollama was not found. Please install Ollama and make sure it is in your PATH."

        try:
            result = self.call_ollama(prompt)

            if result.returncode != 0:
                error = result.stderr.strip() or "Ollama exited without an error message."
                return f"Error running Ollama: {error}"

            response = clean_model_response(result.stdout)
            if response:
                return response

            retry_prompt = (
                f"{prompt}\n\n"
                "The previous model output did not include a usable final answer. "
                "Reply now with a concise final answer only, without reasoning tags."
            )
            retry_result = self.call_ollama(retry_prompt)

            if retry_result.returncode != 0:
                error = retry_result.stderr.strip() or "Ollama exited without an error message."
                return f"Error running Ollama: {error}"

            retry_response = clean_model_response(retry_result.stdout)
            if retry_response:
                return retry_response

            return "Error: The AI returned an empty final answer. Please try asking again."
        except subprocess.TimeoutExpired:
            return "Error: Ollama took more than 5 minutes to respond."
        except Exception as e:
            return f"Error running Ollama: {e}"


class ChatbotApp(QWidget):
    def __init__(self, app_icon=None):
        super().__init__()

        self.setWindowTitle("Ask Chatbot V1.5")
        self.setGeometry(100, 100, 600, 500)
        self.app_icon = app_icon or create_app_icon()
        self.setWindowIcon(self.app_icon)

        self.layout = QVBoxLayout()
        self.create_menu_bar()

        self.upload_button = QPushButton("Upload PDF(s)")
        self.upload_button.setStyleSheet("background-color: white; color: black;")
        self.upload_button.clicked.connect(self.upload_pdf)

        self.show_text_button = QPushButton("Show Extracted Text")
        self.show_text_button.setStyleSheet("background-color: white; color: black;")
        self.show_text_button.clicked.connect(self.show_extracted_text)

        self.question_box = QuestionTextEdit()
        self.question_box.setPlaceholderText("Type your question here. Press Enter to ask, Shift+Enter for a new line.")
        self.question_box.submitted.connect(self.ask_chatbot)

        self.ask_button = QPushButton("Ask Chatbot")
        self.ask_button.setStyleSheet("background-color: white; color: black;")
        self.ask_button.clicked.connect(self.ask_chatbot)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        self.response_label = QLabel("Chatbot response will appear here.")
        self.response_label.setTextFormat(Qt.PlainText)
        self.response_label.setWordWrap(True)
        self.response_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.response_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.response_label)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.upload_button)
        self.layout.addWidget(self.show_text_button)
        self.layout.addWidget(self.question_box)
        self.layout.addWidget(self.ask_button)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.scroll_area)

        self.setLayout(self.layout)

        self.pdf_text = ""
        self.pdf_files = []
        self.chat_history = []
        self.pending_question = ""
        self.ollama_worker = None

    def create_menu_bar(self):
        menu_bar = QMenuBar(self)
        menu_bar.setStyleSheet(
            """
            QMenuBar {
                background-color: white;
                color: black;
            }
            QMenuBar::item:selected {
                background: #e0e0e0;
            }
            QMenu {
                background-color: white;
                color: black;
            }
            QMenu::item:selected {
                background-color: #e0e0e0;
            }
            """
        )

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        self.layout.setMenuBar(menu_bar)

    def show_about_dialog(self):
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle("About")
        about_dialog.setWindowIcon(self.app_icon)
        about_dialog.setIconPixmap(self.app_icon.pixmap(64, 64))
        about_dialog.setTextFormat(Qt.PlainText)
        about_dialog.setText("Ask Chatbot V1.5")
        about_dialog.setInformativeText(
            "by Eng. Abdulrahman Alsaedi\n"
            "Islamic University of Medina\n\n"
            "A local PDF question-answering chatbot powered by Ollama."
        )
        about_dialog.setStandardButtons(QMessageBox.Ok)
        about_dialog.exec_()

    def upload_pdf(self):
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(self, "Select PDF Files", "", "PDF Files (*.pdf)")

        if file_paths:
            self.pdf_text = ""
            self.pdf_files = []
            self.chat_history = []
            self.pending_question = ""
            total_pages = 0
            errors = []
            for pdf_file in file_paths:
                text, page_count, error = self.extract_text_from_pdf(pdf_file)
                total_pages += page_count
                self.pdf_files.append(os.path.basename(pdf_file))
                if error:
                    errors.append(error)
                if text:
                    self.pdf_text += f"File: {os.path.basename(pdf_file)}\n{text}\n\n"

            extracted_chars = len(self.pdf_text.strip())
            if extracted_chars:
                message = (
                    f"PDF text extracted successfully.\n"
                    f"Files: {len(file_paths)} | Pages: {total_pages} | Characters: {extracted_chars}\n"
                    "You can now ask questions. Chat history has been reset for this PDF set."
                )
            else:
                message = (
                    f"No selectable text was found.\n"
                    f"Files: {len(file_paths)} | Pages: {total_pages}\n"
                    "If this PDF is scanned or image-only, it needs OCR before the chatbot can read it."
                )

            if errors:
                message += "\n\nProblems:\n" + "\n".join(errors)

            self.response_label.setText(message)
            self.scroll_response_to_bottom()

    @staticmethod
    def extract_text_from_pdf(pdf_path):
        doc = None
        try:
            doc = fitz.open(pdf_path)
            page_count = doc.page_count
            text = "\n".join(page.get_text("text").strip() for page in doc).strip()
            return text, page_count, None
        except Exception as e:
            return "", 0, f"Error reading {os.path.basename(pdf_path)}: {e}"
        finally:
            if doc is not None:
                doc.close()

    def show_extracted_text(self):
        if not self.pdf_text:
            self.response_label.setText("No text extracted from a PDF yet.")
            self.scroll_response_to_bottom()
            return
        self.response_label.setText(self.pdf_text)
        self.scroll_response_to_bottom()

    @staticmethod
    def is_error_response(response):
        return response.startswith("Error:")

    def scroll_response_to_bottom(self):
        QTimer.singleShot(0, self._scroll_response_to_bottom)
        QTimer.singleShot(50, self._scroll_response_to_bottom)

    def _scroll_response_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def format_chat_history(self, pending_question=None, pending_response=None):
        parts = []
        for role, message in self.chat_history:
            label = "You" if role == "user" else "Chatbot"
            parts.append(f"{label}:\n{message}")

        if pending_question:
            parts.append(f"You:\n{pending_question}")
        if pending_response:
            parts.append(f"Chatbot:\n{pending_response}")

        return "\n\n".join(parts) or "Chatbot response will appear here."

    def format_prompt_history(self):
        recent_history = self.chat_history[-MAX_HISTORY_TURNS * 2 :]
        lines = []
        for role, message in recent_history:
            label = "User" if role == "user" else "Assistant"
            lines.append(f"{label}: {message}")
        return "\n".join(lines)

    def build_prompt(self, user_question):
        instructions = (
            "Answer the user's current question naturally and directly.\n"
            "Use the recent conversation when it helps answer follow-up questions.\n"
            "If PDF context is provided, use it when it is relevant.\n"
            "Give the final answer only. Do not include <think> tags or hidden reasoning."
        )
        history = self.format_prompt_history()

        prompt_parts = [instructions]
        if self.pdf_text:
            prompt_parts.append(f"PDF context:\n{self.pdf_text.strip()}")
        if history:
            prompt_parts.append(f"Recent conversation:\n{history}")
        prompt_parts.append(f"Current question: {user_question}\nAnswer:")

        return "\n\n".join(prompt_parts)

    def ask_chatbot(self):
        if self.ollama_worker is not None:
            self.response_label.setText(
                self.format_chat_history(self.pending_question, "Still thinking. Please wait for this answer to finish.")
            )
            self.scroll_response_to_bottom()
            return

        user_question = self.question_box.toPlainText().strip()
        if not user_question:
            self.response_label.setText("Please enter a question.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.ask_button.setEnabled(False)
        self.question_box.setEnabled(False)
        self.pending_question = user_question
        self.response_label.setText(self.format_chat_history(user_question, "Thinking..."))
        self.scroll_response_to_bottom()

        full_prompt = self.build_prompt(user_question)
        self.question_box.clear()
        self.ollama_worker = OllamaWorker(full_prompt, self)
        self.ollama_worker.response_ready.connect(self.display_chatbot_response)
        self.ollama_worker.start()

    def display_chatbot_response(self, response):
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.ask_button.setEnabled(True)
        self.question_box.setEnabled(True)

        if self.pending_question and not self.is_error_response(response):
            self.chat_history.append(("user", self.pending_question))
            self.chat_history.append(("assistant", response))
            if len(self.chat_history) > MAX_HISTORY_TURNS * 2:
                self.chat_history = self.chat_history[-MAX_HISTORY_TURNS * 2 :]

            self.response_label.setText(self.format_chat_history())
        else:
            self.response_label.setText(self.format_chat_history(self.pending_question, response))

        self.scroll_response_to_bottom()
        self.pending_question = ""
        self.ollama_worker = None
        self.question_box.setFocus()


if __name__ == "__main__":
    set_windows_app_id("chatbot.app.v1")
    app = QApplication(sys.argv)
    app_icon = create_app_icon()
    app.setWindowIcon(app_icon)
    window = ChatbotApp(app_icon)
    window.show()
    sys.exit(app.exec_())
