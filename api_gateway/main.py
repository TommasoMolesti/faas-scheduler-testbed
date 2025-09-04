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
import matplotlib.pyplot as plt
import seaborn as sns
from dataclasses import dataclass
import uuid

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service Gateway API (Docker image execution via SSH)"
)

RESULTS_DIR = "/results"
os.makedirs(RESULTS_DIR, exist_ok=True)
function_registry: Dict[str, str] = {}
node_registry: Dict[str, Dict[str, Any]] = {}
function_state_registry: Dict[str, Dict[str, str]] = {}
metrics_log: List[Dict[str, Any]] = []
first = True
CONTAINER_PREFIX = "faas-scheduler--"

@dataclass(frozen=True)
class Mode:
    value: str
    label: str

class EXECUTION_MODES:
    COLD = Mode(value="cold", label="Cold")
    PRE_WARMED = Mode(value="pre-warmed", label="Pre-warmed")
    WARMED = Mode(value="warmed", label="Warmed")

EXECUTION_MODE_MAP = {
    mode.value: mode.label
    for mode in [EXECUTION_MODES.COLD, EXECUTION_MODES.PRE_WARMED, EXECUTION_MODES.WARMED]
}

async def _get_metrics_for_node(node_name: str, node_info: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Recupera e parsifica le metriche di CPU e RAM per un singolo nodo."""
    try:
        metrics_json = await _run_ssh_command_async(node_info, "/usr/local/bin/get_node_metrics.sh")
        metrics = json.loads(metrics_json)
        return {
            "cpu_usage": float(metrics.get("cpu_usage", float('inf'))),
            "ram_usage": float(metrics.get("ram_usage", float('inf'))),
        }
    except Exception as e:
        print(f"Attenzione: impossibile recuperare metriche per '{node_name}': {e}. Ignorato.")
        return None

class RegisterFunctionRequest(BaseModel):
    name: str
    image: str
    command: str

class RegisterNodeRequest(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str

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
                "CPU Usage %": "N/A",
                "RAM Usage %": "N/A",
                "Execution Mode": f"Round Robin - {EXECUTION_MODES.COLD.label}"
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
        Si connette a tutti i nodi in parallelo e restituisce le loro metriche
        usando la funzione di supporto _get_metrics_for_node.
        """
        tasks = [
            _get_metrics_for_node(name, info) for name, info in nodes.items()
        ]
        results = await asyncio.gather(*tasks)

        live_metrics = {name: metrics for name, metrics in zip(nodes.keys(), results) if metrics}

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
                "CPU Usage %": node_metrics[selected_node]['cpu_usage'],
                "RAM Usage %": node_metrics[selected_node]['ram_usage'],
                "Execution Mode": f"Least Used - {EXECUTION_MODES.COLD.label}"
            }
            return selected_node, metric_entry
        
        return None, None

class StaticWarmingPolicy:
    """
    Sceglie se fare warming o pre-warming in base al valore passato alla funzione in modo statico
    """
    async def apply(self, warming_type: str, function_name):
        if warming_type == EXECUTION_MODES.PRE_WARMED.value:
            node_to_prepare, _ = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, function_name)
            await _prewarm_function_on_node(function_name, node_to_prepare)
        elif warming_type == EXECUTION_MODES.WARMED.value:
            node_to_prepare, _ = await DEFAULT_SCHEDULING_POLICY.select_node(node_registry, function_name)
            await _warmup_function_on_node(function_name, node_to_prepare)

class WarmedFirstPolicy:
    """
    Seleziona un nodo dando priorità a Warmed.
    Se fallisce, delega alla PreWarmedFirstPolicy.
    """
    async def select_node(self, function_name: str):
        # Priorità 1: Cerca un'istanza 'warmed'
        if function_name in function_state_registry:
            for n, state in function_state_registry[function_name].items():
                if state == EXECUTION_MODES.WARMED.value:
                    return n, None, EXECUTION_MODES.WARMED.value

        # Priorità 2: Fallback alla policy successiva nella catena
        return await PreWarmedFirstPolicy().select_node(function_name)

class PreWarmedFirstPolicy:
    """
    Seleziona un nodo dando priorità a Pre-warmed.
    Se fallisce, delega alla DefaultColdPolicy.
    """
    async def select_node(self, function_name: str):
        # Priorità 1: Cerca un'istanza 'pre-warmed'
        if function_name in function_state_registry:
            for n, state in function_state_registry[function_name].items():
                if state == EXECUTION_MODES.PRE_WARMED.value:
                    return n, None, EXECUTION_MODES.PRE_WARMED.value

        # Priorità 2: Fallback alla policy successiva nella catena
        return await DefaultColdPolicy().select_node(function_name)

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

WARMING_TYPE = EXECUTION_MODES.COLD.value

SCHEDULING_POLICY = StaticWarmingPolicy()

NODE_SELECTION_POLICY = WarmedFirstPolicy()

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

def write_metrics_table(output_file=f"{RESULTS_DIR}/metrics_table.txt"):
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
    clean("../results/metrics_table.txt")

@app.post("/functions/register")
async def register_function(req: RegisterFunctionRequest):
    global first
    if first:
        init()
        first = False
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = {"image": req.image, "command": req.command}

    await SCHEDULING_POLICY.apply(WARMING_TYPE, req.name)

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

@app.post("/functions/invoke/{function_name}")
async def invoke_function(function_name: str):
    start_time = time.perf_counter()
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    function_details = function_registry[function_name]
    node_name, metric_to_write, execution_mode = await NODE_SELECTION_POLICY.select_node(function_name)

    node_info = node_registry[node_name]

    try:
        command_to_run = function_details["command"]
        if execution_mode == EXECUTION_MODES.WARMED.value:
            container_name = f"{CONTAINER_PREFIX}{function_name}--{node_name}"
            docker_cmd = f"sudo docker exec {container_name} {command_to_run}"
            output = await _run_ssh_command_async(node_info, docker_cmd)
        else:
            image_name = function_details["image"]
            unique_id = str(uuid.uuid4())[:8]
            container_name = f"{CONTAINER_PREFIX}{function_name}--{unique_id}"

            docker_cmd = f"sudo docker run --rm --name {container_name} {image_name} {command_to_run}"
            output = await _run_ssh_command_async(node_info, docker_cmd)

        print(f"Execution output : {output}")
        end_time = time.perf_counter()
        duration = end_time - start_time

        await write_metrics(metric_to_write, function_name, node_name, execution_mode, duration)

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
        function_state_registry[function_name][node_name] = EXECUTION_MODES.PRE_WARMED.value
    except Exception as e:
        print(f"Errore durante il pre-warm di '{function_name}' su '{node_name}': {e}")


async def _warmup_function_on_node(function_name: str, node_name: str):
    """Avvia un container in background su node_name e aggiorna lo stato a warmed"""
    if function_name not in function_registry or node_name not in node_registry:
        return

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]["image"]
    container_name = f"{CONTAINER_PREFIX}{function_name}--{node_name}"

    try:
        docker_cmd = f"sudo docker run -d --name {container_name} {docker_image} sleep infinity"
        await _run_ssh_command_async(node_info, docker_cmd)
        
        if function_name not in function_state_registry:
            function_state_registry[function_name] = {}
        function_state_registry[function_name][node_name] = EXECUTION_MODES.WARMED.value
    except Exception as e:
        print(f"Errore durante il warm-up di '{function_name}' su '{node_name}': {e}")

async def write_metrics(metric_to_write, function_name, node_name, execution_mode, duration):
    if not metric_to_write:
        metrics = await _get_metrics_for_node(node_name, node_info)
        if metrics:
            metric_to_write = {
                "Function": function_name,
                "Node": node_name,
                "CPU Usage %": metrics.get("cpu_usage"),
                "RAM Usage %": metrics.get("ram_usage"),
            }
        else:
            metric_to_write = { "Function": function_name, "Node": node_name, "CPU Usage %": "---", "RAM Usage %": "---" }

    metric_to_write["Execution Mode"] = EXECUTION_MODE_MAP.get(execution_mode, execution_mode)
    metric_to_write["Execution Time (s)"] = f"{duration:.4f}"
    metrics_log.append(metric_to_write)
    write_metrics_table()
    generate_boxplot_from_metrics()
    generate_barchart_from_metrics()

def generate_boxplot_from_metrics(output_file=f"{RESULTS_DIR}/metrics_boxplot.png"):
    """
    Genera un box plot dinamico basato sulle modalità di esecuzione presenti.
    """
    if not metrics_log:
        return

    try:
        df = pd.DataFrame(metrics_log)
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: 'Cold' if 'Cold' in mode else mode)

        master_order = [EXECUTION_MODES.COLD.label, EXECUTION_MODES.PRE_WARMED.label, EXECUTION_MODES.WARMED.label]
        present_categories = [cat for cat in master_order if cat in df['Category'].unique()]

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))

        sns.boxplot(
            x='Category',
            y='Execution Time (s)',
            data=df,
            order=present_categories,
            palette='viridis',
            hue='Category',
            legend=False,
            ax=ax
        )

        ax.set_title('Distribuzione dei Tempi di Esecuzione per Modalità', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo di Esecuzione (s)', fontsize=12)

        plt.savefig(output_file)
        plt.close(fig)

    except Exception as e:
        print(f"Errore durante la generazione del box plot: {e}")

def generate_barchart_from_metrics(output_file=f"{RESULTS_DIR}/metrics_barchart.png"):
    """
    Genera un grafico a barre dinamico basato sulle modalità di esecuzione presenti.
    """
    if not metrics_log:
        return

    try:
        df = pd.DataFrame(metrics_log)
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: EXECUTION_MODES.COLD.label if EXECUTION_MODES.COLD.label in mode else mode)

        mean_times = df.groupby('Category')['Execution Time (s)'].mean()
        master_order = [EXECUTION_MODES.COLD.label, EXECUTION_MODES.PRE_WARMED.label, EXECUTION_MODES.WARMED.label]
        present_categories = [cat for cat in master_order if cat in mean_times.index]
        mean_times = mean_times.reindex(present_categories)

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))

        mean_times.plot(kind='bar', ax=ax, color=['#FF5733', '#33C1FF', '#33FF57'], rot=0)

        ax.set_title('Confronto Tempo di Esecuzione Medio per Modalità', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo Medio di Esecuzione (s)', fontsize=12)

        for container in ax.containers:
            ax.bar_label(container, fmt='%.4f')

        plt.savefig(output_file)
        plt.close(fig)
    except Exception as e:
        print(f"Errore durante la generazione del bar chart: {e}")
