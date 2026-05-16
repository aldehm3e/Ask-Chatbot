
import sys
from PyQt5 import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QFileDialog
import fitz  # PyMuPDF for handling PDFs

class ChatbotApp(QWidget):
    def __init__(self):
        super().__init__()

        # Set up the window
        self.setWindowTitle("PDF Chatbot")
        self.setGeometry(100, 100, 600, 400)

        # Set up layout and widgets
        self.layout = QVBoxLayout()

        self.label = QLabel("Upload a PDF file(s) to analyze:", self)
        self.layout.addWidget(self.label)

        self.upload_button = QPushButton("Upload PDF", self)
        self.upload_button.clicked.connect(self.upload_pdf)
        self.layout.addWidget(self.upload_button)

        self.result_label = QLabel("Chatbot results will appear here...", self)
        self.layout.addWidget(self.result_label)

        self.setLayout(self.layout)

    def upload_pdf(self):
        # Open file dialog to select a PDF
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("PDF Files (*.pdf)")
        file_dialog.setViewMode(QFileDialog.List)

        if file_dialog.exec_():
            file_paths = file_dialog.selectedFiles()
            self.process_pdfs(file_paths)

    def process_pdfs(self, file_paths):
        """Process uploaded PDFs and display extracted text."""
        text = extract_text_from_pdfs(file_paths)  # Extract text
        preview_text = text[:500] + "..." if len(text) > 500 else text  # Show first 500 characters
        self.result_label.setText(f"Extracted Text:\n{preview_text}")  # Display extracted text

def extract_text_from_pdfs(pdf_paths):
    """Extract text from multiple PDF files."""
    text = ""
    for pdf_path in pdf_paths:
        doc = fitz.open(pdf_path)  # Open the PDF file
        for page in doc:  # Loop through each page
            text += page.get_text() + "\n"  # Extract text and add a newline
    return text

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatbotApp()
    window.show()
    sys.exit(app.exec_())
