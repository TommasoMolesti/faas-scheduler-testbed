#!/bin/bash
# ssh_node/entrypoint.sh

USER="sshuser"
PASSWORD="sshpassword"

# Creazione utente SSH se non esiste e set password
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER"
fi
echo "$USER:$PASSWORD" | chpasswd

# Configurazione SSH per permettere l'accesso tramite password
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

# Gestione dei permessi Docker:
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

if ! getent group "$DOCKER_GID" >/dev/null; then
    groupadd -g "$DOCKER_GID" docker_host_group
    echo "Creato gruppo 'docker_host_group' con GID $DOCKER_GID"
else
    EXISTING_GROUP_NAME=$(getent group "$DOCKER_GID" | cut -d: -f1)
    if [ "$EXISTING_GROUP_NAME" != "docker_host_group" ]; then
        groupmod -n docker_host_group "$EXISTING_GROUP_NAME"
    else
        echo "Gruppo 'docker_host_group' con GID $DOCKER_GID già esistente."
    fi
fi

# Aggiungi l'utente SSH al gruppo corretto
usermod -aG docker_host_group "$USER"

# Avvia il servizio SSH in background
/usr/sbin/sshd -D &
SSH_PID=$!

# Avvia il demone Docker in background
dockerd > /var/log/docker.log 2>&1 &
DOCKER_PID=$!

echo "SSH e Docker Daemon avviati."

# Mantieni il container in esecuzione aspettando che uno dei processi principali termini
# In questo caso, si aspetta entrambi i PID per assicurarci che il container non termini
# finché SSH o Docker non si fermano.
wait $SSH_PID $DOCKER_PID
