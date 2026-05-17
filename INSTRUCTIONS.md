# Instructions

## Run the App

1. Install Python 3.9 or newer.
2. Install Ollama from https://ollama.com.
3. Open PowerShell in the project folder.
4. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

5. Download the local AI model:

```powershell
ollama pull deepseek-r1:1.5b
```

6. Start the app:

```powershell
python chatbot_gui.py
```

## Use the App

1. Click `Upload PDF(s)` to select one or more PDFs.
2. Check the extraction summary for file count, page count, and extracted characters.
3. Type your question.
4. Press `Enter` or click `Ask Chatbot`.
5. Use `Shift+Enter` if you need a new line inside the question box.
6. Click `Show Extracted Text` to inspect the PDF text that was loaded.

## Troubleshooting

If the app says Ollama was not found, make sure Ollama is installed and available in your PATH.

If the app says no selectable text was found, the PDF is probably scanned or image-only. Run OCR on the PDF first, then upload the OCR version.

If the answer takes a while, wait for the progress indicator to finish. The app runs Ollama in the background so the window should stay responsive.

If the model is missing, run:

```powershell
ollama pull deepseek-r1:1.5b
```

## Rebuild the Windows EXE

```powershell
pip install pyinstaller
pyinstaller chatbot_gui.spec
```

The new `.exe` will appear in `dist/`. Do not commit `dist/` or `build/`; they are generated files.
