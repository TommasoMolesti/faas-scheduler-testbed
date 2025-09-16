from fastapi import FastAPI, HTTPException
import time
import uuid
import os
import pandas as pd
import asyncio

import state
import models
import policies
import node_manager
import metrics

app = FastAPI(
    title="FaaS Gateway",
    description="Function as a Service Gateway API"
)

concurrency_limiter = asyncio.Semaphore(state.CONCURRENCY_LIMIT)

DEFAULT_SCHEDULING_POLICY = policies.RoundRobinPolicy()
# DEFAULT_SCHEDULING_POLICY = policies.LeastUsedPolicy()
# DEFAULT_SCHEDULING_POLICY = policies.MostUsedPolicy()

WARMING_TYPE = models.EXECUTION_MODES.COLD.value
# WARMING_TYPE = models.EXECUTION_MODES.PRE_WARMED.value
# WARMING_TYPE = models.EXECUTION_MODES.WARMED.value

SCHEDULING_POLICY = policies.StaticWarmingPolicy()
NODE_SELECTION_POLICY = policies.WarmedFirstPolicy()

@app.on_event("startup")
async def startup_event():
    """
    All'avvio del server, controlla se esiste un file di metriche precedente,
    se si carica i dati nella sessione corrente.
    """
    csv_path = os.path.join(state.RESULTS_DIR, "metrics.csv")
    
    os.makedirs(state.RESULTS_DIR, exist_ok=True)

    if os.path.exists(csv_path):
        try:
            df_existing = pd.read_csv(csv_path)
            state.metrics_log.extend(df_existing.to_dict('records'))
        except Exception as e:
            print(f"Attenzione: impossibile leggere il file di metriche esistente. Errore: {e}")

@app.post("/functions/register")
async def register_function(req: models.RegisterFunctionRequest):
    if req.name in state.function_registry:
        raise HTTPException(status_code=400, detail=f"Funzione '{req.name}' già registrata.")
    state.function_registry[req.name] = {"image": req.image, "command": req.command}
    await SCHEDULING_POLICY.apply(WARMING_TYPE, req.name, DEFAULT_SCHEDULING_POLICY)
    return {"status": "success", "message": f"Function '{req.name}' registered."}

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
    return {"status": "success", "message": f"Node '{req.name}' registered."}

@app.post("/functions/invoke/{function_name}")
async def invoke_function(function_name: str):
    async with concurrency_limiter:        
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
            image_name = function_details["image"]

            if execution_mode == models.EXECUTION_MODES.WARMED.value:
                container_name = f"{state.CONTAINER_PREFIX}{function_name}--{node_name}"
                docker_cmd = f"sudo docker exec {container_name} {command_to_run}"
            else:
                unique_id = str(uuid.uuid4())[:8]
                container_name = f"{state.CONTAINER_PREFIX}{function_name}--{unique_id}"
                docker_cmd = f"sudo docker run --rm --name {container_name} {image_name} {command_to_run}"
            
            output = await node_manager.run_ssh_command(node_info, docker_cmd)

            if models.EXECUTION_MODES.COLD.label in execution_mode:
                try:
                    cleanup_cmd = f"sudo docker rmi {image_name}"
                    await node_manager.run_ssh_command(node_info, cleanup_cmd)
                except Exception as e:
                    print(f"Impossibile rimuovere l'immagine dal nodo '{node_name} : {e}")

        except Exception as e:
            end_time = time.perf_counter()
            duration = end_time - start_time
            print(f"Invocazione fallita dopo {duration:.4f} secondi: {e}")
            raise HTTPException(status_code=500, detail=f"Invocazione della funzione fallita: {e}")

        end_time = time.perf_counter()
        duration = end_time - start_time
        await metrics.log_invocation_metrics(metric_to_write, function_name, node_name, execution_mode, duration)