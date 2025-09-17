import requests
import json
import time
import constants
from typing import List
import asyncio
import httpx

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

async def async_invoke_function(client: httpx.AsyncClient, function_name: str, task_id: int):
    """Invia una singola richiesta di invocazione in modo asincrono."""
    url = f"{constants.BASE_URL}/functions/invoke/{function_name}"
    try:
        response = await client.post(url, timeout=None)
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        print(f"Errore HTTP per {function_name}: {err.response.status_code} - {err.response.text}")
    except httpx.ReadTimeout:
        print(f"Errore TIMEOUT per {function_name}: Il gateway non ha risposto in tempo.")
    except httpx.ConnectError as err:
        print(f"Errore di CONNESSIONE per {function_name}: Impossibile connettersi al gateway. Dettagli: {err}")
    except Exception as err:
        print(f"Errore inatteso per {function_name} (Tipo: {type(err).__name__}): {err}")

async def main():
    for service_name in constants.SSH_NODE_SERVICE_NAMES:
        register_node(service_name, service_name, constants.USER, constants.PASSWORD, port=22)
    
    func_name_small = "fibonacci-image-big-func-small"
    register_function(func_name_small, constants.DOCKER_IMAGE_HEAVY, constants.COMMAND)

    func_name_big = "fibonacci-image-small-func-big"
    register_function(func_name_big, constants.DOCKER_IMAGE_LIGHT, constants.COMMAND)

    tasks_to_run = []
    for _ in range(constants.INVOCATIONS):
        tasks_to_run.append(func_name_small)
        tasks_to_run.append(func_name_big)
    
    async with httpx.AsyncClient() as client:
        invocation_tasks = []
        for i, func_name in enumerate(tasks_to_run):
            task = asyncio.create_task(async_invoke_function(client, func_name, i+1))
            invocation_tasks.append(task)
        
        await asyncio.gather(*invocation_tasks)

if __name__ == "__main__":
    asyncio.run(main())