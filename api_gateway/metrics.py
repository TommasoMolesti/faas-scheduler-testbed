import pandas as pd
from tabulate import tabulate
import matplotlib.pyplot as plt
import seaborn as sns
import os

import state
from models import EXECUTION_MODES, EXECUTION_MODE_MAP
from node_manager import get_metrics_for_node

def write_metrics_table(output_file=os.path.join(state.RESULTS_DIR, "metrics_table.txt")):
    if not state.metrics_log:
        return

    try:
        df = pd.DataFrame(state.metrics_log)
        table = tabulate(df, headers='keys', tablefmt='grid', showindex=False)

        with open(output_file, 'w') as f:
            f.write(table)
    except Exception as e:
        print(f"Errore durante la scrittura della tabella delle metriche: {e}")

def generate_boxplot(output_file=os.path.join(state.RESULTS_DIR, "metrics_boxplot.png")):
    if not state.metrics_log:
        return
    try:
        df = pd.DataFrame(state.metrics_log)
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: 'Cold' if 'Cold' in mode else mode)

        master_order = [EXECUTION_MODES.COLD.label, EXECUTION_MODES.PRE_WARMED.label, EXECUTION_MODES.WARMED.label]
        present_categories = [cat for cat in master_order if cat in df['Category'].unique()]

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(x='Category', y='Execution Time (s)', data=df, order=present_categories, palette='viridis', hue='Category', legend=False, ax=ax)
        ax.set_title('Distribuzione dei Tempi di Esecuzione', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo di Esecuzione (s)', fontsize=12)
        plt.savefig(output_file)
        plt.close(fig)
    except Exception as e:
        print(f"Errore durante la generazione del box plot: {e}")

def generate_barchart(output_file=os.path.join(state.RESULTS_DIR, "metrics_barchart.png")):
    if not state.metrics_log:
        return
    try:
        df = pd.DataFrame(state.metrics_log)
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: EXECUTION_MODES.COLD.label if EXECUTION_MODES.COLD.label in mode else mode)
        mean_times = df.groupby('Category')['Execution Time (s)'].mean().reindex([cat for cat in [EXECUTION_MODES.COLD.label, EXECUTION_MODES.PRE_WARMED.label, EXECUTION_MODES.WARMED.label] if cat in df['Category'].unique()])
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))
        mean_times.plot(kind='bar', ax=ax, color=['#FF5733', '#33C1FF', '#33FF57'], rot=0)
        ax.set_title('Confronto Tempo di Esecuzione Medio', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo Medio di Esecuzione (s)', fontsize=12)
        ax.bar_label(ax.containers[0], fmt='%.4f')
        plt.savefig(output_file)
        plt.close(fig)
    except Exception as e:
        print(f"Errore durante la generazione del bar chart: {e}")

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
    
    write_metrics_table()
    generate_boxplot()
    generate_barchart()