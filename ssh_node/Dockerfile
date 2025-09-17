FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

# Installa OpenSSH Server, curl (per healthcheck), sshpass (per healthcheck)
# e il pacchetto docker.io che include il client Docker CLI e il gruppo 'docker'.
RUN apt-get update && apt-get install -y \
    openssh-server \
    curl \
    sshpass \
    sudo \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Crea la directory per SSH e imposta i permessi
RUN mkdir /var/run/sshd

# Configurazione SSH: Imposta una password per l'utente root
RUN echo 'root:password' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
RUN sed -i 's/UsePAM yes/UsePAM no/' /etc/ssh/sshd_config
RUN sed -i 's/ChallengeResponseAuthentication yes/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config

EXPOSE 22

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

CMD ["/usr/local/bin/entrypoint.sh"]
