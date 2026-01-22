FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (for OCR fallback)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port FastAPI runs on
EXPOSE 8000

# Start command
CMD ["uvicorn", "pdf_parser:app", "--host", "0.0.0.0", "--port", "8000"]
