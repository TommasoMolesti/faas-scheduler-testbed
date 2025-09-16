DOCKER_IMAGE_HEAVY = "tommasomolesti/custom_python_heavy:v6"
DOCKER_IMAGE_LIGHT = "tommasomolesti/custom_python_light:v1"

BASE_URL = "http://api_gateway:8000"

COMMAND = "python loop_function.py"
INVOCATIONS = 10
USER = "sshuser"
PASSWORD = "sshpassword"
SSH_NODE_SERVICE_NAMES = [
    "ssh_node_1",
    "ssh_node_2",
    "ssh_node_3",
    "ssh_node_4"
]