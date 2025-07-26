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
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config # Meglio no per utenti non root
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

# 3. Gestione dei permessi Docker:
# Ottieni il GID del gruppo proprietario del socket Docker montato dall'host.
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

# Verifica se un gruppo con questo GID esiste già.
if ! getent group "$DOCKER_GID" >/dev/null; then
    groupadd -g "$DOCKER_GID" docker_host_group
    echo "Creato gruppo 'docker_host_group' con GID $DOCKER_GID"
else
    EXISTING_GROUP_NAME=$(getent group "$DOCKER_GID" | cut -d: -f1)
    if [ "$EXISTING_GROUP_NAME" != "docker_host_group" ]; then
        groupmod -n docker_host_group "$EXISTING_GROUP_NAME"
        echo "Rinominato gruppo '$EXISTING_GROUP_NAME' a 'docker_host_group' con GID $DOCKER_GID"
    else
        echo "Gruppo 'docker_host_group' con GID $DOCKER_GID già esistente."
    fi
fi

# Aggiungi l'utente SSH al gruppo corretto
usermod -aG docker_host_group "$USER"
echo "Aggiunto utente '$USER' al gruppo 'docker_host_group'."

# 4. Avvia il servizio SSH in background
/usr/sbin/sshd -D &
SSH_PID=$! # Cattura il PID del processo SSH

# 5. Avvia il demone Docker in background
dockerd > /var/log/docker.log 2>&1 &
DOCKER_PID=$! # Cattura il PID del processo Docker

echo "SSH e Docker Daemon avviati."

# 6. Mantieni il container in esecuzione aspettando che uno dei processi principali termini
# In questo caso, aspettiamo entrambi i PID per assicurarci che il container non termini
# finché SSH o Docker non si fermano.
wait $SSH_PID $DOCKER_PID
