# ArenaHub API image
FROM python:3.12-slim

# Don't write .pyc files, print logs immediately, keep the image small.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first: Docker caches this layer, so rebuilding after a
# code change is fast as long as requirements.txt didn't change.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code.
COPY . .

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Migrate the database, load demo data, then start the API.
CMD ["sh", "scripts/start.sh"]