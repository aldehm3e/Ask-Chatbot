# Instructions

## Run the App

1. Install Python 3.9 or newer.
2. Install Ollama from https://ollama.com.
3. Open PowerShell in the project folder.
4. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

5. Download a local AI model:

```powershell
ollama pull deepseek-r1:1.5b
```

6. Start the app:

```powershell
python chatbot_gui.py
```

## Use the App

1. Click `Upload PDF(s)` to select one or more PDFs.
2. Optionally enable `OCR scanned pages` before upload if the PDF is scanned.
3. Check the document panel for file count, page count, extracted characters, and chunks.
4. Search extracted text or double-click a source chunk to inspect it.
5. Choose an Ollama model from the model dropdown.
6. Type your question.
7. Press `Enter` or click `Ask`.
8. Use `Shift+Enter` if you need a new line inside the question box.
9. Click `Stop` to cancel a long answer.
10. Use `Copy Last Answer`, `Export Chat`, or `Clear Chat` as needed.

## OCR Setup

OCR is optional. If Tesseract is installed and available in PATH, Ask Chatbot can render low-text PDF pages and run OCR locally.

Useful language values:

```text
eng
ara
eng+ara
```

If OCR is enabled but Tesseract is missing, the app still extracts selectable PDF text and reports that OCR was unavailable.

## Troubleshooting

If the app says Ollama was not found, make sure Ollama is installed and available in your PATH.

If no models appear, run:

```powershell
ollama list
```

If the default model is missing, run:

```powershell
ollama pull deepseek-r1:1.5b
```

If no selectable text was found, the PDF is probably scanned or image-only. Enable OCR and make sure Tesseract is installed.

If an answer takes a while, wait for streaming output or click `Stop`. The app runs Ollama in the background so the window should stay responsive.

## Run Tests

```powershell
python -m unittest
```

## Rebuild the Windows EXE

```powershell
pip install pyinstaller
pyinstaller chatbot_gui.spec
```

The new `.exe` will appear in `dist/`. Do not commit `dist/` or `build/`; they are generated files.
