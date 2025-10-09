import requests
import json
import time
import constants
from typing import List

def register_function(name: str, image: str, command: str):
    """Register a function on the gateway."""
    url = f"{constants.BASE_URL}/functions/register"
    payload = {"name": name, "image": image, "command": command}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error during function registration: {err}")
        try:
            error_details = err.response.json()
            print(f"Details: {error_details}")
        except json.JSONDecodeError:
            print(f"Details: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Connection error: Make sure the FastAPI server is running at {constants.BASE_URL}. Details: {err}")
    except Exception as err:
        print(f"An unexpected error has occurred: {err}")

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
        print(f"HTTP error during node registration: {err}")
        try:
            error_details = err.response.json()
            print(f"Details: {error_details}")
        except json.JSONDecodeError:
            print(f"Details: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Connection error: Make sure the FastAPI server is running at {constants.BASE_URL}. Details: {err}")
    except Exception as err:
        print(f"An unexpected error has occurred: {err}")

def invoke_function(function_name: str):
    """Invia una singola richiesta di invocazione in modo asincrono."""
    url = f"{constants.BASE_URL}/functions/invoke/{function_name}"
    try:
        response = requests.post(url, timeout=None)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error while invoking the function ‘{function_name}’: {err}")
        try:
            error_details = err.response.json()
            print(f"Details: {error_details}")
        except json.JSONDecodeError:
            print(f"Details: {err.response.text}")
    except requests.exceptions.ConnectionError as err:
        print(f"Connection error: Make sure the FastAPI server is running at {constants.BASE_URL}. Details: {err}")
    except Exception as err:
        print(f"An unexpected error occurred during invocation: {err}")

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
        invoke_function(func_name_big)