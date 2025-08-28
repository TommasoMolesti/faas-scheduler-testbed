FROM python:3.11

WORKDIR /app

COPY custom_python_heavy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY custom_python_heavy/loop_function.py .