# SpeakFill – Voice-to-Form Assistant

To rename the app: edit the `<h1>` and `<title>` in `web/index.html` (and `title=` in `app/main.py`).

Speak your details in Urdu / Roman Urdu / English → AI fills the form → you review → PDF.
Built with **Python (FastAPI)** + a plain HTML/JS frontend (no Node, no build step).

**A complete form costs 1–2 LLM calls** (not 50+). See "How we stay inside free API limits" below.

---------------------------------------------------------------------------

## 1. Run it on your laptop (5 minutes)

```bash
# 1. Python 3.10+ required
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Urdu font for the PDF (one time)
python download_fonts.py
#    If it fails: download "Noto Naskh Arabic" from fonts.google.com
#    and copy the .ttf file into app/fonts/

# 3. Add your API keys
cp .env.example .env               # Windows: copy .env.example .env
#    open .env and paste your keys (see section 2)

# 4. Start
uvicorn app.main:app --reload
```
Open **http://localhost:8000** in **Chrome**.

Check http://localhost:8000/api/health – it tells you which providers are active and whether the Urdu font was found.
Run tests: `python -m pytest -q`

> **No keys yet?** Press **Offline demo** on the first screen. It uses a pre-recorded transcript and a cached
> model answer, so the whole flow (including the PDF) works with zero API calls and no internet.

## 2. Get the API keys (both are free)

| Provider | Used for | Where |
|---|---|---|
| Google Gemini | Main LLM (extraction) | https://aistudio.google.com/apikey |
| Groq | LLM fallback + Whisper speech-to-text fallback | https://console.groq.com/keys |

Put them in `.env` as `GEMINI_API_KEY=` and `GROQ_API_KEY=`. Only one is required to work; both give you the fallback chain.
Free-tier limits change often. Open each dashboard's rate-limit page before the event and set
`GEMINI_RPM`, `GROQ_RPM` in `.env` slightly **below** what you see. Model names also change: if a call fails with 404,
update `GEMINI_MODEL` / `GROQ_LLM_MODEL` in `.env`.

Never put keys in the frontend or in git. `.env` is already in `.gitignore`.

## Voice not detected? (read this)
- The page has a **Voice engine** menu. **Auto** uses Whisper when `GROQ_API_KEY` is set (most reliable for Urdu), otherwise Chrome voice.
- While recording you will see **live level bars**. If they don't move, the browser is not hearing your microphone: check the lock icon in the address bar, the Windows/Android mic permission, and the selected input device.
- If nothing was heard, the app tells you and does NOT waste an API call.
- Chrome voice now restarts itself after silence and rebuilds text without duplicates. It still needs internet and HTTPS (or localhost).

## New in v2.0
- A **microphone on every field**: review screen, follow-up questions and guided mode. Tap, speak, the value fills in.
- If you do not see the new look, hard-refresh the browser (Ctrl+Shift+R). The footer must say **SpeakFill v2.0**.

## 3. How we stay inside free API limits

| Technique | Where in code | Effect |
|---|---|---|
| **One call for the whole form**, not one per field | `pipeline.extract` | 25-field form = 1 call |
| **Rules first**: CNIC, phone, email, dates found by regex, never sent to the LLM; if rules fill everything, 0 calls | `services/rules.py` | fewer calls and tokens |
| **Compact schema** (id, type, short label only), JSON-only output, `temperature 0`, Gemini thinking off | `compact_schema`, `llm_router._gemini` | small prompts, small answers |
| **Follow-up questions are local templates** (no LLM) | `pipeline.build_questions` | 0 calls |
| **Follow-up answers**: typed per-field answers use rules only; a spoken blob = 1 batched call with only the unresolved fields | `/api/clarify` | 0–1 call |
| **Max 2 clarification rounds**, then "Please fill manually" | `config.MAX_CLARIFY_ROUNDS` | no endless loops |
| **Cache** by hash(form, schema, transcript): rehearsals cost nothing | `services/cache.py` | repeat = 0 calls |
| **Browser speech-to-text first** (free); Whisper only as a fallback | `web/app.js` Recorder | 0 STT calls usually |
| **Guided mode**: field-by-field with zero AI calls (local validation) | `/api/validate` | 0 calls |
| **Edits are local**; Confirm only runs local validation | `web/app.js` | 0 calls |
| **Provider chain** Gemini → Groq → rules-only; one retry with backoff on 429/5xx | `services/llm_router.py` | no crash on limits |
| **Server-side rate limiter** (sliding window per provider) | `RateLimiter` | we never trigger a 429 ourselves |
| **Per-session budget guard** (`MAX_LLM_CALLS_PER_SESSION`) | `llm_router.call_json` | one user can't drain the quota |
| **One request in flight** (client lock + server session lock) | `app.js api()`, `session_lock` | double-clicks can't double-spend |
| **Offline demo mode** | `/api/demo` | demo never depends on the network |
| Live counter "AI / voice / cached" in the page header | `services/usage.py` | proof for the judges |

Rotating many free accounts to dodge a quota can violate provider terms, so this project doesn't do that.
If you really need more quota, enable billing on one key (the cost for this app is tiny) or use a second provider.

## 4. Deploy

The app is one Python web service that also serves the frontend, so deploy it as a single service.

### Option A: Render (recommended, free tier)
1. Push this folder to a GitHub repo (check `.env` is NOT committed).
2. render.com → **New → Blueprint** (it reads `render.yaml`) or **New → Web Service**:
   - Build: `pip install -r requirements.txt && python download_fonts.py`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. In **Environment**, add `GEMINI_API_KEY` and `GROQ_API_KEY`.
4. Open the URL. The free tier sleeps after inactivity: open the site a few minutes before your demo.

### Option B: Hugging Face Spaces (Docker)
1. New Space → SDK **Docker** → upload the files (the `Dockerfile` is included, port 7860).
2. Settings → **Secrets** → add the two keys.

### Option C: Railway
New project → Deploy from GitHub → add the two variables. Start command as in Render.

> Vercel is a poor fit for this backend (serverless time limits, no persistent font/cache files). Use Render or Spaces.
> Microphone access needs **HTTPS** (or localhost). All three options give you HTTPS automatically.

## 5. Project layout

```
app/main.py              FastAPI routes
app/services/pipeline.py rules -> cache -> 1 LLM call -> validate -> questions
app/services/llm_router.py  Gemini -> Groq -> rules-only, rate limiter, retries
app/services/rules.py    regex extraction (CNIC, phone, email, date, names)
app/services/validators.py  local validation + normalisation
app/services/pdf_builder.py ReportLab + arabic-reshaper + bidi (Urdu)
app/schemas/*.json       4 built-in forms (edit/add your own: same JSON shape)
app/demo/demo.json       offline demo data
web/                     index.html, style.css, app.js
tests/                   unit tests
```
**Add a new form:** copy any file in `app/schemas/`, change `id`, `title_*` and `fields`. Restart. Done.
Field types: `text, cnic, phone, date, email, select, number, address, textarea`.

## 6. Demo script (3 minutes)
1. Pitch: long forms + language barrier (20 s).
2. Pick **Job Application**, tap the mic, speak ~45 s in Urdu/Roman Urdu.
3. Show the transcript and the colour-coded form.
4. App asks the missing fields together; answer by voice.
5. Edit one field, press **Confirm and make PDF**.
6. Show the Urdu PDF and the header counter ("1 AI · 0 voice").
**Backup:** press **Offline demo** if the Wi-Fi or an API fails. Rehearse the real flow twice first, because the cache then makes repeat runs free.

## 7. Troubleshooting
| Problem | Fix |
|---|---|
| Mic does nothing | Use Chrome, allow the microphone, use `localhost` or HTTPS |
| "Browser voice failed" | Tick **High-accuracy voice** (needs `GROQ_API_KEY`) or type |
| AI says "busy" / filled very little | Quota or key problem: check `/api/health`; rules-only mode still filled what it could |
| Urdu in PDF shows boxes | Run `python download_fonts.py` or put a Naskh `.ttf` in `app/fonts/` |
| 404 from Gemini in logs | Model name changed: update `GEMINI_MODEL` |

## 8. Known limits (honest list)
Upload of arbitrary PDFs / OCR (PRD F3, F4, F25) is **not** included; templates only (P2 in the PRD).
Punjabi / Pashto / Sindhi work through Whisper (best effort), not the browser.
Roman Urdu *speech* is recognised as Urdu script by the speech engines; the LLM handles both scripts.
