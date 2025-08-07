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
            result = await conn.run(command, check=True)
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
            return None

        current_node_names = sorted(list(nodes.keys()))

        if current_node_names != self._nodes_cache:
            self._nodes_cache = current_node_names
            self.node_iterator = itertools.cycle(current_node_names)

        try:
            selected_node = next(self.node_iterator)
            metrics_data = {
                "Function": function_name,
                "Node": selected_node,
                "CPU Usage % ": "None",
                "RAM Usage %": "None",
                "Policy": "Round Robin"
            }

            write_metrics_to_csv(metrics_data)
            return selected_node
        except StopIteration:
            return None

class LeastUsedNodeSelectionPolicy(NodeSelectionPolicy):
    """
    Politica di selezione del nodo Least Used.
    Seleziona il nodo con il carico medio più basso.
    """
    def __init__(self):
        self._node_metrics_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_last_updated: float = 0.0
        self._cache_ttl: int = 0 # 1 secondo di TTL nella cache

    async def _update_metrics_cache(self, nodes: Dict[str, Dict[str, Any]]):        
        tasks = []
        for node_name, node_info in nodes.items():
            task = _run_ssh_command_async(node_info, "/usr/local/bin/get_node_metrics.sh")
            tasks.append((node_name, task))

        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        
        temp_cache = {}
        for (node_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                print(f"  Errore nel recupero metriche per '{node_name}': {result}. Ignorato.")
            else:
                try:
                    metrics = json.loads(result)
                    temp_cache[node_name] = {
                        "cpu_usage": float(metrics.get("cpu_usage", float('inf'))),
                        "ram_usage": float(metrics.get("ram_usage", float('inf'))),
                    }
                except (json.JSONDecodeError, TypeError):
                    print(f"Errore nel parsing del JSON da '{node_name}'.")

        self._node_metrics_cache = temp_cache
        self._cache_last_updated = time.time()
        
        self._cache_last_updated = time.time()

    async def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None

        if (time.time() - self._cache_last_updated) > self._cache_ttl:
            await self._update_metrics_cache(nodes)
        
        if not self._node_metrics_cache:
            print("Least Used: Cache delle metriche vuota, nessun nodo selezionabile.")
            return None

        min_load = float('inf')
        selected_node = None
        
        # Sceglie il nodo basandosi sulla cache
        for node_name, metrics in self._node_metrics_cache.items():
            current_load = (metrics["cpu_usage"] + metrics["ram_usage"]) / 2
            if current_load < min_load:
                min_load = current_load
                selected_node = node_name
        
        if selected_node:
            metrics_data = {
                "Function": function_name,
                "Node": selected_node,
                "CPU Usage % ": self._node_metrics_cache[selected_node]['cpu_usage'],
                "RAM Usage %": self._node_metrics_cache[selected_node]['ram_usage'],
                "Policy": "Least Used"
            }
            write_metrics_to_csv(metrics_data)
        
        return selected_node

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
    "least_used": LeastUsedNodeSelectionPolicy()
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
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    policy_instance = SCHEDULING_POLICIES.get(req.policy_name)
    if not policy_instance:
        raise HTTPException(status_code=400, detail=f"Politica di scheduling '{req.policy_name}' non valida.")

    node_name = await policy_instance.select_node(node_registry, function_name)
    format_csv_as_table()
    
    if not node_name or node_name not in node_registry:
        raise HTTPException(status_code=503, detail=f"Nessun nodo idoneo trovato dalla politica '{req.policy_name}'.")

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]

    try:
        output = await _run_docker_on_node_async(node_info, docker_image)
        return {
            "node": node_name,
            "docker_image": docker_image,
            "output": output,
            "policy_used": req.policy_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")
