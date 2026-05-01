FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -U pip && \
    pip3 install --no-cache-dir -U -r requirements.txt

# Copy the rest of the application code
COPY . .

# Command to run the bot
CMD ["python3", "main.py"]
