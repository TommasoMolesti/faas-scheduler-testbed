FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

# Install OpenSSH Server, curl (for healthcheck), sshpass (for healthcheck)
# and the docker.io package, which includes the Docker CLI client and the ‘docker’ group.
RUN apt-get update && apt-get install -y \
    openssh-server \
    curl \
    sshpass \
    sudo \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Create the directory for SSH and set the permissions
RUN mkdir /var/run/sshd

# SSH Configuration: Set a password for the root user
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
