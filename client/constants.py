DOCKER_IMAGE_HEAVY = "tommasomolesti/custom_python_heavy:v8"
DOCKER_IMAGE_LIGHT = "tommasomolesti/custom_python_light:v3"

BASE_URL = "http://api_gateway:8000"

COMMAND_LIGHT = "python3 loop_function.py 15000"
COMMAND_HEAVY = "python3 loop_function.py 20000"
INVOCATIONS = 100
USER = "sshuser"
PASSWORD = "sshpassword"
SSH_NODE_SERVICE_NAMES = [
    "ssh_node_1",
    "ssh_node_2",
    "ssh_node_3",
    "ssh_node_4"
]