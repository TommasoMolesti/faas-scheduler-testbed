from fastapi import FastAPI, HTTPException
import time
import uuid
import os

import state
import models
import policies
import node_manager
import metrics

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service Gateway API"
)

DEFAULT_SCHEDULING_POLICY = policies.LeastUsedPolicy()
WARMING_TYPE = models.EXECUTION_MODES.COLD.value
SCHEDULING_POLICY = policies.StaticWarmingPolicy()
NODE_SELECTION_POLICY = policies.WarmedFirstPolicy()

@app.on_event("startup")
async def startup_event():
    os.makedirs(state.RESULTS_DIR, exist_ok=True)
    metrics_file_path = os.path.join(state.RESULTS_DIR, "metrics_table.txt")
    if os.path.exists(metrics_file_path):
        try:
            with open(metrics_file_path, 'w') as f: f.truncate(0)
        except Exception as e:
            print(f"Errore durante la pulizia del file '{metrics_file_path}': {e}")

@app.post("/functions/register")
async def register_function(req: models.RegisterFunctionRequest):
    if req.name in state.function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    state.function_registry[req.name] = {"image": req.image, "command": req.command}
    await SCHEDULING_POLICY.apply(WARMING_TYPE, req.name, DEFAULT_SCHEDULING_POLICY)

@app.post("/nodes/register")
def register_node(req: models.RegisterNodeRequest):
    if req.name in state.node_registry:
        raise HTTPException(status_code=400, detail=f"Nodo '{req.name}' già registrato.")
    state.node_registry[req.name] = {
        "host": req.host,
        "port": req.port,
        "username": req.username,
        "password": req.password
    }

@app.post("/functions/invoke/{function_name}")
async def invoke_function(function_name: str):
    start_time = time.perf_counter()
    if function_name not in state.function_registry:
        raise HTTPException(status_code=404, detail=f"Funzione '{function_name}' non trovata.")
    if not state.node_registry:
        raise HTTPException(status_code=503, detail="Nessun nodo disponibile per l'esecuzione.")

    function_details = state.function_registry[function_name]
    
    try:
        node_name, metric_to_write, execution_mode = await NODE_SELECTION_POLICY.select_node(function_name, DEFAULT_SCHEDULING_POLICY)
        node_info = state.node_registry[node_name]
        command_to_run = function_details["command"]

        if execution_mode == models.EXECUTION_MODES.WARMED.value:
            container_name = f"{state.CONTAINER_PREFIX}{function_name}--{node_name}"
            docker_cmd = f"sudo docker exec {container_name} {command_to_run}"
        else:
            image_name = function_details["image"]
            unique_id = str(uuid.uuid4())[:8]
            container_name = f"{state.CONTAINER_PREFIX}{function_name}--{unique_id}"
            docker_cmd = f"sudo docker run --rm --name {container_name} {image_name} {command_to_run}"
        
        output = await node_manager.run_ssh_command(node_info, docker_cmd)
        print(f"Execution output : {output}")

    except Exception as e:
        end_time = time.perf_counter()
        duration = end_time - start_time
        print(f"Invocazione fallita dopo {duration:.4f} secondi: {e}")
        raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")

    end_time = time.perf_counter()
    duration = end_time - start_time
    await metrics.log_invocation_metrics(metric_to_write, function_name, node_name, execution_mode, duration)