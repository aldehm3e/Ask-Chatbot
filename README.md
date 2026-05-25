# Ask Chatbot

Ask Chatbot is a local desktop app for asking questions about PDF files. It uses PyQt5 for the interface, PyMuPDF for PDF text extraction, and Ollama for local AI answers.

## Features

- Upload one or more PDF files.
- Extract selectable PDF text by file, page, and chunk.
- Retrieve only the most relevant PDF chunks for each question instead of sending the whole PDF every time.
- Ask PDF-specific questions with source citations such as `[S1]`.
- Ask general questions without uploading a PDF.
- Search extracted text and inspect source chunks.
- Optional OCR for scanned pages when Tesseract is installed.
- Select from installed Ollama models.
- Stream answers as they are generated.
- Stop a long answer in progress.
- Copy the latest answer, clear the chat, or export the conversation.
- English and Arabic UI modes with RTL layout support.
- Runs PDF extraction and AI requests in background threads so the app stays responsive.
- Cleans model reasoning tags and terminal control characters from responses.
- Uses a generated in-app icon, so no external runtime icon file is required.

## Requirements

- Python 3.9 or newer
- Ollama
- At least one Ollama model, for example `deepseek-r1:1.5b`
- Optional: Tesseract OCR for scanned or image-only PDFs

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

## OCR Notes

Ask Chatbot reads selectable text directly from PDFs. For scanned or image-only PDFs, enable `OCR scanned pages` in the app. OCR requires the `tesseract` command to be installed and available in PATH.

Common OCR language examples:

- `eng` for English
- `ara` for Arabic
- `eng+ara` for mixed English and Arabic

## Build an EXE

Install PyInstaller, then build from the project folder:

```powershell
pip install pyinstaller
pyinstaller chatbot_gui.spec
```

The executable will be created in `dist/`. Build output is ignored by Git.

## Run Tests

```powershell
python -m unittest
```

## Project Layout

- `chatbot_gui.py` - PyQt5 desktop UI and background workers.
- `ask_chatbot/pdf_processing.py` - PDF extraction, OCR hooks, and chunking.
- `ask_chatbot/retrieval.py` - lightweight local chunk retrieval.
- `ask_chatbot/prompts.py` - source-aware prompt building.
- `ask_chatbot/ollama_client.py` - Ollama model discovery helpers.
- `ask_chatbot/response_cleaning.py` - model output cleanup.
- `tests/` - focused unit tests for core behavior.

## Author

Eng. Abdulrahman Alsaedi  
Islamic University of Medina
