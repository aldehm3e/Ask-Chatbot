# Ask Chatbot

Ask Chatbot is a local desktop app for asking questions about PDF files. It uses PyQt5 for the interface, PyMuPDF for PDF text extraction, and Ollama with `deepseek-r1:1.5b` for local AI answers.

## Features

- Upload one or more PDF files.
- Extract selectable PDF text.
- Ask questions using the uploaded PDF text as context.
- Ask general questions without uploading a PDF.
- Press `Enter` to ask, or `Shift+Enter` for a new line.
- Runs the AI request in the background so the app stays responsive.
- Cleans model reasoning tags and terminal control characters from responses.
- Uses a generated in-app icon, so no external icon file is required.

## Requirements

- Python 3.9 or newer
- Ollama
- The Ollama model `deepseek-r1:1.5b`

Python packages are listed in `requirements.txt`.

## Quick Start

```powershell
git clone https://github.com/aldehm3e/Ask-Chatbot.git
cd Ask-Chatbot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull deepseek-r1:1.5b
python chatbot_gui.py
```

## PDF Notes

Ask Chatbot reads selectable text from PDFs. Scanned or image-only PDFs usually need OCR before the app can extract useful text.

## Build an EXE

Install PyInstaller, then build from the project folder:

```powershell
pip install pyinstaller
pyinstaller chatbot_gui.spec
```

The executable will be created in `dist/`. Build output is ignored by Git.

## Author

Eng. Abdulrahman Alsaedi  
Islamic University of Medina
