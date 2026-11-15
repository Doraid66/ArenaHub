# ArenaHub API image
# Start from a small official Python 3.12 image.
FROM python:3.12-slim

# Don't write .pyc files, print logs immediately, keep the image small.
ENV PYTHONDONTWRITEBYTECODE=1 \
# Skip .pyc files; they only add clutter in a container.
    PYTHONUNBUFFERED=1 \
# Send logs straight to the console without buffering.
    PYTHONPATH=/app \
# Let Python find the "app" package from anywhere.
    PIP_NO_CACHE_DIR=1 \
# Do not keep pip's download cache in the image.
    PIP_DISABLE_PIP_VERSION_CHECK=1
# Skip pip's "new version available" check.

# All following commands run from /app inside the container.
WORKDIR /app

# Install dependencies first: Docker caches this layer, so rebuilding after a
# code change is fast as long as requirements.txt didn't change.
# Copy only the dependency list first, so this layer stays cached.
COPY requirements.txt .
# Install the Python packages.
RUN pip install -r requirements.txt

# Copy the application code.
# Copy everything else (anything in .dockerignore is skipped).
COPY . .

# Run as a normal user, not root.
# Create a non-root user with a fixed ID.
RUN useradd --create-home --uid 1000 appuser
# Switch to that user for everything after this point.
USER appuser

# Document that the API listens on port 8000.
EXPOSE 8000

# Migrate the database, load demo data, then start the API.
# Run the start-up script when the container starts.
CMD ["sh", "scripts/start.sh"]
