import os
import shutil

RESULTS_DIR = "results"

def clean_results_directory():
    """
    Rimuove tutti i file e le sottocartelle all'interno della cartella 'results',
    se questa esiste. Funziona su qualsiasi sistema operativo.
    """

    if not os.path.isdir(RESULTS_DIR):
        print(f"La cartella '{RESULTS_DIR}' non esiste. Nessuna operazione necessaria.")
        return
    
    for item_name in os.listdir(RESULTS_DIR):
        item_path = os.path.join(RESULTS_DIR, item_name)
        
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            print(f"Errore durante la rimozione di {item_path}. Causa: {e}")
    
    print("\n✅ Pulizia della cartella 'results' completata.")

if __name__ == "__main__":
    clean_results_directory()