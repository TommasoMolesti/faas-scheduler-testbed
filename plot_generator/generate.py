import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

RESULTS_DIR = "/results"
INPUT_CSV_PATH = os.path.join(RESULTS_DIR, "metrics.csv")

def generate_boxplot(df, function_name, order, color_map):
    """Genera un box plot per una specifica funzione, usando un ordine e colori definiti."""
    output_file = os.path.join(RESULTS_DIR, f"metrics_boxplot_{function_name}.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 7))
        
        sns.boxplot(x='Execution Mode', y='Execution Time (s)', data=df, 
                    palette=color_map,
                    order=order,
                    hue='Execution Mode', legend=False, ax=ax)
        
        ax.set_title(f'Distribuzione Tempi di Esecuzione - Funzione: {function_name}', fontsize=16, pad=20)
        ax.set_xlabel('Strategia di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo di Esecuzione (s)', fontsize=12)
        fig.subplots_adjust(bottom=0.2) 

        plt.savefig(output_file)
        plt.close(fig)
        print(f"✅ Box plot salvato in: {output_file}")
    except Exception as e:
        print(f"❌ Errore durante la generazione del box plot per {function_name}: {e}")

def generate_barchart(df, function_name, order, color_map):
    """Genera un grafico a barre per una specifica funzione, usando un ordine e colori definiti."""
    output_file = os.path.join(RESULTS_DIR, f"metrics_barchart_{function_name}.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        mean_times = df.groupby('Execution Mode')['Execution Time (s)'].mean()
        
        mean_times = mean_times.reindex(order)
        
        valid_order = [m for m in order if m in mean_times.index]
        bar_colors = [color_map[mode] for mode in valid_order]
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 7))
        
        mean_times.loc[valid_order].plot(kind='bar', ax=ax, color=bar_colors, rot=0)
        
        ax.set_title(f'Confronto Tempo Medio di Esecuzione - Funzione: {function_name}', fontsize=16, pad=20)
        ax.set_xlabel('Strategia di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo Medio di Esecuzione (s)', fontsize=12)
        
        if hasattr(ax, 'containers') and ax.containers:
             ax.bar_label(ax.containers[0], fmt='%.4f')
             
        plt.savefig(output_file)
        plt.close(fig)
        print(f"✅ Bar chart salvato in: {output_file}")
    except Exception as e:
        print(f"❌ Errore durante la generazione del bar chart per {function_name}: {e}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_CSV_PATH):
        print(f"❌ Errore: File di dati non trovato in '{INPUT_CSV_PATH}'.")
    else:
        print(f"Leggo i dati da '{INPUT_CSV_PATH}'...")
        dataframe = pd.read_csv(INPUT_CSV_PATH)
        
        all_modes = dataframe['Execution Mode'].unique()
        
        ordered_modes = sorted(all_modes)
        
        palette = sns.color_palette('viridis', n_colors=len(ordered_modes))
        color_map = {mode: color for mode, color in zip(ordered_modes, palette)}
        
        unique_functions = dataframe['Function'].unique()

        for func_name in unique_functions:
            df_func_filtered = dataframe[dataframe['Function'] == func_name]
            
            if not df_func_filtered.empty:
                generate_boxplot(df_func_filtered, func_name, ordered_modes, color_map)
                generate_barchart(df_func_filtered, func_name, ordered_modes, color_map)
            else:
                print(f"ℹ️ Nessun dato trovato per la funzione '{func_name}'. Grafici saltati.")