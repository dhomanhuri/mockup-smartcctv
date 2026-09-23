FROM python:3.12-slim

# libgl1/libglib2.0-0: opencv-python-headless still dynamically links against
# these even in its "headless" build; without them cv2 fails to import.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --force-reinstall opencv-python-headless==4.10.0.84

COPY models/ models/
COPY inference.py .

CMD ["python", "-u", "inference.py"]
