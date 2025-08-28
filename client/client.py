import requests
import json
import time
from typing import Optional, Any, List

BASE_URL = "http://api_gateway:8000"

DOCKER_IMAGE = "tommasomolesti/custom_python_heavy:v2"
COMMAND = "python loop_function.py"
NUM_FUNCTIONS = 20
USER = "sshuser"
PASSWORD = "sshpassword"
SSH_NODE_SERVICE_NAMES = [
    "ssh_node_1",
    "ssh_node_2",
    "ssh_node_3",
    "ssh_node_4"
]

def register_function(name: str, image: str, command: str):
    """Registra una funzione sul gateway."""
    url = f"{BASE_URL}/functions/register"
    payload = {"name": name, "image": image, "command": command}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        response_data = response.json()
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

def invoke_function(function_name: str):
    url = f"{BASE_URL}/functions/invoke/{function_name}"
    payload = {}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        response_data = response.json()
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

def init():
    url = f"{BASE_URL}/init"
    try:
        response = requests.post(url)
        response.raise_for_status()
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
    init()
    for service_name in SSH_NODE_SERVICE_NAMES:
        register_node(service_name, service_name, USER, PASSWORD, port=22)
    
    for i in range(0, NUM_FUNCTIONS):
        func_name = f"func-{i+1}"
        
        register_function(func_name, DOCKER_IMAGE, COMMAND)
        invoke_function(func_name)
