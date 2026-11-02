# syntax=docker/dockerfile:1.9

# A named stage, rather than `COPY --from=<image>`, so that Dependabot can see
# and bump the version. Keep `uv-version` in .github/actions/setup-env/action.yml
# in step with it - Dependabot cannot bump that one.
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM ubuntu:resolute AS build

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
  ca-certificates \
  python3.14
EOT

# Security-conscious organizations should package/review uv themselves.
COPY --from=uv /uv /usr/local/bin/uv

# Ubuntu's apt nodejs only moves with the distro release - noble's was 18.x,
# which is EOL and cannot `require()` an ESM module, and that broke sass >=1.93
# (it pulls in the ESM-only chokidar 5, which needs Node >=20.19 where
# require(ESM) was backported). Copy a Node LTS from the official image
# instead, mirroring the uv copy above, so Node is chosen independently of the
# base image. We copy only the node binary and the npm package (not the whole
# bin/ dir, which also carries yarn/corepack/docker-entrypoint cruft) and
# recreate the npm/npx launcher symlinks ourselves.
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim /usr/local/lib/node_modules/npm/ /usr/local/lib/node_modules/npm/
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
  && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# - Silence uv complaining about not being able to use hard links,
# - tell uv to byte-compile packages for faster application startups,
# - prevent uv from accidentally downloading isolated Python builds,
# - pick a Python (use `/usr/bin/python3.14` on uv 0.5.0 and later),
# - and finally declare `/app` as the target for `uv sync`.
ENV UV_LINK_MODE=copy \
  UV_COMPILE_BYTECODE=1 \
  UV_PYTHON_DOWNLOADS=never \
  UV_PYTHON=python3.14 \
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
COPY package.json package-lock.json /src/

WORKDIR /src
# and the same for the npm dependencies - using `npm ci` to fully rely on the package-lock.json
# Build the sass files fresh
RUN --mount=type=cache,target=/root/.cache \
  npm ci

COPY . /src

# Build the sass files fresh
# Need the sass files copied in before we run this of course
RUN --mount=type=cache,target=/root/.cache \
  npm run build

# Create the .mo files from the .po files
# Note that .mo files are in the .gitignore
#
# This is the one place we call pybabel directly rather than through the `just`
# recipe that wraps it (`just translate-compile`), because there is no `just` in
# the build image. It is a safe exception: compile is the only pybabel
# subcommand with no flags we depend on. Do NOT do the same for extract or
# update - see docs/translations.md for what those drop when called bare.
#
# Two things that look like bugs and are not:
# - Fuzzy entries are left out of the .mo, which is the point of the flag: they
#   are machine translations awaiting review. A language can be almost fully
#   translated in the .po and still come out mostly English here. Do not reach
#   for --use-fuzzy to "fix" that; get the entries reviewed instead.
# - pybabel compile accepts a catalogue that msgfmt rejects, so it cannot be
#   relied on to catch a broken one. `just translate-check` does that, and the
#   publish workflow needs the quality job (which runs it) before it builds an
#   image, so nothing reaches a registry unchecked.
#
# `--no-sync` because a plain `uv run` syncs the default groups first, which
# would install every dev dependency into /app (one of them from git). Babel is
# already there as a production dependency of flask-babel.
RUN uv run --no-sync pybabel compile -d translations

# Now install the rest from `/src`: The APPLICATION w/o dependencies.
# `/src` will NOT be copied into the runtime container.
RUN --mount=type=cache,target=/root/.cache \
  uv sync \
  --locked \
  --no-dev \
  --no-editable \
  --extra production

# copy all the files we need into app (ignoring the ones we don't need)
# so that we can do a single copy in the final build stage.
# Note that we could do most of these from outside using COPY - but they
# are all already inside from `COPY . /src` - and we also need to copy generated
# files from:
# - /src/static/ now contains CSS and JS bundles generated by `npm run build`
# - /src/translations/ now contains files generated by `uv run pybabel compile ...`
RUN <<EOT
cp alembic.ini babel.cfg generated_version.txt wsgi.py gunicorn.conf.py /app/
cp -r /src/migrations /app/migrations
cp -r /src/static /app/static
cp -r /src/templates /app/templates
cp -r /src/translations /app/translations
EOT

##########################################################################

FROM ubuntu:resolute
SHELL ["sh", "-exc"]

# Optional: add the application virtualenv to search path.
ENV PATH=/app/bin:$PATH

# Don't run your app as root.
RUN <<EOT
groupadd -r app
useradd -r --uid 999 -d /app -g app -N app
EOT

# See <https://hynek.me/articles/docker-signals/>.
STOPSIGNAL SIGINT

# Note how the runtime dependencies differ from build-time ones.
# Notably, there is no uv either!
# curl is added to allow the healthcheck to run
# Also we run unattended-upgrade to get just security updates
RUN <<EOT
apt-get update -qy
apt-get install -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  python3.14 \
  libpython3.14 \
  curl \
  unattended-upgrades

/usr/bin/unattended-upgrade

# some packages do not get picked up by unattended-upgrade for some reason
apt-get upgrade -qyy \
  -o APT::Install-Recommends=false \
  -o APT::Install-Suggests=false \
  coreutils

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# The resolute base image ships Canonical's Pebble service manager as a bare
# binary outside dpkg, so unattended-upgrade never patches it and the image
# scan flags its bundled Go standard library. We don't use it - the entrypoint
# is gunicorn or celery.
rm -f /usr/bin/pebble
EOT

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
ENV PROJECT_ROOT=/app
