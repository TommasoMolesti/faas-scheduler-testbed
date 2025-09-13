import subprocess
import sys

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