import subprocess
import sys

IMAGE_TO_REMOVE = "tommasomolesti/custom_python_heavy:v2" 
WARMED_CONTAINER_PREFIX = "warmed--"

def run_command(command, stream_output=False):
    """
    Esegue un comando di shell. Se stream_output è True, l'output viene
    mostrato in tempo reale. Altrimenti, viene catturato e mostrato alla fine.
    """
    try:
        if stream_output:
            subprocess.run(command, shell=True, check=True)
        else:
            process = subprocess.run(
                command, 
                shell=True, 
                check=True, 
                capture_output=True, 
                text=True
            )
        
    except subprocess.CalledProcessError as e:
        print(f"Errore durante l'esecuzione del comando.")


if __name__ == "__main__":
    print("\nInizio la pulizia dell'ambiente Docker...")
    print("\n---Fermo i servizi di docker---")
    run_command("docker-compose down")

    container_ids_str = subprocess.check_output(
        f'docker ps -a --filter "name={WARMED_CONTAINER_PREFIX}" -q', 
        shell=True, 
        text=True
    ).strip()
    
    if container_ids_str:
        container_ids = container_ids_str.split('\n')
        print("\n---Fermo i container warmed---")
        run_command(f"docker stop {' '.join(container_ids)}")
        print("\n---Rimuovo i container warmed---")
        run_command(f"docker rm {' '.join(container_ids)}")

    print("\n✅ Pulizia dell'ambiente completata.")
    print("\nAvvio progetto...\n")

    run_command("docker-compose up --build", stream_output=True)

    print("\n\n✅ Test completato.")