import requests
import json
import time
import constants
from typing import List

def register_function(name: str, image: str, command: str):
    """Registra una funzione sul gateway."""
    url = f"{constants.BASE_URL}/functions/register"
    payload = {"name": name, "image": image, "command": command}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante la registrazione della funzione: {err}")
        try:
            error_details = err.response.json()
            print(f"Dettagli: {error_details}")
        except json.JSONDecodeError:
            print(f"Dettagli: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {constants.BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def register_node(name: str, host: str, username: str, password: str, port: int = 22):
    url = f"{constants.BASE_URL}/nodes/register"
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
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {constants.BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso: {err}")

def invoke_function(function_name: str):
    """Invia una singola richiesta di invocazione in modo asincrono."""
    url = f"{constants.BASE_URL}/functions/invoke/{function_name}"
    try:
        response = requests.post(url, timeout=None)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Errore HTTP durante l'invocazione della funzione '{function_name}': {err}")
        try:
            error_details = err.response.json()
            print(f"Dettagli: {error_details}")
        except json.JSONDecodeError:
            print(f"Dettagli: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Errore di connessione: Assicurati che il server FastAPI sia in esecuzione su {constants.BASE_URL}. Dettagli: {err}")
    except Exception as err:
        print(f"Si è verificato un errore inatteso durante l'invocazione: {err}")

if __name__ == "__main__":
    for service_name in constants.SSH_NODE_SERVICE_NAMES:
        register_node(service_name, service_name, constants.USER, constants.PASSWORD, port=22)
    
    func_name_small = "fibonacci-image-big-func-small"
    register_function(func_name_small, constants.DOCKER_IMAGE_HEAVY, constants.COMMAND_LIGHT)

    func_name_big = "fibonacci-image-small-func-big"
    register_function(func_name_big, constants.DOCKER_IMAGE_LIGHT, constants.COMMAND_HEAVY)

    tasks_to_run = []
    for _ in range(constants.INVOCATIONS):
        invoke_function(func_name_small)
        time.sleep(1)
        invoke_function(func_name_big)