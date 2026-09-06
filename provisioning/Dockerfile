FROM ubuntu:22.04

LABEL maintainer="Linux Server Administration & Network Diagnostic Suite"
LABEL description="Ubuntu Server environment with systemd, networking tools, and diagnostic daemon"

ENV DEBIAN_FRONTEND=noninteractive
ENV container=docker

# Install core server utilities, networking packages, and diagnostic tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd \
    systemd-sysv \
    udev \
    dbus \
    bash \
    sudo \
    curl \
    wget \
    openssh-server \
    ufw \
    iptables \
    iperf3 \
    iproute2 \
    net-tools \
    iputils-ping \
    traceroute \
    dnsutils \
    procps \
    cron \
    logrotate \
    python3 \
    python3-pip \
    tar \
    gzip \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Clean up systemd units for container usage
RUN rm -f /lib/systemd/system/multi-user.target.wants/* \
    /etc/systemd/system/*.wants/* \
    /lib/systemd/system/local-fs.target.wants/* \
    /lib/systemd/system/sockets.target.wants/*udev* \
    /lib/systemd/system/sockets.target.wants/*initctl* \
    /lib/systemd/system/basic.target.wants/*

# Create test administrator user with sudo permissions
RUN useradd -m -s /bin/bash sysadmin && \
    echo "sysadmin ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    mkdir -p /home/sysadmin/.ssh && \
    chmod 700 /home/sysadmin/.ssh

# Configure SSH directory
RUN mkdir -p /var/run/sshd && \
    chmod 0755 /var/run/sshd

# Expose SSH, iperf3, and diagnostic ports
EXPOSE 22 5201 9100

WORKDIR /opt/linux-server-diagnostic-suite

STOPSIGNAL SIGRTMIN+3

CMD ["/lib/systemd/systemd"]
