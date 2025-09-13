FROM python:3.11-slim

WORKDIR /app

COPY custom_python_light/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY custom_python_light/loop_function.py .