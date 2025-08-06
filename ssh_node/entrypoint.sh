#!/bin/bash
# ssh_node/entrypoint.sh

# Credenziali utente SSH
USER="sshuser"
PASSWORD="sshpassword" # !!! CAMBIARE QUESTA PASSWORD IN UNA FORTE PER AMBIENTI DI PRODUZIONE !!!

# 1. Crea l'utente SSH se non esiste e imposta la password
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER"
fi
echo "$USER:$PASSWORD" | chpasswd

# 2. Configurazione SSH per permettere l'accesso tramite password
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

# 3. Aggiungi l'utente SSH al gruppo 'docker'
# Questo permette all'utente di interagire con il socket Docker dell'host.
usermod -aG docker "$USER"

# --- INIZIO: Modifica per workaround temporaneo con sudo (SOLO PER TEST) ---
# Permetti all'utente SSH di eseguire comandi docker con sudo senza password
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/docker" > /etc/sudoers.d/docker-access
chmod 0440 /etc/sudoers.d/docker-access
# --- FINE: Modifica per workaround temporaneo con sudo ---

# 4. Crea lo script per recuperare le metriche del nodo
# Questo script verrà eseguito dal gateway via SSH
cat << 'EOF' > /usr/local/bin/get_node_metrics.sh
#!/bin/bash
# Script per recuperare le metriche del nodo

# Ottieni il carico medio (load average) dell'ultimo minuto
LOAD_AVERAGE=$(uptime | awk -F'load average: ' '{print $2}' | awk '{print $3}')

# Ottieni la memoria RAM totale e disponibile (in KB)
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_AVAILABLE_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
MEM_USED_KB=$((MEM_TOTAL_KB - MEM_AVAILABLE_KB))

# Formatta l'output come JSON
echo "{\"load_average\": $LOAD_AVERAGE, \"mem_total_kb\": $MEM_TOTAL_KB, \"mem_used_kb\": $MEM_USED_KB, \"mem_available_kb\": $MEM_AVAILABLE_KB}"
EOF

# Rendi lo script eseguibile
chmod +x /usr/local/bin/get_node_metrics.sh

echo "Nodo SSH pronto"

# 5. Avvia il servizio SSH in foreground
# Questo sarà il processo principale del container e lo manterrà in vita.
exec /usr/sbin/sshd -D
