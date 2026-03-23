# ABOUTME: Deployment guide for the OpenDLP documentation site
# ABOUTME: Covers static site deployment, CMS authentication setup, and content editing workflow

# Deploying the OpenDLP Documentation Site

This guide covers deploying the Hugo documentation site and setting up
Sveltia CMS for browser-based content editing.

## Prerequisites

- Hugo installed (v0.100.0 or later)
- Access to the target server for rsync deployment
- A GitHub account with access to the `sortitionfoundation/opendlp` repository

## Building the site

From the `docs-site/` directory:

```bash
just build
```

This runs `hugo` and outputs the static site to `public/`.

## Deploying the static files

The site is served as static files from disk. Deploy with rsync:

```bash
rsync -avz --delete public/ user@server:/path/to/docs-root/
```

Replace `user@server:/path/to/docs-root/` with the actual server details.

## Content editing with Sveltia CMS

Sveltia CMS provides a browser-based editor at `/admin/` on the deployed site.
Editors can create and update pages through a visual interface — changes are
committed directly to the GitHub repository.

After content is edited via the CMS, the site needs to be rebuilt and
redeployed (manually or via automation).

### Local editing (no auth needed)

When running the site locally with `just serve`, visit `http://localhost:1313/admin/`
and click "Work with Local Repository". The browser will prompt you to select the
root directory of the `opendlp` repo. Changes are written directly to your local
files — no GitHub auth required. This is useful for drafting content before pushing.

### Quick start: token-based sign-in

The simplest way to use the CMS requires no additional infrastructure:

1. Deploy the site (the `/admin/` path is included in the static output)
2. Visit `https://your-docs-domain/admin/`
3. Click "Sign in with GitHub" then choose "Sign in with token"
4. Generate a GitHub personal access token at https://github.com/settings/tokens
   with the `repo` scope
5. Paste the token into the prompt

This works immediately with no OAuth setup. It's suitable for a small number
of editors who each have GitHub accounts.

### Full setup: OAuth sign-in for teams

For a smoother sign-in experience (no token management), set up OAuth
authentication using the Sveltia CMS Authenticator on Cloudflare Workers.

#### Step 1: Deploy the OAuth authenticator

The authenticator is a small Cloudflare Workers script that handles the
OAuth flow between the browser and GitHub.

1. Go to https://github.com/sveltia/sveltia-cms-auth
2. Click the "Deploy to Cloudflare Workers" button, or clone and run
   `wrangler deploy` locally
3. Note your worker URL: `https://sveltia-cms-auth.<SUBDOMAIN>.workers.dev`

Cloudflare Workers has a generous free tier — this will cost nothing for
typical documentation editing usage.

#### Step 2: Register a GitHub OAuth App

1. Go to https://github.com/organizations/sortitionfoundation/settings/applications/new
   (or your GitHub org's settings)
2. Fill in:
   - **Application name:** `OpenDLP Docs CMS` (or similar)
   - **Homepage URL:** Your docs site URL
   - **Authorization callback URL:** `https://sveltia-cms-auth.<SUBDOMAIN>.workers.dev/callback`
3. Click "Register application"
4. On the next page, click "Generate a new client secret"
5. Save both the **Client ID** and **Client Secret**

#### Step 3: Configure the Cloudflare Worker

In the Cloudflare dashboard, go to your worker's Settings > Variables and add:

| Variable               | Value                        | Encrypt? |
|------------------------|------------------------------|----------|
| `GITHUB_CLIENT_ID`     | Your OAuth app's Client ID   | No       |
| `GITHUB_CLIENT_SECRET` | Your OAuth app's Client Secret | Yes    |

Optionally set `ALLOWED_DOMAINS` to restrict which domains can use the
authenticator (e.g. `your-docs-domain.org`).

#### Step 4: Update CMS configuration

In `docs-site/static/admin/config.yml`, uncomment and update the `base_url`:

```yaml
backend:
  name: github
  repo: sortitionfoundation/opendlp
  branch: main
  base_url: https://sveltia-cms-auth.<SUBDOMAIN>.workers.dev
```

Rebuild and redeploy the site.

#### Step 5: Test

1. Visit `https://your-docs-domain/admin/`
2. Click "Sign in with GitHub"
3. You should be redirected to GitHub for authorization
4. After authorizing, you'll be returned to the CMS editor

### Access control

Editors need:
- A GitHub account
- Write access to the `sortitionfoundation/opendlp` repository

The CMS commits changes using the editor's GitHub identity, so all edits
are attributed to the person who made them.

## Content workflow

1. Editor signs in at `/admin/` and makes changes
2. Changes are committed to the repository on GitHub
3. Someone (or automation) rebuilds the site: `just build`
4. Someone (or automation) deploys: `rsync -avz --delete public/ user@server:/path/to/docs-root/`

For fully automated publishing, consider adding a GitHub Actions workflow
that builds and deploys on push to the relevant branch.
