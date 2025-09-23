from typing import Dict, Any, Optional
import json
import asyncssh

import state
from models import EXECUTION_MODES

async def run_ssh_command(node_info: Dict[str, Any], command: str) -> str:
    """
    Si connette a un nodo via SSH, esegue un comando e controlla l'esito.
    """
    try:
        async with asyncssh.connect(
            host=node_info["host"],
            port=node_info["port"],
            username=node_info["username"],
            password=node_info["password"],
            known_hosts=None
        ) as conn:
            result = await conn.run(command, check=True)
            return result.stdout.strip()
            
    except asyncssh.ProcessError as e:
        raise Exception(
            f"Il comando sul nodo '{node_info['host']}' è fallito con exit code {e.returncode}.\n"
            f"Stderr: {e.stderr.strip()}"
        )
    except asyncssh.Error as e:
        raise Exception(f"Errore di connessione SSH sul nodo '{node_info['host']}': {e}")
    except Exception as e:
        raise Exception(f"Errore inatteso durante l'esecuzione SSH: {e}")

async def get_metrics_for_node(node_name: str, node_info: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Recupera e parsifica le metriche di CPU e RAM per un singolo nodo."""
    try:
        metrics_json = await run_ssh_command(node_info, "/usr/local/bin/get_node_metrics.sh")
        metrics = json.loads(metrics_json)
        return {
            "cpu_usage": float(metrics.get("cpu_usage", float('inf'))),
            "ram_usage": float(metrics.get("ram_usage", float('inf'))),
        }
    except Exception as e:
        print(f"Attenzione: impossibile recuperare metriche per '{node_name}': {e}. Ignorato.")
        return None

async def prewarm_function_on_node(function_name: str, node_name: str):
    """Esegue un docker pull su node_name e aggiorna lo stato a pre-warmed"""
    if function_name not in state.function_registry or node_name not in state.node_registry:
        return

    node_info = state.node_registry[node_name]
    docker_image = state.function_registry[function_name]["image"]

    try:
        await run_ssh_command(node_info, f"sudo docker pull {docker_image}")
        
        if function_name not in state.function_state_registry:
            state.function_state_registry[function_name] = {}
        state.function_state_registry[function_name][node_name] = EXECUTION_MODES.PRE_WARMED.value
    except Exception as e:
        print(f"Errore durante il pre-warm di '{function_name}' su '{node_name}': {e}")


async def warmup_function_on_node(function_name: str, node_name: str):
    """Avvia un container in background su node_name e aggiorna lo stato a warmed"""
    if function_name not in state.function_registry or node_name not in state.node_registry:
        return

    node_info = state.node_registry[node_name]
    docker_image = state.function_registry[function_name]["image"]
    container_name = f"{state.CONTAINER_PREFIX}{function_name}--{node_name}"

    try:
        docker_cmd = f"sudo docker run -d --name {container_name} {docker_image} sleep infinity"
        await run_ssh_command(node_info, docker_cmd)
        
        if function_name not in state.function_state_registry:
            state.function_state_registry[function_name] = {}
        state.function_state_registry[function_name][node_name] = EXECUTION_MODES.WARMED.value
    except Exception as e:
        print(f"Errore durante il warm-up di '{function_name}' su '{node_name}': {e}")