import requests
import json
import time
from typing import Optional, Any, List

BASE_URL = "http://api_gateway:8000"

DOCKER_IMAGE = "busybox"
COMMAND = "echo Hello world from Busybox!"
NUM_FUNCTIONS = 20
USER = "sshuser"
PASSWORD = "sshpassword"
SSH_NODE_SERVICE_NAMES = [
    "ssh_node_1",
    "ssh_node_2",
    "ssh_node_3",
    "ssh_node_4"
]

def register_function(name: str, docker_image: str):
    """Registra una funzione sul gateway."""
    url = f"{BASE_URL}/functions/register"
    payload = {"name": name, "docker_image": docker_image}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        response_data = response.json()
        if 'message' in response_data:
            print(f"Funzione registrata: {response_data['message']}")
        else:
            print(f"Funzione registrata (risposta completa): {response_data}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione della funzione: {err}")
        try:
            error_details = err.response.json()
            print(f"Dettagli: {error_details}")
        except json.JSONDecodeError:
            print(f"Dettagli: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def functions_count():
    url = f"{BASE_URL}/functions_count"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nFunzioni registrate: {response.json()}")
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
        response_data = response.json()
        if 'message' in response_data:
            print(f"Nodo registrato: {response_data['message']}")
        else:
            print(f"Nodo registrato (risposta completa): {response_data}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione del nodo: {err}")
        try:
            error_details = err.response.json()
            print(f"Dettagli: {error_details}")
        except json.JSONDecodeError:
            print(f"Dettagli: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def nodes_count():
    url = f"{BASE_URL}/nodes_count"
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"\nNodi fisici registrati: {response.json()}")
    except requests.exceptions.RequestException as err:
        print(f"Errore durante il recupero dei nodi: {err}")

def invoke_function(function_name: str, policy: str = "round_robin", input_data: Optional[Any] = None):
    url = f"{BASE_URL}/functions/invoke/{function_name}"
    payload = {"input": input_data, "policy_name": policy}
    try:
        print(f"\nInvocazione della funzione '{function_name}' con politica '{policy}'...")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        response_data = response.json()
        if 'output' in response_data:
            print(f"Risultato invocazione (nodo: {response_data.get('node')}, politica: {response_data.get('policy_used')}): {response_data['output'].strip()}")
        else:
            print(f"Risultato invocazione (completo): {response_data}")
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante l'invocazione della funzione '{function_name}': {err}")
        try:
            error_details = err.response.json()
            print(f"Dettagli: {error_details}")
        except json.JSONDecodeError:
            print(f"Dettagli: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso durante l'invocazione: {err}")

if __name__ == "__main__":
    print("\n--- Registrazione Nodi Fisici ---")
    for service_name in SSH_NODE_SERVICE_NAMES:
        print(f"Registrazione nodo fisico: {service_name}")
        register_node(service_name, service_name, USER, PASSWORD, port=22)
    nodes_count()

    print("\n--- Registrazione Funzioni ---")
    for i in range(1, NUM_FUNCTIONS + 1):
        register_function(f"func-{i}", f"{DOCKER_IMAGE} /bin/sh -c '{COMMAND}'")
    functions_count()

    # print("\n--- Invocazione Funzioni (Politica Round Robin) ---")
    # for i in range(1, NUM_FUNCTIONS + 1):
    #     invoke_function(f"func-{i}", policy="round_robin")

    print("\n--- Invocazione Funzioni (Politica Least Loaded) ---")
    for i in range(1, NUM_FUNCTIONS + 1):
        invoke_function(f"func-{i}", policy="least_loaded")

    print("\nScript client completato.")
