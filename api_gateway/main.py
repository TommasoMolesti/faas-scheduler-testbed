from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import paramiko

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service Gateway API (Docker image execution via SSH)"
)

function_registry: Dict[str, str] = {}
node_registry: Dict[str, Dict[str, Any]] = {}

class RegisterFunctionRequest(BaseModel):
    name: str
    docker_image: str

class RegisterNodeRequest(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str

class InvokeFunctionRequest(BaseModel):
    input: Optional[Any] = None

class RoundRobinNodeSelectionPolicy():
    def __init__(self):
        self.last_selected_node_index = -1
        self.node_names_cache: List[str] = []

    def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        if not nodes:
            return None

        current_node_names = list(nodes.keys())

        if current_node_names != self.node_names_cache:
            self.node_names_cache = current_node_names
            self.last_selected_node_index = -1

        if not self.node_names_cache:
            return None

        self.last_selected_node_index = (self.last_selected_node_index + 1) % len(self.node_names_cache)
        return self.node_names_cache[self.last_selected_node_index]

node_selection_policy = RoundRobinNodeSelectionPolicy()

def _run_docker_on_node(node_info: Dict[str, Any], docker_image: str) -> str:
    """
    Si connette a un nodo via SSH ed esegue un'immagine Docker.
    Restituisce l'output dello stdout del comando docker run.
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
        docker_cmd = f"docker run --rm {docker_image}"
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

@app.post("/functions/register")
def register_function(req: RegisterFunctionRequest):
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = req.docker_image
    return f"Funzione {req.name}' registrata con immagine '{req.docker_image}'."

@app.get("/functions")
def list_functions() -> Dict[str, str]:
    return function_registry

@app.get("/functions_count")
def functions_count() -> int:
    return len(function_registry)

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
    return f"Nodo '{req.name}' registrato."

@app.get("/nodes")
def list_nodes() -> Dict[str, Dict[str, Any]]:
    return {name: {k: v for k, v in info.items() if k != "password"} for name, info in node_registry.items()}

@app.get("/nodes_count")
def nodes_count() -> int:
    return len(node_registry)

@app.post("/functions/invoke/{function_name}")
def invoke_function(function_name: str, req: InvokeFunctionRequest):
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    node_name = node_selection_policy.select_node(node_registry, function_name)
    print(f"Nodo logico {node_name} ha invocato {function_name}")
    if not node_name or node_name not in node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo idoneo trovato o il nodo selezionato non è valido.")

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]

    try:
        output = _run_docker_on_node(node_info, docker_image)
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")