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
# Usando un 'heredoc' senza virgolette sul delimitatore 'EOF'
# e facendo l'escape dei caratteri '$' che non devono essere interpretati ora.
cat << EOF > /usr/local/bin/get_node_metrics.sh
#!/bin/bash

# CPU Usage
cpu_usage=\$(grep 'cpu ' /proc/stat | awk '{usage=(\$2+\$4)*100/(\$2+\$4+\$5)} END {print usage}')

# RAM Usage
ram_total=\$(free | awk '/Mem:/ {print \$2}')
ram_used=\$(free | awk '/Mem:/ {print \$3}')
ram_usage=\$(awk "BEGIN {print (\$ram_used/\$ram_total)*100}")

# JSON output
echo "{"
echo "  \\"cpu_usage\\": \\"\$cpu_usage\\","
echo "  \\"ram_usage\\": \\"\$ram_usage\\""
echo "}"
EOF

# Rendi lo script eseguibile
chmod +x /usr/local/bin/get_node_metrics.sh

echo "Nodo SSH pronto"

# 5. Avvia il servizio SSH in foreground
# Questo sarà il processo principale del container e lo manterrà in vita.
exec /usr/sbin/sshd -D
