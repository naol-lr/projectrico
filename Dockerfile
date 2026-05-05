FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright/Chromium (cached layer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
    libatspi2.0-0t64 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64 libxkbcommon0 \
    libx11-xcb1 fonts-liberation fonts-noto-color-emoji xvfb \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached when requirements.txt unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser binary (system deps already present)
RUN playwright install chromium

# Copy application code
COPY . .

CMD ["python3", "V10 BOT.py"]
