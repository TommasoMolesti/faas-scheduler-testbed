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

class NodeSelectionPolicy:
    """
    Classe base per la politica di selezione del nodo.
    Sovrascrivi 'select_node' per politiche personalizzate.
    Politica di default: sceglie il primo disponibile
    """
    async def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        return next(iter(nodes.keys())) if nodes else None

class RoundRobinNodeSelectionPolicy(NodeSelectionPolicy):
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
                "Policy": "Round Robin"
            }
            return selected_node, metric_entry
        except StopIteration:
            return None, None

class LeastUsedNodeSelectionPolicy(NodeSelectionPolicy):
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
                "Policy": "Least Used"
            }
            return selected_node, metric_entry
        
        return None, None

# SCHEDULING_POLICY = {
#     "name": "Round Robin",
#     "instance": RoundRobinNodeSelectionPolicy()
# }

SCHEDULING_POLICY = {
    "name": "Least Used",
    "instance": LeastUsedNodeSelectionPolicy()
}

def write_metrics_to_csv(metrics_data: Dict[str, Any], filename: str = "metrics.csv"):
    file_path = os.path.join("/app", filename)
    df = pd.DataFrame([metrics_data])
    write_header = not os.path.exists(file_path) or os.path.getsize(file_path) == 0

    df.to_csv(file_path, mode='a', header=write_header, index=False)

def format_csv_as_table(input_file="metrics.csv", output_file="metrics_table.txt"):
    if not os.path.exists(input_file):
        print(f"Il file {input_file} non esiste.")
        return False
    
    try:
        df = pd.read_csv(input_file)
        table = tabulate(df, headers='keys', tablefmt='grid', showindex=False)
        
        with open(output_file, 'w') as f:
            f.write(table)
                
        return True
    except Exception as e:
        print(f"Errore durante la formattazione: {e}")
        return False

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
    clean("metrics.csv")
    clean("metrics_table.txt")

@app.post("/functions/register")
async def register_function(req: RegisterFunctionRequest):
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = {"image": req.image, "command": req.command}

    node_name, _ = await SCHEDULING_POLICY["instance"].select_node(node_registry, req.name)

    # Ogni 3 funzioni ne preparo una "pre-warmed"
    if len(function_registry) % 3 == 1:
        await _prewarm_function_on_node(req.name, node_name)

    # Ogni 3 funzioni (con offset 2) ne preparo una "warmed"
    if len(function_registry) % 3 == 2:
        await _warmup_function_on_node(req.name, node_name)


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

    node_name = None
    execution_mode = "Cold"

    # Se c'è un'istanza warmed prende quella
    if function_name in function_state_registry:
        for n, state in function_state_registry[function_name].items():
            if state == "warmed":
                node_name = n
                execution_mode = "Warmed"
                break
    
    # Se non ci sono istanze warmed, uso la policy di scheduling
    metric_to_write = None
    if not node_name:
        selected_node, metric_to_write = await SCHEDULING_POLICY["instance"].select_node(node_registry, function_name)
        if not selected_node:
            raise HTTPException(status_code=503, detail="Nessun nodo disponibile o selezionato dalla policy.")
        
        node_name = selected_node
        # Controllo se per caso il nodo scelto è pre-warmed
        if function_name in function_state_registry and node_name in function_state_registry[function_name]:
            if function_state_registry[function_name][node_name] == "pre-warmed":
                execution_mode = "Pre-warmed"

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
            metric_to_write = { "Function": function_name, "Node": node_name, "CPU Usage % ": "---", "RAM Usage %": "---", "Policy": "Warmed Override" }

        metric_to_write["Execution Time (s)"] = f"{duration:.4f}"
        metric_to_write["Execution Mode"] = execution_mode
        write_metrics_to_csv(metric_to_write)
        format_csv_as_table()

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
    warmed_command = "python warmed_function.py"
    docker_image_and_command_warmed = f"{docker_image} {warmed_command}"
    
    container_name = f"warmed--{function_name}--{node_name}"

    try:
        docker_cmd = f"sudo docker run -d --name {container_name} {docker_image_and_command_warmed}"
        await _run_ssh_command_async(node_info, docker_cmd)
        
        if function_name not in function_state_registry:
            function_state_registry[function_name] = {}
        function_state_registry[function_name][node_name] = "warmed"
    except Exception as e:
        print(f"Errore durante il warm-up di '{function_name}' su '{node_name}': {e}")