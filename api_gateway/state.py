from typing import Dict, Any, List

function_registry: Dict[str, Dict[str, Any]] = {}
node_registry: Dict[str, Dict[str, Any]] = {}
function_state_registry: Dict[str, Dict[str, str]] = {}
metrics_log: List[Dict[str, Any]] = []

CONTAINER_PREFIX = "faas-scheduler--"
RESULTS_DIR = "/results"

RAM_THRESHOLD = 90

CONCURRENCY_LIMIT = 5