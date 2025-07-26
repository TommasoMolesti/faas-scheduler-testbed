import requests
import json
import time
from typing import Optional, Any

BASE_URL = "http://api_gateway:8000"

def register_function(name: str, docker_image: str):
    """Registra una funzione sul gateway."""
    url = f"{BASE_URL}/functions/register"
    payload = {"name": name, "docker_image": docker_image}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Funzione registrata: {response.json()}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione della funzione: {err}")
        print(f"Dettagli: {err.response.json()}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def list_functions():
    """Elenca tutte le funzioni registrate."""
    url = f"{BASE_URL}/functions"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nFunzioni registrate: {response.json()}")
    except requests.exceptions.RequestException as err:
        print(f"Errore durante il recupero delle funzioni: {err}")

def register_node(name: str, host: str, username: str, password: str, port: int = 22):
    """Registra un nodo sul gateway."""
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
        print(f"Nodo registrato: {response.json()}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione del nodo: {err}")
        print(f"Dettagli: {err.response.json()}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def list_nodes():
    """Elenca tutti i nodi registrati."""
    url = f"{BASE_URL}/nodes"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nNodi registrati: {response.json()}")
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
    # --- Registrazione Nodi ---
    print("\n--- Registrazione Nodi ---")
    register_node("my-local-node", "ssh_node", "sshuser", "sshpassword")
    # Un eventuale secondo nodo
    # register_node("another-node", "ANOTHER_SSH_HOST", "ANOTHER_SSH_USERNAME", "ANOTHER_SSH_PASSWORD")

    list_nodes()

    # --- Registrazione Funzioni ---
    print("\n--- Registrazione Funzioni ---")
    register_function("hello_world_ubuntu", "ubuntu:latest") # Questa immagine potrebbe non avere un entrypoint di default che produce output visibile facilmente
    register_function("hello_world_alpine", "alpine/git") # Un'altra immagine di base

    list_functions()

    # Breve pausa per assicurarsi che le registrazioni siano elaborate dal server
    time.sleep(1)

    # --- Invocazione Funzioni ---
    print("\n--- Invocazione Funzioni ---")

    invoke_function("hello_world_ubuntu")
    invoke_function("hello_world_alpine")

    print("\nScript client completato.")
