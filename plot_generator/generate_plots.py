import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

from api_gateway import models
from api_gateway import state

INPUT_CSV_PATH = os.path.join(state.RESULTS_DIR, "metrics.csv")

def generate_boxplot(df):
    """Genera un box plot dal DataFrame di metriche."""
    output_file = os.path.join(state.RESULTS_DIR, "metrics_boxplot.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: 'Cold' if 'Cold' in mode else mode)

        master_order = [models.EXECUTION_MODES.COLD, models.EXECUTION_MODES.PRE_WARMED, models.EXECUTION_MODES.WARMED]
        present_categories = [cat for cat in master_order if cat in df['Category'].unique()]

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(x='Category', y='Execution Time (s)', data=df, order=present_categories, palette='viridis', hue='Category', legend=False, ax=ax)
        ax.set_title('Distribuzione dei Tempi di Esecuzione', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
        ax.set_ylabel('Tempo di Esecuzione (s)', fontsize=12)
        plt.savefig(output_file)
        plt.close(fig)
        print(f"✅ Box plot salvato in: {output_file}")
    except Exception as e:
        print(f"❌ Errore durante la generazione del box plot: {e}")

def generate_barchart(df):
    """Genera un grafico a barre dal DataFrame di metriche."""
    output_file = os.path.join(state.RESULTS_DIR, "metrics_barchart.png")
    try:
        df['Execution Time (s)'] = pd.to_numeric(df['Execution Time (s)'])
        df['Category'] = df['Execution Mode'].apply(lambda mode: models.EXECUTION_MODES.COLD if models.EXECUTION_MODES.COLD in mode else mode)
        
        mean_times = df.groupby('Category')['Execution Time (s)'].mean()
        master_order = [models.EXECUTION_MODES.COLD, models.EXECUTION_MODES.PRE_WARMED, models.EXECUTION_MODES.WARMED]
        present_categories = [cat for cat in master_order if cat in mean_times.index]
        mean_times = mean_times.reindex(present_categories)
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))
        mean_times.plot(kind='bar', ax=ax, color=['#FF5733', '#3C8AFF', '#52FF33'], rot=0)
        ax.set_title('Confronto Tempo di Esecuzione Medio', fontsize=16)
        ax.set_xlabel('Modalità di Esecuzione', fontsize=12)
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