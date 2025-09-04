from typing import Dict, Any, Optional
import itertools
import asyncio
from fastapi import HTTPException

import state
from models import EXECUTION_MODES
from node_manager import get_metrics_for_node, prewarm_function_on_node, warmup_function_on_node


class RoundRobinPolicy:
    def __init__(self):
        self.node_iterator = itertools.cycle([])
        self._nodes_cache = []

    async def select_node(self, nodes: Dict[str, Any], function_name: str) -> Optional[tuple]:
        if not nodes:
            return None, None
        current_node_names = sorted(list(nodes.keys()))
        if current_node_names != self._nodes_cache:
            self._nodes_cache = current_node_names
            self.node_iterator = itertools.cycle(current_node_names)
        try:
            selected_node = next(self.node_iterator)
            metric_entry = {"Function": function_name, "Node": selected_node, "CPU Usage %": "N/A", "RAM Usage %": "N/A", "Execution Mode": f"Round Robin - {EXECUTION_MODES.COLD.label}"}
            return selected_node, metric_entry
        except StopIteration:
            return None, None

class LeastUsedPolicy:
    async def _get_all_node_metrics(self, nodes: Dict[str, Any]) -> Dict[str, Any]:
        tasks = [get_metrics_for_node(name, info) for name, info in nodes.items()]
        results = await asyncio.gather(*tasks)
        return {name: metrics for name, metrics in zip(nodes.keys(), results) if metrics}

    async def select_node(self, nodes: Dict[str, Any], function_name: str) -> Optional[tuple]:
        if not nodes:
            return None, None
        node_metrics = await self._get_all_node_metrics(nodes)
        if not node_metrics:
            print("Least Used: Impossibile recuperare le metriche da alcun nodo.")
            return None, None
        
        selected_node = min(node_metrics, key=lambda n: (node_metrics[n]["cpu_usage"] + node_metrics[n]["ram_usage"]) / 2)
        
        if selected_node:
            metric_entry = {"Function": function_name, "Node": selected_node, "CPU Usage %": node_metrics[selected_node]['cpu_usage'], "RAM Usage %": node_metrics[selected_node]['ram_usage'], "Execution Mode": f"Least Used - {EXECUTION_MODES.COLD.label}"}
            return selected_node, metric_entry
        return None, None

class StaticWarmingPolicy:
    async def apply(self, warming_type: str, function_name: str, scheduler):
        if warming_type == EXECUTION_MODES.PRE_WARMED.value:
            node_to_prepare, _ = await scheduler.select_node(state.node_registry, function_name)
            if node_to_prepare: await prewarm_function_on_node(function_name, node_to_prepare)
        elif warming_type == EXECUTION_MODES.WARMED.value:
            node_to_prepare, _ = await scheduler.select_node(state.node_registry, function_name)
            if node_to_prepare: await warmup_function_on_node(function_name, node_to_prepare)

class WarmedFirstPolicy:
    async def select_node(self, function_name: str, scheduler):
        if function_name in state.function_state_registry:
            for n, s in state.function_state_registry[function_name].items():
                if s == EXECUTION_MODES.WARMED.value:
                    return n, None, EXECUTION_MODES.WARMED.value
        return await PreWarmedFirstPolicy().select_node(function_name, scheduler)

class PreWarmedFirstPolicy:
    async def select_node(self, function_name: str, scheduler):
        if function_name in state.function_state_registry:
            for n, s in state.function_state_registry[function_name].items():
                if s == EXECUTION_MODES.PRE_WARMED.value:
                    return n, None, EXECUTION_MODES.PRE_WARMED.value
        return await DefaultColdPolicy().select_node(function_name, scheduler)

class DefaultColdPolicy:
    async def select_node(self, function_name: str, scheduler):
        node_name, metric_to_write = await scheduler.select_node(state.node_registry, function_name)
        if not node_name:
            raise HTTPException(status_code=503, detail="Nessun nodo disponibile.")
        execution_mode = metric_to_write.get("Execution Mode", "Unknown")
        return node_name, metric_to_write, execution_mode