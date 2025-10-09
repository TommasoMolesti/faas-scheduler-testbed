import os
import shutil

RESULTS_DIR = "results"

def clean_results_directory():
    """
    Removes all files and subfolders within the 'results' folder,
    if it exists. Works on any operating system.
    """

    if not os.path.isdir(RESULTS_DIR):
        print(f"The folder '{RESULTS_DIR}' does not exist. No action is required.")
        return
    
    for item_name in os.listdir(RESULTS_DIR):
        item_path = os.path.join(RESULTS_DIR, item_name)
        
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            print(f"Error while removing {item_path}. Cause: {e}")
    
    print("\n✅ Cleaning of the 'results' folder completed.")

if __name__ == "__main__":
    clean_results_directory()