from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import json
import itertools
import os
import pandas as pd
from tabulate import tabulate
import time
import asyncio
import asyncssh

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service Gateway API (Docker image execution via SSH)"
)

function_registry: Dict[str, str] = {}
node_registry: Dict[str, Dict[str, Any]] = {}
function_state_registry: Dict[str, Dict[str, str]] = {}
metrics_log: List[Dict[str, Any]] = []

class RegisterFunctionRequest(BaseModel):
    name: str = Field(..., description="Il nome univoco della funzione da registrare.")
    image: str = Field(..., description="Il nome dell'immagine Docker (es. 'python:3.11-slim').")
    command: str = Field(..., description="Il comando da eseguire nel container (es. 'python main.py').")

class RegisterNodeRequest(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str

class InvokeFunctionRequest(BaseModel):
    pass

async def _run_ssh_command_async(node_info: Dict[str, Any], command: str) -> str:
    """
    Si connette a un nodo via SSH in modo asincrono ed esegue un comando.
    """
    try:
        async with asyncssh.connect(
            host=node_info["host"],
            port=node_info["port"],
            username=node_info["username"],
            password=node_info["password"],
            known_hosts=None
        ) as conn:
            result = await conn.run(command)
            return result.stdout.strip()
    except asyncssh.Error as e:
        raise Exception(f"Errore SSH o del comando sul nodo '{node_info['host']}': {e}")
    except Exception as e:
        raise Exception(f"Errore inatteso durante l'esecuzione SSH asincrona: {e}")


async def _run_docker_on_node_async(node_info: Dict[str, Any], docker_image: str) -> str:
    """
    Esegue un'immagine Docker su un nodo via SSH in modo asincrono.
    """
    docker_cmd = f"sudo docker run --rm {docker_image}"
    return await _run_ssh_command_async(node_info, docker_cmd)

class RoundRobinPolicy():
    """
    Politica di selezione del nodo Round Robin.
    Seleziona i nodi in modo sequenziale per distribuire il carico.
    """
    def __init__(self):
        self.node_iterator = itertools.cycle([])
        self._nodes_cache = []

    async def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None, None

        current_node_names = sorted(list(nodes.keys()))

        if current_node_names != self._nodes_cache:
            self._nodes_cache = current_node_names
            self.node_iterator = itertools.cycle(current_node_names)

        try:
            selected_node = next(self.node_iterator)
            
            metric_entry = {
                "Function": function_name,
                "Node": selected_node,
                "CPU Usage % ": "N/A",
                "RAM Usage %": "N/A",
                "Execution Mode": "Round Robin - Cold"
            }
            return selected_node, metric_entry
        except StopIteration:
            return None, None

class LeastUsedPolicy():
    """
    Politica di selezione del nodo Least Used.
    Seleziona il nodo con il carico medio più basso.
    """

    async def _get_all_node_metrics(self, nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Si connette a tutti i nodi in parallelo e restituisce le loro metriche.
        """
        tasks = []
        for node_name, node_info in nodes.items():
            task = _run_ssh_command_async(node_info, "/usr/local/bin/get_node_metrics.sh")
            tasks.append((node_name, task))

        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        
        live_metrics = {}
        for (node_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                print(f"  Errore nel recupero metriche per '{node_name}': {result}. Ignorato.")
            else:
                try:
                    metrics = json.loads(result)
                    live_metrics[node_name] = {
                        "cpu_usage": float(metrics.get("cpu_usage", float('inf'))),
                        "ram_usage": float(metrics.get("ram_usage", float('inf'))),
                    }
                except (json.JSONDecodeError, TypeError):
                    print(f"Errore nel parsing del JSON da '{node_name}'.")
        
        return live_metrics

    async def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None, None

        node_metrics = await self._get_all_node_metrics(nodes)
        
        if not node_metrics:
            print("Least Used: Impossibile recuperare le metriche da alcun nodo.")
            return None, None

        min_load = float('inf')
        selected_node = None
        
        for node_name, metrics in node_metrics.items():
            current_load = (metrics["cpu_usage"] + metrics["ram_usage"]) / 2
            if current_load < min_load:
                min_load = current_load
                selected_node = node_name
        
        if selected_node:
            metric_entry = {
                "Function": function_name,
                "Node": selected_node,
                "CPU Usage % ": node_metrics[selected_node]['cpu_usage'],
                "RAM Usage %": node_metrics[selected_node]['ram_usage'],
                "Execution Mode": "Least Used - Cold"
            }
            return selected_node, metric_entry
        
        return None, None

class CyclicWarmingPolicy():
    """
    Policy che esegue il pre-warm e il warm in modo ciclico
    in base all'ordine di registrazione delle funzioni.
    """
    async def apply(self, function_name: str, node_name: str):
        # Ogni 3 funzioni ne preparo una "pre-warmed"
        if len(function_registry) % 3 == 1:
            await _prewarm_function_on_node(function_name, node_name)

        # Ogni 3 funzioni (con offset 2) ne preparo una "warmed"
        if len(function_registry) % 3 == 2:
            await _warmup_function_on_node(function_name, node_name)

class WarmedFirstPolicy:
    """
    Seleziona un nodo dando priorità a Warmed > Pre-warmed > Default Policy.
    """
    async def select_node(self, function_name: str):
        node_name = None
        metric_to_write = None
        execution_mode = None

        # Priorità 1: Cerca un'istanza 'warmed'
        if function_name in function_state_registry:
            for n, state in function_state_registry[function_name].items():
                if state == "warmed":
                    node_name = n
                    execution_mode = "Warmed"
                    break
        
        # Priorità 2: Cerca un'istanza 'pre-warmed'
        if not node_name and function_name in function_state_registry:
            for n, state in function_state_registry[function_name].items():
                if state == "pre-warmed":
                    node_name = n
                    execution_mode = "Pre-warmed"
                    break

        # Priorità 3: Fallback sulla policy di scheduling
        if not node_name:
            node_name, metric_to_write = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, function_name)
            if not node_name:
                raise HTTPException(status_code=503, detail="Nessun nodo disponibile.")
            execution_mode = metric_to_write.get("Execution Mode", "Unknown")

        return node_name, metric_to_write, execution_mode

class PreWarmedFirstPolicy:
    """
    Seleziona un nodo dando priorità a Pre-warmed > Default Policy.
    """
    async def select_node(self, function_name: str):
        node_name = None
        metric_to_write = None
        execution_mode = None

        # Priorità 1: Cerca un'istanza 'pre-warmed'
        if function_name in function_state_registry:
            for n, state in function_state_registry[function_name].items():
                if state == "pre-warmed":
                    node_name = n
                    node_name = "Pre-warmed"
                    break

        # Priorità 2: Fallback sulla policy di scheduling
        if not node_name:
            node_name, metric_to_write = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, function_name)
            if not node_name:
                raise HTTPException(status_code=503, detail="Nessun nodo disponibile.")
            execution_mode = metric_to_write.get("Execution Mode", "Unknown")

        return node_name, metric_to_write, execution_mode

class DefaultColdPolicy:
    """
    Utilizza sempre la policy di scheduling di default per un'esecuzione Cold.
    """
    async def select_node(self, function_name: str):
        node_name, metric_to_write = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, function_name)
        if not node_name:
            raise HTTPException(status_code=503, detail="Nessun nodo disponibile.")
        
        execution_mode = metric_to_write.get("Execution Mode", "Unknown")

        return node_name, metric_to_write, execution_mode

# DEFAULT_SCHEDULING_POLICY = RoundRobinPolicy()
DEFAULT_SCHEDULING_POLICY = LeastUsedPolicy()

WARMING_POLICY = CyclicWarmingPolicy()

# NODE_SELECTION_POLICY = PreWarmedFirstPolicy()
NODE_SELECTION_POLICY = WarmedFirstPolicy()
# NODE_SELECTION_POLICY = DefaultColdPolicy()

def write_metrics_table(output_file="metrics_table.txt"):
    if not metrics_log:
        return

    try:
        df = pd.DataFrame(metrics_log)
        table = tabulate(df, headers='keys', tablefmt='grid', showindex=False)

        with open(output_file, 'w') as f:
            f.write(table)
    except Exception as e:
        print(f"Errore durante la scrittura della tabella delle metriche: {e}")

def clean(filename):
    file_path = os.path.join("/app", filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'w') as f:
                f.truncate(0)
        except Exception as e:
            print(f"Errore durante la pulizia del file '{file_path}': {e}")

@app.post("/init")
def init():
    metrics_log.clear()
    clean("metrics_table.txt")

@app.post("/functions/register")
async def register_function(req: RegisterFunctionRequest):
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = {"image": req.image, "command": req.command}

    node_name, _ = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, req.name)

    await WARMING_POLICY.apply(req.name, node_name)


@app.get("/functions")
def list_functions() -> Dict[str, str]:
    return function_registry

@app.post("/nodes/register")
def register_node(req: RegisterNodeRequest):
    if req.name in node_registry:
        raise HTTPException(status_code=400, detail=f"Nodo '{req.name}' già registrato.")
    node_registry[req.name] = {
        "host": req.host,
        "port": req.port,
        "username": req.username,
        "password": req.password
    }

@app.get("/nodes")
def list_nodes() -> Dict[str, Dict[str, Any]]:
    return {name: {k: v for k, v in info.items() if k != "password"} for name, info in node_registry.items()}

@app.post("/functions/invoke/{function_name}")
async def invoke_function(function_name: str, req: InvokeFunctionRequest):
    start_time = time.perf_counter()

    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    node_name, metric_to_write, execution_mode = await NODE_SELECTION_POLICY.select_node(function_name)

    node_info = node_registry[node_name]
    function_details = function_registry[function_name]

    try:
        if execution_mode == "Warmed":
            container_name = f"warmed--{function_name}--{node_name}"
            command_to_run = function_details["command"]
            # Uso docker exec per eseguire lo script nel container già attivo
            output = await _run_ssh_command_async(node_info, f"sudo docker exec {container_name} {command_to_run}")
        else:
            image_and_command = f'{function_details["image"]} {function_details["command"]}'
            output = await _run_docker_on_node_async(node_info, image_and_command)
            # Se era pre-warmed, ora è "usato", quindi torna cold.
            if execution_mode == "Pre-warmed":
                function_state_registry[function_name][node_name] = "cold"

        end_time = time.perf_counter()
        duration = end_time - start_time

        if not metric_to_write:
            metric_to_write = { "Function": function_name, "Node": node_name, "CPU Usage % ": "---", "RAM Usage %": "---" }

        metric_to_write["Execution Mode"] = execution_mode
        metric_to_write["Execution Time (s)"] = f"{duration:.4f}"
        metrics_log.append(metric_to_write)
        write_metrics_table()

    except Exception as e:
        end_time = time.perf_counter()
        duration = end_time - start_time
        print(f"Invocazione fallita dopo {duration:.4f} secondi.")
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")

async def _prewarm_function_on_node(function_name: str, node_name: str):
    """Esegue un docker pull su node_name e aggiorna lo stato a pre-warmed"""
    if function_name not in function_registry or node_name not in node_registry:
        return

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]["image"]

    try:
        await _run_ssh_command_async(node_info, f"sudo docker pull {docker_image}")
        
        if function_name not in function_state_registry:
            function_state_registry[function_name] = {}
        function_state_registry[function_name][node_name] = "pre-warmed"
    except Exception as e:
        print(f"Errore durante il pre-warm di '{function_name}' su '{node_name}': {e}")


async def _warmup_function_on_node(function_name: str, node_name: str):
    """Avvia un container in background su node_name e aggiorna lo stato a warmed"""
    if function_name not in function_registry or node_name not in node_registry:
        return

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]["image"]
    container_name = f"warmed--{function_name}--{node_name}"

    try:
        # Pulisco eventuali container vecchi con lo stesso nome per evitare conflitti.
        await _run_ssh_command_async(node_info, f"sudo docker rm -f {container_name}")

        # Avvio il nuovo container usando "sleep infinity" per mantenerlo attivo
        docker_cmd = f"sudo docker run -d --name {container_name} {docker_image} sleep infinity"
        await _run_ssh_command_async(node_info, docker_cmd)
        
        if function_name not in function_state_registry:
            function_state_registry[function_name] = {}
        function_state_registry[function_name][node_name] = "warmed"
    except Exception as e:
        print(f"Errore durante il warm-up di '{function_name}' su '{node_name}': {e}")