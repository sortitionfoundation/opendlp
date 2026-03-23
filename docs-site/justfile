# ABOUTME: Build and development commands for the OpenDLP documentation site
# ABOUTME: Provides targets for building, serving locally, and cleaning the Hugo site

# Build the static site into public/
build:
    hugo --source .

# Serve the site locally with live reload for development
serve:
    hugo server --source . --buildDrafts --navigateToChanged --bind=0.0.0.0

# Clean the build output
clean:
    rm -rf public/
