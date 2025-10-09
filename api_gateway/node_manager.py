from typing import Dict, Any, Optional
import json
import asyncssh

import state
from models import EXECUTION_MODES

async def run_ssh_command(node_info: Dict[str, Any], command: str) -> str:
    """
    Connects to a node via SSH, executes a command, and checks the outcome.
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
            f"The command on node '{node_info['host']}' failed with exit code {e.returncode}.n"
            f"Stderr: {e.stderr.strip()}"
        )
    except asyncssh.Error as e:
        raise Exception(f"SSH connection error on node '{node_info['host']}': {e}")
    except Exception as e:
        raise Exception(f"Unexpected error during SSH execution: {e}")

async def get_metrics_for_node(node_name: str, node_info: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Retrieves and parses CPU and RAM metrics for a single node."""
    try:
        metrics_json = await run_ssh_command(node_info, "/usr/local/bin/get_node_metrics.sh")
        metrics = json.loads(metrics_json)
        return {
            "cpu_usage": float(metrics.get("cpu_usage", float('inf'))),
            "ram_usage": float(metrics.get("ram_usage", float('inf'))),
        }
    except Exception as e:
        print(f"Warning: Unable to retrieve metrics for '{node_name}': {e}. Ignored.")
        return None

async def prewarm_function_on_node(function_name: str, node_name: str):
    """Performs a docker pull on node_name and updates the status to pre-warmed."""
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
        print(f"Error during pre-warm of '{function_name}' on '{node_name}': {e}")


async def warmup_function_on_node(function_name: str, node_name: str):
    """Start a container in the background on node_name and update the status to warmed"""
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
        print(f"Error during warm-up of '{function_name}' on '{node_name}': {e}")