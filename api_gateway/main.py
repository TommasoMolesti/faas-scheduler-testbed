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

class RegisterFunctionRequest(BaseModel):
    name: str = Field(..., description="Il nome univoco della funzione da registrare.")
    docker_image: str = Field(..., description="Il nome dell'immagine Docker da associare alla funzione (es. 'python:3.11-slim', 'ubuntu:latest').")

class RegisterNodeRequest(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str

class InvokeFunctionRequest(BaseModel):
    input: Optional[Any] = None
    policy_name: str = Field("round_robin", description="Nome della politica di scheduling da utilizzare (es. 'round_robin', 'least_loaded').")
    execution_mode: Optional[str] = None

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

class WarmedFirstPolicy(NodeSelectionPolicy):
    """
    Politica che cerca prima un container 'warmed'.
    Se non lo trova, esegue un fallback alla politica 'least_used' per un cold start.
    """
    def __init__(self, fallback_policy: NodeSelectionPolicy):
        self._fallback_policy = fallback_policy

    async def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> tuple[Optional[str], Optional[Dict]]:
        for node_name, node_info in nodes.items():
            container_name = f"warmed--{function_name}--{node_name}"
            check_cmd = f"sudo docker ps -q -f name=^{container_name}$"
            
            try:
                running_container_id = await _run_ssh_command_async(node_info, check_cmd)
                if running_container_id:
                    metric_entry = {
                        "Function": function_name,
                        "Node": node_name,
                        "CPU Usage % ": "WARMED",
                        "RAM Usage %": "WARMED",
                        "Policy": "Warmed First"
                    }
                    return node_name, metric_entry
            except Exception:
                continue

        print("Nessun container 'warmed' trovato. Eseguo fallback a 'least_used' per un cold start.")
        return await self._fallback_policy.select_node(nodes, function_name)


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

SCHEDULING_POLICIES = {
    "round_robin": RoundRobinNodeSelectionPolicy(),
    "least_used": LeastUsedNodeSelectionPolicy(),
    "warmed_first": WarmedFirstPolicy(fallback_policy=LeastUsedNodeSelectionPolicy())
}

@app.post("/init")
def init():
    clean("metrics.csv")
    clean("metrics_table.txt")

@app.post("/functions/register")
def register_function(req: RegisterFunctionRequest):
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = req.docker_image

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

    policy_instance = SCHEDULING_POLICIES.get(req.policy_name)
    if not policy_instance:
        raise HTTPException(status_code=400, detail=f"Politica di scheduling '{req.policy_name}' non valida.")

    node_name, metric_to_write = await policy_instance.select_node(node_registry, function_name)
    
    if not node_name or node_name not in node_registry:
        raise HTTPException(status_code=503, detail=f"Nessun nodo idoneo trovato dalla politica '{req.policy_name}'.")

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]

    try:
        is_warmed_execution = metric_to_write and metric_to_write.get("CPU Usage % ") == "WARMED"

        if is_warmed_execution:
            container_name = f"warmed--{function_name}--{node_name}"
            output = await _run_ssh_command_async(node_info, f"sudo docker logs {container_name}")
        else:
            output = await _run_docker_on_node_async(node_info, docker_image)
        
        end_time = time.perf_counter()
        duration = end_time - start_time

        if metric_to_write:
            if req.execution_mode == "pre-warmed" and not is_warmed_execution:
                metric_to_write["Policy"] = "Least Used (Pre-warmed)"
            metric_to_write["Execution Time (s)"] = f"{duration:.4f}"
            write_metrics_to_csv(metric_to_write)
        
        format_csv_as_table()

        return {
            "node": node_name,
            "docker_image": docker_image,
            "output": output,
            "policy_used": req.policy_name,
            "execution_type": "warmed" if is_warmed_execution else "cold",
            "duration_seconds": duration
        }
    except Exception as e:
        end_time = time.perf_counter()
        duration = end_time - start_time
        print(f"Invocazione fallita dopo {duration:.4f} secondi.")
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")

@app.post("/functions/prewarm")
async def prewarm_function(function_name: str, node_name: str):
    """
    Esegue un 'docker pull' dell'immagine di una funzione su un nodo specifico.
    """
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail="Funzione non trovata.")
    if node_name not in node_registry:
        raise HTTPException(status_code=404, detail="Nodo non trovato.")

    node_info = node_registry[node_name]
    docker_image_name = function_registry[function_name].split(' ')[0]
    
    try:
        output = await _run_ssh_command_async(node_info, f"sudo docker pull {docker_image_name}")
        return {"status": "success", "node": node_name, "image": docker_image_name, "output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/functions/warmup")
async def warmup_function(function_name: str, node_name: str):
    """
    Avvia un'istanza di una funzione in background (detached) su un nodo specifico,
    simulando un container 'warmed'.
    """
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail="Funzione non trovata.")
    if node_name not in node_registry:
        raise HTTPException(status_code=404, detail="Nodo non trovato.")

    node_info = node_registry[node_name]
    docker_image_and_command = function_registry[function_name]
    container_name = f"warmed--{function_name}--{node_name}"

    await _run_ssh_command_async(node_info, f"sudo docker rm -f {container_name}")

    docker_cmd = f"sudo docker run -d --name {container_name} {docker_image_and_command}"
    
    try:
        container_id = await _run_ssh_command_async(node_info, docker_cmd)
        return {"status": "warming_up", "node": node_name, "container_name": container_name, "container_id": container_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))