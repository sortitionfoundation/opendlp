# This file is in the git repo root, so outside of the directory claude runs.
# So claude should not try to run the jobs in this file.

# It is assumed the server names below are set up in your ~/.ssh/config file
# - opendlp-prod
# - opendlp-test
#
# For example:
#
# Host opendlp-test
#     Hostname opendlpstaging.vs.mythic-beasts.com

# `docker pussh` also needs to be set up - and the double-s in pussh is NOT a typo
# See https://github.com/psviderski/unregistry#installation for how to do that

# deploy the latest github docker image build to the test/demo server
deploy-opendlp-test:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  ssh opendlp-test sudo -u opendlp just --justfile /var/lib/opendlp/justfile opendlp-update

# deploy the latest github docker image build to production
deploy-opendlp-production:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  ssh opendlp-prod sudo -u opendlp just --justfile /var/lib/opendlp/justfile opendlp-update

# build docker with the current code, copy the image to the preview server and run on hd.preview
deploy-preview-hd:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  echo "*** Building docker image ***"
  docker build -t opendlp:hdpreview backend/
  # the double-s in pussh is NOT a typo
  echo "*** Pushing docker image to preview server ***"
  docker pussh opendlp:hdpreview opendlp-test
  echo "*** Restarting preview docker compose ***"
  ssh opendlp-test just --justfile /home/hamish/hdpreview/justfile update

# for hd.preview - reset the database with the one from the main demo instance
deploy-preview-hd-resetdb:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  ssh opendlp-test just --justfile /home/hamish/hdpreview/justfile resetdb

# build docker with the current code, copy the image to the preview server and run on gg.preview
deploy-preview-gg:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  echo "*** Building docker image ***"
  docker build -t opendlp:ggpreview backend/
  # the double-s in pussh is NOT a typo
  echo "*** Pushing docker image to preview server ***"
  docker pussh opendlp:ggpreview opendlp-test
  echo "*** Restarting preview docker compose ***"
  ssh opendlp-test just --justfile /home/gergo/ggpreview/justfile update

# for gg.preview - reset the database with the one from the main demo instance
deploy-preview-gg-resetdb:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  ssh opendlp-test just --justfile /home/gergo/ggpreview/justfile resetdb
