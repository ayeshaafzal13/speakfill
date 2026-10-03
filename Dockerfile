FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python download_fonts.py || echo "Font download failed - add a .ttf to app/fonts manually"
# Hugging Face Spaces uses 7860; Render/Railway set $PORT
ENV PORT=7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
