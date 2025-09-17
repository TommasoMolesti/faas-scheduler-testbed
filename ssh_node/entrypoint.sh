#!/bin/bash
# ssh_node/entrypoint.sh

# Credenziali utente SSH
USER="sshuser"
PASSWORD="sshpassword"

# 1. Crea l'utente SSH se non esiste e imposta la password
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER"
fi
echo "$USER:$PASSWORD" | chpasswd

# 2. Configurazione SSH
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

# 3. Aggiungi l'utente al gruppo 'docker'
usermod -aG docker "$USER"

# Workaround per sudo
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/docker" > /etc/sudoers.d/docker-access
chmod 0440 /etc/sudoers.d/docker-access

# 4. Crea lo script per recuperare le metriche (compatibile con cgroups v1 e v2)
cat << 'EOF' > /usr/local/bin/get_node_metrics.sh
#!/bin/bash

# --- Rilevamento automatico della versione di Cgroups ---

# Se questo file esiste, stiamo usando cgroups v2
if [ -f "/sys/fs/cgroup/cpu.stat" ]; then
    # Calcolo CPU
    # In v2, l'unità di misura è in microsecondi ('usage_usec')
    cpu_usage_start=$(grep 'usage_usec' /sys/fs/cgroup/cpu.stat | awk '{print $2}')
    time_start=$(date +%s%N)
    sleep 0.1
    cpu_usage_end=$(grep 'usage_usec' /sys/fs/cgroup/cpu.stat | awk '{print $2}')
    time_end=$(date +%s%N)

    cpu_delta=$((cpu_usage_end - cpu_usage_start))   # Delta in microsecondi
    time_delta=$((time_end - time_start))           # Delta in nanosecondi

    # Convertiamo il delta della CPU in nanosecondi per avere la stessa unità di misura del tempo
    # e poi calcoliamo la percentuale.
    cpu_usage=$(awk -v cpu_delta_us="$cpu_delta" -v time_delta_ns="$time_delta" \
        'BEGIN { printf "%.2f", ((cpu_delta_us * 1000) / time_delta_ns) * 100 }')

    # Calcolo RAM
    # In v2, i file si chiamano 'memory.current' e 'memory.max'
    mem_usage_bytes=$(cat /sys/fs/cgroup/memory.current)
    mem_limit_bytes=$(cat /sys/fs/cgroup/memory.max)

    # Se non c'è limite, il file 'memory.max' contiene la stringa "max"
    if [ "$mem_limit_bytes" = "max" ]; then
        ram_usage="0.00"
    else
        ram_usage=$(awk -v used="$mem_usage_bytes" -v limit="$mem_limit_bytes" \
            'BEGIN { if (limit > 0) printf "%.2f", (used / limit) * 100; else print "0.00" }')
    fi
else
    # --- (Fallback) ---

    # Calcolo CPU
    # In v1, l'unità è in nanosecondi ('cpuacct.usage')
    cpu_usage_start=$(cat /sys/fs/cgroup/cpuacct/cpuacct.usage)
    time_start=$(date +%s%N)
    sleep 0.1
    cpu_usage_end=$(cat /sys/fs/cgroup/cpuacct/cpuacct.usage)
    time_end=$(date +%s%N)
    
    cpu_delta=$((cpu_usage_end - cpu_usage_start))
    time_delta=$((time_end - time_start))
    
    cpu_usage=$(awk -v cpu_delta_ns="$cpu_delta" -v time_delta_ns="$time_delta" \
        'BEGIN { printf "%.2f", (cpu_delta_ns / time_delta_ns) * 100 }')

    # Calcolo RAM
    # In v1, i file si chiamano 'memory.usage_in_bytes' e 'memory.limit_in_bytes'
    mem_usage_bytes=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes)
    mem_limit_bytes=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)
    
    ram_usage=$(awk -v used="$mem_usage_bytes" -v limit="$mem_limit_bytes" \
        'BEGIN { if (limit > 0) printf "%.2f", (used / limit) * 100; else print "0.00" }')
fi

# --- Output JSON ---
echo "{"
echo "  \"cpu_usage\": \"$cpu_usage\","
echo "  \"ram_usage\": \"$ram_usage\""
echo "}"
EOF

# Rendi lo script eseguibile
chmod +x /usr/local/bin/get_node_metrics.sh

echo "Nodo SSH pronto"

# 5. Avvia il servizio SSH in foreground
exec /usr/sbin/sshd -D