from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import paramiko
import json
import itertools

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

def _run_ssh_command(node_info: Dict[str, Any], command: str) -> str:
    """
    Si connette a un nodo via SSH ed esegue un comando arbitrario.
    Restituisce l'output dello stdout del comando.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=node_info["host"],
            port=node_info["port"],
            username=node_info["username"],
            password=node_info["password"],
            timeout=5
        )
        _stdin, stdout, stderr = client.exec_command(command)

        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if error:
            raise Exception(f"Errore SSH durante l'esecuzione del comando '{command}': {error}")
        return output
    except paramiko.AuthenticationException:
        raise Exception("Autenticazione SSH fallita. Controlla username/password.")
    except paramiko.SSHException as e:
        raise Exception(f"Impossibile stabilire la connessione SSH: {e}")
    except Exception as e:
        raise Exception(f"Si è verificato un errore inatteso durante l'esecuzione SSH: {e}")
    finally:
        client.close()

def _run_docker_on_node(node_info: Dict[str, Any], docker_image: str) -> str:
    """
    Si connette a un nodo via SSH ed esegue un'immagine Docker.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=node_info["host"],
            port=node_info["port"],
            username=node_info["username"],
            password=node_info["password"],
            timeout=10
        )
        docker_cmd = f"sudo docker run --rm {docker_image}"
        _stdin, stdout, stderr = client.exec_command(docker_cmd)

        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if error:
            raise Exception(f"Errore del comando Docker sul nodo: {error}")
        return output
    except paramiko.AuthenticationException:
        raise Exception("Autenticazione SSH fallita. Controlla username/password.")
    except paramiko.SSHException as e:
        raise Exception(f"Impossibile stabilire la connessione SSH: {e}")
    except Exception as e:
        raise Exception(f"Si è verificato un errore inatteso durante l'esecuzione Docker: {e}")
    finally:
        client.close()

class NodeSelectionPolicy:
    """
    Classe base per la politica di selezione del nodo.
    Sovrascrivi 'select_node' per politiche personalizzate.
    Politica di default: sceglie il primo disponibile
    """
    def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        return next(iter(nodes.keys())) if nodes else None

class RoundRobinNodeSelectionPolicy(NodeSelectionPolicy):
    """
    Politica di selezione del nodo Round Robin.
    Seleziona i nodi in modo sequenziale per distribuire il carico.
    """
    def __init__(self):
        self.node_iterator = itertools.cycle([])
        self._nodes_cache = []

    def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None

        current_node_names = sorted(list(nodes.keys()))

        if current_node_names != self._nodes_cache:
            self._nodes_cache = current_node_names
            self.node_iterator = itertools.cycle(current_node_names)

        try:
            selected_node = next(self.node_iterator)
            print(f"Round Robin: Selezionato nodo '{selected_node}' per funzione '{function_name}'.")
            return selected_node
        except StopIteration:
            return None

class LeastUsedNodeSelectionPolicy(NodeSelectionPolicy):
    """
    Politica di selezione del nodo Least Used.
    Seleziona il nodo con il carico medio più basso.
    """
    def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None

        min_load = float('inf')
        selected_node_name = None

        # Prende il load_average di tutti i nodi e salva il nodo con quello più piccolo
        for node_name, node_info in nodes.items():
            try:
                # Esegue lo script get_node_metrics.sh sul nodo SSH
                metrics_json_str = _run_ssh_command(node_info, "/usr/local/bin/get_node_metrics.sh")
                metrics = json.loads(metrics_json_str)

                cpu_usage = float(metrics.get("cpu_usage", float('inf')))
                ram_usage = float(metrics.get("ram_usage", float('inf')))

                current_load = (cpu_usage + ram_usage) / 2

                if current_load < min_load:
                    min_load = current_load
                    selected_node_name = node_name
            except Exception as e:
                print(f"  Errore nel recupero metriche per il nodo '{node_name}': {e}. Questo nodo verrà ignorato.")

        if not selected_node_name:
            print("Least Used: Nessun nodo idoneo trovato (o tutti i nodi non sono raggiungibili).")
            return None

        print(f"Least Used: Selezionato nodo '{selected_node_name}'  per funzione '{function_name} con carico {min_load}.")

        return selected_node_name

SCHEDULING_POLICIES = {
    "round_robin": RoundRobinNodeSelectionPolicy(),
    "least_used": LeastUsedNodeSelectionPolicy()
}

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
def invoke_function(function_name: str, req: InvokeFunctionRequest):
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    policy_instance = SCHEDULING_POLICIES.get(req.policy_name)
    if not policy_instance:
        raise HTTPException(status_code=400, detail=f"Politica di scheduling '{req.policy_name}' non valida.")

    node_name = policy_instance.select_node(node_registry, function_name)
    
    if not node_name or node_name not in node_registry:
        raise HTTPException(status_code=503, detail=f"Nessun nodo idoneo trovato dalla politica '{req.policy_name}'.")

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]

    try:
        output = _run_docker_on_node(node_info, docker_image)
        return {
            "node": node_name,
            "docker_image": docker_image,
            "output": output,
            "policy_used": req.policy_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")
