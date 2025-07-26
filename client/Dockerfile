# Usa un'immagine Python ufficiale come base
FROM python:3.11-slim

# Imposta la directory di lavoro nel container
WORKDIR /app

# Copia i requirements del client e installa le dipendenze
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice del client
COPY client.py .

# Comando predefinito per eseguire lo script client
# Il 'sleep 10' è una tecnica semplice per dare tempo al gateway di avviarsi.
# Una soluzione più robusta sarebbe un healthcheck nel docker-compose.yml per il gateway.
CMD ["sh", "-c", "sleep 10 && python client.py"]