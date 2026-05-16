import os
import sys
import fitz  # PyMuPDF for PDF processing
import subprocess  # For running Ollama locally
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QFileDialog, QLabel, QProgressBar,
    QMenuBar, QAction, QMessageBox, QScrollArea
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

# Windows-specific imports for taskbar icon
if sys.platform == "win32":
    from PyQt5.QtWinExtras import QtWin

# Function to get the correct path for PyInstaller
def resource_path(relative_path):
    """ Get the absolute path to a resource (useful for PyInstaller). """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class ChatbotApp(QWidget):
    def __init__(self):
        super().__init__()

        # Set window properties
        self.setWindowTitle("Ask Chatbot V1.5")
        self.setGeometry(100, 100, 600, 500)

        # Set application and taskbar icon
        app_icon = QIcon(resource_path("AIS1.ico"))
        self.setWindowIcon(app_icon)

        # Explicitly set taskbar icon for Windows
        if sys.platform == "win32":
            app_id = "chatbot.app.v1"  # Unique app ID
            QtWin.setCurrentProcessExplicitAppUserModelID(app_id)

        # Create layout
        self.layout = QVBoxLayout()
        self.create_menu_bar()

        # Create a button to upload PDFs
        self.upload_button = QPushButton("📂 Upload PDF(s)")
        self.upload_button.setStyleSheet("background-color: white; color: black;")
        self.upload_button.clicked.connect(self.upload_pdf)

        # Create a button to show the extracted PDF text
        self.show_text_button = QPushButton("📄 Show Extracted Text")
        self.show_text_button.setStyleSheet("background-color: white; color: black;")
        self.show_text_button.clicked.connect(self.show_extracted_text)

        # Create a text area for user input
        self.question_box = QTextEdit()
        self.question_box.setPlaceholderText("✍ Type your question here...")

        # Create a button to ask the chatbot
        self.ask_button = QPushButton("🤖 Ask Chatbot")
        self.ask_button.setStyleSheet("background-color: white; color: black;")
        self.ask_button.clicked.connect(self.ask_chatbot)

        # Create a progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        # Create a label to display responses
        self.response_label = QLabel("💬 Chatbot Response will appear here.")
        self.response_label.setWordWrap(True)
        self.response_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

        # Wrap the response label in a scroll area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.response_label)
        self.scroll_area.setWidgetResizable(True)

        # Add widgets to layout
        self.layout.addWidget(self.upload_button)
        self.layout.addWidget(self.show_text_button)
        self.layout.addWidget(self.question_box)
        self.layout.addWidget(self.ask_button)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.scroll_area)

        # Set layout
        self.setLayout(self.layout)

        # Store extracted PDF text
        self.pdf_text = ""

    def create_menu_bar(self):
        """Creates the menu bar with an About button."""
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

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        menu_bar.addAction(about_action)
        self.layout.setMenuBar(menu_bar)

    def show_about_dialog(self):
        """Displays the About dialog."""
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle("About")
        about_dialog.setTextFormat(Qt.RichText)
        about_dialog.setText(
            "<center>Ask Chatbot🤖 V1.5<br>"
            "by Eng. Abdulrahman Alsaedi<br>"
            "Islamic University of Medina</center>"
        )
        about_dialog.setStandardButtons(QMessageBox.Ok)
        about_dialog.exec_()

    def upload_pdf(self):
        """Opens a file dialog for selecting PDFs and extracts text."""
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(self, "Select PDF Files", "", "PDF Files (*.pdf)")

        if file_paths:
            self.pdf_text = ""
            for pdf_file in file_paths:
                text = self.extract_text_from_pdf(pdf_file)
                self.pdf_text += text + "\n\n"
            self.response_label.setText("✅ PDF text extracted successfully! You can now ask questions.")

    def extract_text_from_pdf(self, pdf_path):
        """Extracts text from a given PDF file."""
        try:
            doc = fitz.open(pdf_path)
            text = "".join([page.get_text() + "\n" for page in doc])
            return text
        except Exception as e:
            return f"⚠️ Error reading {pdf_path}: {e}"

    def show_extracted_text(self):
        """Displays the extracted text."""
        if not self.pdf_text:
            self.response_label.setText("⚠️ No text extracted from the PDF yet.")
            return
        self.response_label.setText(self.pdf_text)

    def ask_chatbot(self):
        """Runs DeepSeek-R1:1.5B locally using Ollama."""
        user_question = self.question_box.toPlainText()
        if not self.pdf_text:
            self.response_label.setText("⚠️ Please upload a PDF first.")
            return
        if not user_question:
            self.response_label.setText("⚠️ Please enter a question.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(50)

        full_prompt = f"Context:\n{self.pdf_text}\n\nQuestion: {user_question}\nAnswer:"
        response = self.run_ollama(full_prompt)

        self.progress_bar.setVisible(False)
        self.response_label.setText(f"💡 {response}")

    def run_ollama(self, prompt):
        """Runs DeepSeek-R1:1.5B locally using Ollama CLI."""
        try:
            result = subprocess.run(
                ["ollama", "run", "deepseek-r1:1.5b", prompt],
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW  # Hide the CMD terminal
            )
            return result.stdout if result.stdout else "⚠️ Error: No response from AI."
        except Exception as e:
            return f"⚠️ Error running Ollama: {e}"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatbotApp()
    window.show()
    sys.exit(app.exec_())
