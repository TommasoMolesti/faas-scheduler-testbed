#!/bin/bash
# ssh_node/entrypoint.sh

# SSH user credentials
USER="sshuser"
PASSWORD="sshpassword"

# 1. Create the SSH user if it does not exist and set the password
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER"
fi
echo "$USER:$PASSWORD" | chpasswd

# 2. SSH configuration
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

# 3. Add the user to the ‘docker’ group
usermod -aG docker "$USER"

# Workaround for sudo
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/docker" > /etc/sudoers.d/docker-access
chmod 0440 /etc/sudoers.d/docker-access

# 4. Create the script to retrieve metrics (compatible with cgroups v1 and v2)
cat << 'EOF' > /usr/local/bin/get_node_metrics.sh
#!/bin/bash

# --- Automatic detection of Cgroups version ---

# If this file exists, we are using cgroups v2.
if [ -f "/sys/fs/cgroup/cpu.stat" ]; then
    # CPU calculation
    # In v2, the unit of measurement is in microseconds ('usage_usec')
    cpu_usage_start=$(grep 'usage_usec' /sys/fs/cgroup/cpu.stat | awk '{print $2}')
    time_start=$(date +%s%N)
    sleep 0.1
    cpu_usage_end=$(grep 'usage_usec' /sys/fs/cgroup/cpu.stat | awk '{print $2}')
    time_end=$(date +%s%N)

    cpu_delta=$((cpu_usage_end - cpu_usage_start))   # Delta in microseconds
    time_delta=$((time_end - time_start))           # Delta in nanoseconds

    # We convert the CPU delta into nanoseconds to have the same unit of measurement for time
    # and then calculate the percentage.
    cpu_usage=$(awk -v cpu_delta_us="$cpu_delta" -v time_delta_ns="$time_delta" \
        'BEGIN { printf "%.2f", ((cpu_delta_us * 1000) / time_delta_ns) * 100 }')

    # RAM calculation
    # In v2, the files are called 'memory.current' and 'memory.max'
    mem_usage_bytes=$(cat /sys/fs/cgroup/memory.current)
    mem_limit_bytes=$(cat /sys/fs/cgroup/memory.max)

    # If there is no limit, the file 'memory.max' contains the string “max”.
    if [ "$mem_limit_bytes" = "max" ]; then
        ram_usage="0.00"
    else
        ram_usage=$(awk -v used="$mem_usage_bytes" -v limit="$mem_limit_bytes" \
            'BEGIN { if (limit > 0) printf "%.2f", (used / limit) * 100; else print "0.00" }')
    fi
else
    # --- (Fallback) ---

    # CPU calculation
    # In v1, the unit is in nanoseconds ('cpuacct.usage')
    cpu_usage_start=$(cat /sys/fs/cgroup/cpuacct/cpuacct.usage)
    time_start=$(date +%s%N)
    sleep 0.1
    cpu_usage_end=$(cat /sys/fs/cgroup/cpuacct/cpuacct.usage)
    time_end=$(date +%s%N)
    
    cpu_delta=$((cpu_usage_end - cpu_usage_start))
    time_delta=$((time_end - time_start))
    
    cpu_usage=$(awk -v cpu_delta_ns="$cpu_delta" -v time_delta_ns="$time_delta" \
        'BEGIN { printf "%.2f", (cpu_delta_ns / time_delta_ns) * 100 }')

    # RAM calculation
    # In v1, the files are called 'memory.usage_in_bytes' and 'memory.limit_in_bytes'
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

# Make the script executable
chmod +x /usr/local/bin/get_node_metrics.sh

echo "Nodo SSH pronto"

# 5. Start the SSH service in the foreground
exec /usr/sbin/sshd -D