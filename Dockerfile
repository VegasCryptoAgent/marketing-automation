FROM python:3.11-slim

# Install system dependencies (ffmpeg/ffprobe, Chromium for HyperFrames renders, fonts)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    ffmpeg \
    curl \
    unzip \
    chromium \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    dbus \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Official Node 22 tarball. NodeSource's setup script is not pipefail-safe and
# can leave Debian's nodejs (no npm) on the image, which breaks hyperframes.
RUN curl -fsSL https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1 \
    && node -v && npm -v

RUN printf '%s\n' '#!/bin/sh' 'exec /usr/bin/chromium --no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage --disable-gpu "$@"' > /usr/local/bin/chromium-no-sandbox \
    && chmod +x /usr/local/bin/chromium-no-sandbox

ENV PUPPETEER_EXECUTABLE_PATH=/usr/local/bin/chromium-no-sandbox
ENV HYPERFRAMES_BROWSER_PATH=/usr/local/bin/chromium-no-sandbox

# Install yt-dlp binary to /usr/local/bin/yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# Deno is required by current yt-dlp YouTube JS challenges (player_client=tv).
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && chmod a+rx /usr/local/bin/deno

ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app

# Preinstall HyperFrames locally so npx resolves the package runtime from /app/node_modules.
RUN npm install hyperframes@0.7.40

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the application code
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Start Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
