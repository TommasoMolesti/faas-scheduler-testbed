import requests
import json
import time
from typing import Optional, Any

BASE_URL = "http://api_gateway:8000"
DOCKER_IMAGE = "busybox"
COMMAND = "/bin/sh -c 'echo Hello world from Busybox!'"
NUM_NODES = 5
NUM_FUNCTIONS = 10
USER = "sshuser"
PASSWORD = "sshpassword"

def register_function(name: str, docker_image: str):
    """Registra una funzione sul gateway."""
    url = f"{BASE_URL}/functions/register"
    payload = {"name": name, "docker_image": docker_image}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione della funzione: {err}")
        print(f"Dettagli: {err.response.json()}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def functions_count():
    url = f"{BASE_URL}/functions_count"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nFunzioni registrate ({response.json()})")
    except requests.exceptions.RequestException as err:
        print(f"Errore durante il recupero delle funzioni: {err}")

def register_node(name: str, host: str, username: str, password: str, port: int = 22):
    url = f"{BASE_URL}/nodes/register"
    payload = {
        "name": name,
        "host": host,
        "port": port,
        "username": username,
        "password": password
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione del nodo: {err}")
        print(f"Dettagli: {err.response.json()}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def nodes_count():
    url = f"{BASE_URL}/nodes_count"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nNodi registrati ({response.json()})")
    except requests.exceptions.RequestException as err:
        print(f"Errore durante il recupero dei nodi: {err}")

def invoke_function(function_name: str, input_data: Optional[Any] = None):
    """Invoca una funzione registrata."""
    url = f"{BASE_URL}/functions/invoke/{function_name}"
    payload = {"input": input_data}
    try:
        print(f"\nInvocazione della funzione '{function_name}'...")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Risultato invocazione: {response.json()}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante l'invocazione della funzione '{function_name}': {err}")
        print(f"Dettagli: {err.response.json()}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso durante l'invocazione: {err}")

if __name__ == "__main__":
    print("\n--- Registrazione Nodi ---")
    for i in range(1, NUM_NODES + 1):
        register_node(f"node-{i}", "ssh_node", USER, PASSWORD)
    nodes_count()

    print("\n--- Registrazione Funzioni ---")

    for i in range(1, NUM_FUNCTIONS + 1):
        register_function(f"func-{i}", f"{DOCKER_IMAGE} {COMMAND}")

    functions_count()

    time.sleep(1)

    print("\n--- Invocazione Funzioni ---")

    for i in range(1, NUM_FUNCTIONS + 1):
        invoke_function(f"func-{i}")

    print("\n--- Script client completato ---")
