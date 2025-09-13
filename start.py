import subprocess

from api_gateway import state
from client import constants
import utils

if __name__ == "__main__":
    print("\nInizio la pulizia dell'ambiente Docker...")
    print("\n---Fermo i servizi di docker---")
    utils.run_command("docker-compose down")

    container_ids_str = subprocess.check_output(
        f'docker ps -a --filter "name={state.CONTAINER_PREFIX}" -q', 
        shell=True, 
        text=True
    ).strip()
    
    if container_ids_str:
        container_ids = container_ids_str.split('\n')
        print("\n---Fermo i container warmed---")
        utils.run_command(f"docker stop {' '.join(container_ids)}")
        print("\n---Rimuovo i container warmed---")
        utils.run_command(f"docker rm {' '.join(container_ids)}")

    utils.run_command(f"docker rmi {constants.DOCKER_IMAGE_HEAVY}")
    utils.run_command(f"docker rmi {constants.DOCKER_IMAGE_LIGHT}")

    print("\n✅ Pulizia dell'ambiente completata.")
    print("\nAvvio progetto...\n")

    utils.run_command("docker-compose up --build", stream_output=True)

    print("\n\n✅ Test completato.")