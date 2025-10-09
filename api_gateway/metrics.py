import pandas as pd
from tabulate import tabulate
import os

import state
from models import EXECUTION_MODES, EXECUTION_MODE_MAP
from node_manager import get_metrics_for_node

def write_metrics_files():
    if not state.metrics_log:
        return

    try:
        df = pd.DataFrame(state.metrics_log)
        
        table_output_path = os.path.join(state.RESULTS_DIR, "metrics_table.txt")
        table = tabulate(df, headers='keys', tablefmt='grid', showindex=False)
        with open(table_output_path, 'w') as f:
            f.write(table)
            
        csv_output_path = os.path.join(state.RESULTS_DIR, "metrics.csv")
        df.to_csv(csv_output_path, index=False)

    except Exception as e:
        print(f"Error while writing metric files: {e}")

async def log_invocation_metrics(metric_to_write, function_name, node_name, execution_mode, duration):
    if not metric_to_write:
        node_info = state.node_registry.get(node_name)
        metrics = await get_metrics_for_node(node_name, node_info) if node_info else None
        metric_to_write = {
            "Function": function_name, "Node": node_name,
            "CPU Usage %": metrics.get("cpu_usage") if metrics else "---",
            "RAM Usage %": metrics.get("ram_usage") if metrics else "---",
        }

    metric_to_write["Execution Mode"] = EXECUTION_MODE_MAP.get(execution_mode, execution_mode)
    metric_to_write["Execution Time (s)"] = f"{duration:.4f}"
    state.metrics_log.append(metric_to_write)
    
    write_metrics_files()
