<div align="center">

# 🎙️ SpeakFill

### Speak once. We fill the form.

**Voice-to-form assistant for Urdu, Roman Urdu and English.**
Speak your details, review the AI-filled form, and download a print-ready PDF.

### 🔴Live Demo →  https://speakfill.onrender.com/

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-LLM-4285F4?logo=google&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Whisper%20%2B%20Llama-F55036)
![License](https://img.shields.io/badge/License-MIT-green)

[Live Demo](https://YOUR-APP-NAME.onrender.com) · [Demo Video](https://YOUR-VIDEO-LINK) · [PRD](docs/SpeakFill_PRD.docx)

</div>

---

## 📌 The Problem

Forms for banks, universities and employers are long, written in English, and strict about formats (CNIC, phone, dates). Many people can't read them confidently or can't type quickly in English, so they pay middlemen and hand over private data to strangers.

## 💡 The Solution

SpeakFill lets you **talk instead of type**. Speak in Urdu, Roman Urdu or English. The app transcribes your speech, extracts every field, validates Pakistani formats, asks only for what's missing, and generates a clean **bilingual PDF with correct Urdu text**.

> A complete form costs only **1 to 2 AI calls**, not one per field.

## ✨ Features

| Feature | Description |
|---|---|
| 🗣️ **Multilingual voice input** | Urdu script, Roman Urdu, English (Punjabi, Pashto, Sindhi via Whisper, best effort) |
| ⚡ **Say everything at once** | One 45-second recording fills the whole form |
| 🧭 **Guided mode** | One question at a time, with zero AI calls |
| 🎨 **Colour-coded review** | Green = OK, yellow = check, red = missing |
| ❓ **Smart follow-ups** | Asks only for missing fields, all together (max 2 rounds) |
| 🎤 **Mic on every field** | Fix any value by voice or keyboard |
| ✅ **Local validation** | CNIC, phone, email, dates checked without an LLM |
| 📄 **Urdu-ready PDF** | Proper right-to-left shaping with bilingual labels |
| 🛡️ **Never crashes** | Gemini → Groq → rules-only fallback chain |
| 📴 **Offline demo** | Works with every API down |

## 🧠 How It Stays Fast and Cheap

```
Voice → Speech-to-text → Rules (regex) → Cache → ONE LLM call → Local validation → Review → PDF
```

- **Rules first:** CNIC, phone, email and dates are found by regex and never sent to the LLM.
- **One batched call** for the whole form, using a compact schema and JSON-only output.
- **Cache:** the same input costs nothing the second time.
- **Local follow-up questions:** no AI needed.
- **Rate limiter + per-session budget** so free-tier quotas are never exceeded.
- A live counter in the header shows AI / voice / cached calls.

## 🏗️ Tech Stack

- **Backend:** Python, FastAPI, Pydantic
- **AI:** Google Gemini (primary), Groq Llama 3.3 (fallback), Groq Whisper (speech)
- **Frontend:** HTML, CSS, JavaScript (no build step), Web Speech API
- **PDF:** ReportLab, arabic-reshaper, python-bidi, Noto Naskh Arabic
- **Deploy:** Render / Hugging Face Spaces / Railway, Docker supported

## 🚀 Run Locally

```bash
# 1. Clone
git clone https://github.com/YOUR-USERNAME/speakfill.git
cd speakfill

# 2. Create environment (Python 3.10+)
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Urdu font for the PDF (one time)
python download_fonts.py

# 4. Add your API keys
copy .env.example .env            # Mac/Linux: cp .env.example .env
# open .env and paste GEMINI_API_KEY and GROQ_API_KEY

# 5. Start
uvicorn app.main:app --reload
```

Open **http://localhost:8000** in **Chrome**. Check `http://localhost:8000/api/health` to confirm your providers and font are active.

**Free API keys:** [Google AI Studio](https://aistudio.google.com/apikey) · [Groq Console](https://console.groq.com/keys)

> No keys yet? Click **▶ Offline demo** on the first screen. The whole flow works without internet.

## 🧪 Tests

```bash
python -m pytest -q
```

## 📁 Project Structure

```
app/
├── main.py                 FastAPI routes
├── config.py               Settings from environment variables
├── services/
│   ├── pipeline.py         rules → cache → 1 LLM call → validate → questions
│   ├── llm_router.py       Gemini → Groq → rules-only, rate limiter, retries
│   ├── rules.py            regex extraction (CNIC, phone, email, date)
│   ├── validators.py       local validation and normalisation
│   ├── stt.py              Whisper speech-to-text fallback
│   ├── pdf_builder.py      Urdu-capable PDF generation
│   ├── cache.py            result cache
│   └── usage.py            AI / voice / cached counters
├── schemas/                built-in forms (JSON)
└── demo/demo.json          offline demo data
web/                        index.html, style.css, app.js
tests/                      unit tests
docs/                       PRD and screenshots
```

## ➕ Add Your Own Form

Copy any file in `app/schemas/`, change `id`, `title_en`, `title_ur` and `fields`, then restart. No code changes needed.

Field types: `text`, `cnic`, `phone`, `date`, `email`, `select`, `number`, `address`, `textarea`.

**Built-in forms:** Job Application · Bank Account Opening · University Admission · Complaint Letter

## 🔌 API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Active providers, font status |
| GET | `/api/forms` | List forms |
| POST | `/api/transcribe` | Audio → text |
| POST | `/api/extract` | Transcript → filled fields |
| POST | `/api/clarify` | Resolve missing fields |
| POST | `/api/validate` | Local validation only |
| POST | `/api/pdf` | Values → PDF |

Interactive docs are available at `/docs` when the server is running.

## ☁️ Deploy

1. Push this repo to GitHub (make sure `.env` is **not** committed).
2. On [Render](https://render.com): **New → Blueprint** → select the repo (reads `render.yaml`).
3. Add `GEMINI_API_KEY` and `GROQ_API_KEY` in the environment settings.
4. Deploy. HTTPS is automatic, which the microphone requires.

Also supports Hugging Face Spaces (Docker) and Railway. The free tier sleeps when idle, so open the site a few minutes before a demo.

## 🗺️ Roadmap

- [x] Voice dictation and guided mode
- [x] 4 built-in forms, Urdu PDF, offline demo
- [ ] Upload any PDF or image and auto-detect fields (OCR)
- [ ] Opt-in saved profile for repeat forms
- [ ] Form builder for organisations
- [ ] WhatsApp bot and embeddable widget
- [ ] Direct integrations with institutions

## 🔒 Privacy

No accounts and no database of personal data. API keys stay on the server and are never exposed to the browser. Audio and text are sent only to the configured speech and LLM providers. Users always review and confirm before a PDF is created.

## ⚠️ Known Limits

- Arbitrary PDF upload / OCR is not included yet (see Roadmap).
- Punjabi, Pashto and Sindhi work through Whisper on a best-effort basis.
- Free-tier API limits and model names change; update `.env` if a call returns 404.

## 📸 Screenshots

<!-- Add your images to docs/ and uncomment -->
<!-- ![Home](docs/home.png) -->
<!-- ![Review](docs/review.png) -->
<!-- ![PDF](docs/pdf.png) -->

## 👥 Team

Built for **[Hackathon Name]** by **[Your Name / Team Name]**.

## 📄 License

MIT License. See [LICENSE](LICENSE) if you add one.

---

<div align="center">
<b>SpeakFill</b>: because everyone deserves to fill a form in their own language. 🇵🇰
</div>
