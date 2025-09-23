# This file is in the git repo root, so outside of the directory claude runs.
# So claude should not try to run the jobs in this file.

# update the deployment on opendlp-test server from git main branch
deploy-opendlp-test:
  @ssh opendlp-test just opendlp-update
