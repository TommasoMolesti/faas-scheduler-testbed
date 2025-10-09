import subprocess
import sys

def run_command(command, stream_output=False):
    """
    Executes a shell command. If stream_output is True, the output is
    displayed in real time. Otherwise, it is captured and displayed at the end.
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
        print(f"Error while executing the command.")