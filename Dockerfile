FROM python:3.11-slim

# Install system dependencies (ffmpeg, ffprobe, curl)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp binary to /usr/local/bin/yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the application code
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Start Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
