# syntax=docker/dockerfile:1.9
FROM ubuntu:noble AS build

# The following does not work in Podman unless you build in Docker
# compatibility mode: <https://github.com/containers/podman/issues/8477>
# You can manually prepend every RUN script with `set -ex` too.
SHELL ["sh", "-exc"]

# Ensure apt-get doesn't open a menu on you.
ENV DEBIAN_FRONTEND=noninteractive

### Start build prep.
### This should be a separate build container for better reuse.

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  build-essential \
  ca-certificates \
  python3-setuptools \
  python3.12-dev \
  nodejs \
  npm
EOT

# Security-conscious organizations should package/review uv themselves.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# - Silence uv complaining about not being able to use hard links,
# - tell uv to byte-compile packages for faster application startups,
# - prevent uv from accidentally downloading isolated Python builds,
# - pick a Python (use `/usr/bin/python3.12` on uv 0.5.0 and later),
# - and finally declare `/app` as the target for `uv sync`.
ENV UV_LINK_MODE=copy \
  UV_COMPILE_BYTECODE=1 \
  UV_PYTHON_DOWNLOADS=never \
  UV_PYTHON=python3.12 \
  UV_PROJECT_ENVIRONMENT=/app

### End build prep -- this is where your app Dockerfile should start.

# Synchronize DEPENDENCIES without the application itself.
# This layer is cached until uv.lock or pyproject.toml change, which are
# only temporarily mounted into the build container since we don't need
# them in the production one.
# You can create `/app` using `uv venv` in a separate `RUN`
# step to have it cached, but with uv it's so fast, it's not worth
# it, so we let `uv sync` create it for us automagically.
RUN --mount=type=cache,target=/root/.cache \
  --mount=type=bind,source=uv.lock,target=/uv.lock \
  --mount=type=bind,source=pyproject.toml,target=/pyproject.toml \
  uv sync \
  --locked \
  --no-dev \
  --no-install-project \
  --extra production

RUN mkdir /src
COPY package.json /src/
COPY package-lock.json /src/

WORKDIR /src
# and the same for the npm dependencies
# Build the sass files fresh
RUN --mount=type=cache,target=/root/.cache \
  npm install

COPY . /src

# Build the sass files fresh
# Need the sass files copied in before we run this of course
RUN --mount=type=cache,target=/root/.cache \
  npm run build:sass

# Now install the rest from `/src`: The APPLICATION w/o dependencies.
# `/src` will NOT be copied into the runtime container.
RUN --mount=type=cache,target=/root/.cache \
  uv sync \
  --locked \
  --no-dev \
  --no-editable

##########################################################################

FROM ubuntu:noble
SHELL ["sh", "-exc"]

# Optional: add the application virtualenv to search path.
ENV PATH=/app/bin:$PATH

# Don't run your app as root.
RUN <<EOT
groupadd -r app
useradd -r -d /app -g app -N app
EOT

# See <https://hynek.me/articles/docker-signals/>.
STOPSIGNAL SIGINT

# Note how the runtime dependencies differ from build-time ones.
# Notably, there is no uv either!
RUN <<EOT
apt-get update -qy
apt-get install -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  python3.12 \
  libpython3.12 \
  libpcre3 \
  libxml2

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# COPY uwsgi.ini /app/etc/uwsgi.ini

# Copy things we need to work before the app - the app is most likely to change
# Copy in order from least likely to change to most likely
# Copy from local if possible
COPY alembic.ini babel.cfg wsgi.py migrations templates translations /app/

# static includes css files built from sass, so copy them from the build container
COPY --from=build --chown=app:app /src/static /app/static

# Copy the pre-built `/app` directory to the runtime container
# and change the ownership to user app and group app in one step.
COPY --from=build --chown=app:app /app /app

USER app
WORKDIR /app

# Strictly optional, but I like it for introspection of what I've built
# and run a smoke test that the application can, in fact, be imported.
RUN <<EOT
/app/bin/python -V
/app/bin/python -Im site
/app/bin/python -Ic 'import opendlp'
EOT

ENV FLASK_APP=opendlp.entrypoints.flask_app
