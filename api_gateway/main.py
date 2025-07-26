from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import paramiko

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service gateway API (Docker image execution via SSH)",
    version="2.0.0"
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

class NodeSelectionPolicy:
    def select_node(self, nodes: Dict[str, Dict[str, Any]], function_name: str) -> Optional[str]:
        return next(iter(nodes.keys())) if nodes else None

node_selection_policy = NodeSelectionPolicy()

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
        # Esegue il comando Docker sul nodo remoto
        _stdin, stdout, stderr = client.exec_command(docker_cmd)

        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if error:
            # Se c'è un errore sullo stderr di Docker, lo solleva come eccezione
            raise Exception(f"Errore del comando Docker sul nodo: {error}")
        return output
    except paramiko.AuthenticationException:
        raise Exception("Autenticazione SSH fallita. Controlla username/password.")
    except paramiko.SSHException as e:
        raise Exception(f"Impossibile stabilire la connessione SSH: {e}")
    except Exception as e:
        # Cattura qualsiasi altro errore imprevisto
        raise Exception(f"Si è verificato un errore inatteso durante l'esecuzione Docker: {e}")
    finally:
        # Assicurati che la connessione SSH sia sempre chiusa
        client.close()

@app.post("/functions/register")
def register_function(req: RegisterFunctionRequest):
    if req.name in function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    function_registry[req.name] = req.docker_image
    return {"message": f"Funzione '{req.name}' registrata con immagine '{req.docker_image}'."}

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
    return {"message": f"Nodo '{req.name}' registrato."}

@app.get("/nodes")
# Lista dei nodi registrati
def list_nodes() -> Dict[str, Dict[str, Any]]:
    return {name: {k: v for k, v in info.items() if k != "password"} for name, info in node_registry.items()}

@app.post("/functions/invoke/{function_name}")
def invoke_function(function_name: str, req: InvokeFunctionRequest):
    if function_name not in function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    # Seleziono un nodo
    node_name = node_selection_policy.select_node(node_registry, function_name)
    if not node_name or node_name not in node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo idoneo trovato o il nodo selezionato non è valido.")

    node_info = node_registry[node_name]
    docker_image = function_registry[function_name]

    try:
        output = _run_docker_on_node(node_info, docker_image)
        return {
            "node": node_name,
            "docker_image": docker_image,
            "output": output
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")