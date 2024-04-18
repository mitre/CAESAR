# ---- use a base image to compile requirements / save image size -----
FROM ubuntu:jammy-20240227 as base

# Install MITRE CA Certs if on the MII
RUN apt update && apt install -yq curl && if curl -ksSL https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/os_scripts/install_certs.sh > /tmp/install_certs.sh 2>/dev/null; then sh /tmp/install_certs.sh && rm -f /tmp/install_certs.sh; else echo "Not on the MII, skipping certificate install"; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update -y && \
    apt install -yq \
    libffi-dev \
    libimage-exiftool-perl \
    libjpeg8-dev \
    libmysqlclient-dev \
    libncurses5-dev \
    libpq-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libzip-dev \
    python-setuptools \
    python3-dev \
    python3-pip \
    python3-venv

WORKDIR /app

# Sets utf-8 encoding for Python
ENV LANG=C.UTF-8
# Turns off writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Seems to speed things up
ENV PYTHONUNBUFFERED=1
# The `--copies` option tells `venv` to copy libs and binaries
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY ./requirements.txt  /app/requirements.txt

RUN . /opt/venv/bin/activate


RUN pip install --no-cache-dir -Ur requirements.txt
RUN ls -la /opt/venv/bin/


# ----------------- main container -------------------------

FROM ubuntu:jammy-20240227

# Install MITRE CA Certs if on the MII
RUN apt update && apt install -yq curl && if curl -ksSL https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/os_scripts/install_certs.sh > /tmp/install_certs.sh 2>/dev/null; then sh /tmp/install_certs.sh && rm -f /tmp/install_certs.sh; else echo "Not on the MII, skipping certificate install"; fi

ENV DEBIAN_FRONTEND=noninteractive
ARG ROLE
ENV ROLE=${ROLE}
RUN echo "Building ${ROLE} container."
RUN if [ "$ROLE" = "flask" ]; then \
    apt update -y && apt install -yq python3-dev python3-venv postgis weasyprint; \
    elif [ "$ROLE" = "celery" ]; then \
    apt update -y && apt install -yq python3-dev python3-venv postgis libimage-exiftool-perl ffmpeg; \
    fi
RUN apt clean
RUN apt autoremove

WORKDIR /app

# Allows specifying a custom UID and GID during build
ARG USER_ID=${USER_ID:-1000}
ENV USER_ID=${USER_ID:-1000}
ARG GROUP_ID=${GROUP_ID:-1000}
ENV GROUP_ID=${GROUP_ID:-1000}

RUN groupadd bayanat --gid=$GROUP_ID
RUN useradd bayanat --uid $USER_ID --gid=$GROUP_ID

# Sets utf-8 encoding for Python
ENV LANG=C.UTF-8
# Turns off writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Seems to speed things up
ENV PYTHONUNBUFFERED=1

COPY . /app
# copy compiled virtualenv
COPY --from=base /opt/venv /opt/venv

COPY --chown=bayanat:bayanat ./flask/bin/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 550 /usr/local/bin/entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH"

# Credentials for adding an admin user if one does not already exist
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=change_this_password

# Install MITRE tool certs if on the MII
RUN if curl -ksSL https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/tool_scripts/install_certs.sh > /tmp/install_tool_certs.sh 2>/dev/null; then MODE=python sh /tmp/install_tool_certs.sh && rm -f /tmp/install_tool_certs.sh; else echo "Not on the MII, skipping tool certificate install"; fi

USER bayanat

CMD ["/usr/local/bin/entrypoint.sh"]
