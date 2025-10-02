# This file is in the git repo root, so outside of the directory claude runs.
# So claude should not try to run the jobs in this file.

# update the deployment on opendlp-test server from git main branch
deploy-opendlp-test:
  #!/usr/bin/env bash
  if [ "$CLAUDECODE" == "1" ]; then
    echo "claude code is not allowed to deploy"
    exit 1
  fi
  ssh opendlp-test just opendlp-update
