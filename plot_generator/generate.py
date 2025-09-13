import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

RESULTS_DIR = "/results"
INPUT_CSV_PATH = os.path.join(RESULTS_DIR, "metrics.csv")

def generate_boxplot(df):
    """Genera un box plot dal DataFrame di metriche."""
    output_file = os.path.join(RESULTS_DIR, "metrics_boxplot.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 7))
        
        sns.boxplot(x='Execution Mode', y='Execution Time (s)', data=df, palette='viridis', 
                            hue='Execution Mode', legend=False, ax=ax)        
        ax.set_title('Distribuzione dei Tempi di Esecuzione per Strategia', fontsize=16)
        ax.set_xlabel('Strategia di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo di Esecuzione (s)', fontsize=12)
        plt.savefig(output_file)
        plt.close(fig)
        print(f"✅ Box plot salvato in: {output_file}")
    except Exception as e:
        print(f"❌ Errore durante la generazione del box plot: {e}")

def generate_barchart(df):
    """Genera un grafico a barre dal DataFrame di metriche."""
    output_file = os.path.join(RESULTS_DIR, "metrics_barchart.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        
        mean_times = df.groupby('Execution Mode')['Execution Time (s)'].mean()
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 7))
        
        mean_times.plot(kind='bar', ax=ax, color=sns.color_palette('viridis', n_colors=len(mean_times)), rot=0)
        
        ax.set_title('Confronto Tempo di Esecuzione Medio per Strategia', fontsize=16)
        ax.set_xlabel('Strategia di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo Medio di Esecuzione (s)', fontsize=12)
        ax.bar_label(ax.containers[0], fmt='%.4f')
        plt.savefig(output_file)
        plt.close(fig)
        print(f"✅ Bar chart salvato in: {output_file}")
    except Exception as e:
        print(f"❌ Errore durante la generazione del bar chart: {e}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_CSV_PATH):
        print(f"❌ Errore: File di dati non trovato in '{INPUT_CSV_PATH}'.")
        print("Assicurati di aver eseguito prima il test per generare il file metrics.csv.")
    else:
        print(f"Leggo i dati da '{INPUT_CSV_PATH}'...")
        dataframe = pd.read_csv(INPUT_CSV_PATH)
        generate_boxplot(dataframe)
        generate_barchart(dataframe)