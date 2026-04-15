# Google Service Account

## What is a Service Account?

A Service Account is a special type of Google account that represents a non-human user (like a server or application). Instead of using your personal Google account (which requires browser-based login), a service account authenticates programmatically using a JSON key file. This allows the OpenDLP backend to access Google Sheets without human interaction.

Think of it as a "robot user" that can read and write to Google Spreadsheets on behalf of your application.

## Setup Overview

To work with Google Spreadsheets we need to set up a service account. The high level instructions are:

- ensure there is a google cloud project
- create a new service account in that project
- enable the Google Sheets API and Google Drive API on the project
- generate and save a JSON API Key for that service account
- share the spreadsheet in question with the service account email address

## Google Cloud Project

You could create a new project, or you could add the service account to an existing project. You can find the list of google cloud projects by going to <https://console.cloud.google.com/iam-admin/serviceaccounts> and clicking on the Project box in the top bar. The `Ctrl-O` shortcut will also open it.

In the dialogue box that pops up, you can select any project you have access to, or click on "New project".

### gcloud cli

```sh
gcloud projects list | rg -v '^sys-'

gcloud projects create [PROJECT_ID]
```

Then switch to the project:

```sh
gcloud config set project [PROJECT_ID]

# just to confirm
gcloud config list
```

## Create Service Account

Go to <https://console.cloud.google.com/iam-admin/serviceaccounts> - it will show a list of service accounts. At the top there is a link to "Create service account".

### gcloud cli

```sh
gcloud iam service-accounts create SERVICE_ACCOUNT_NAME \
  --description="DESCRIPTION" \
  --display-name="DISPLAY_NAME"

# check it exists
gcloud iam service-accounts list

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT_NAME@PROJECT_ID.iam.gserviceaccount.com"
```

## Give project access to the Google Sheets API

_Note this is for the project, not per-service-account._

Go to <https://console.cloud.google.com/apis/library/sheets.googleapis.com?project=PROJECT_ID> - it will either say "API Enabled" (in which case you're fine) or will have a button to enable it.

### gcloud cli

```sh
gcloud services enable sheets.googleapis.com
```

## Give project access to the Google Drive API

_Note this is for the project, not per-service-account._

OpenDLP (via the `sortition-algorithms` library) calls the Drive API to verify that a given file is a native Google Sheet before reading it. Without this API enabled, selections against Google Spreadsheets will fail.

Go to <https://console.cloud.google.com/apis/library/drive.googleapis.com?project=PROJECT_ID> - it will either say "API Enabled" (in which case you're fine) or will have a button to enable it.

### gcloud cli

```sh
gcloud services enable drive.googleapis.com
```

Note that enabling the Drive API does not grant the service account broad access to your Drive - it can still only access spreadsheets that have been explicitly shared with its email address.

## JSON API Key for service account

From the [service accounts page](https://console.cloud.google.com/iam-admin/serviceaccounts) you should see a list of service accounts. The table has a column with 3 dots, from there you can choose "Manage keys" and then "Add key". Choose "Create new key" > "JSON". That will then create the key and it will be downloaded by your browser. **Save it somewhere sensible.**

### gcloud cli

```sh
gcloud iam service-accounts keys create KEY_FILE \
    --iam-account=SA_NAME@PROJECT_ID.iam.gserviceaccount.com
```

[More docs here](https://cloud.google.com/iam/docs/keys-create-delete).

## Share the spreadsheet with the service account email address

If you look in the JSON file, the key `client_email` has the value of the email address - something like `SERVICE_ACCOUNT_NAME@PROJECT_ID.iam.gserviceaccount.com`. Go to the Google Spreadsheet you want to use, and share it with that email address.

Once you have done that, OpenDLP can do a selection with that spreadsheet.

## Configure OpenDLP

After downloading the JSON key file, you need to tell OpenDLP where to find it by setting the `GOOGLE_AUTH_JSON_PATH` environment variable.

### For local development

Store your credentials in a secure location outside the repository, with restricted permissions:

```bash
# Create a private directory for credentials (if it doesn't exist)
mkdir -p ~/private
chmod 700 ~/private

# Move your downloaded file there
mv ~/Downloads/your-project-*.json ~/private/google-service-account.json
chmod 600 ~/private/google-service-account.json
```

Then add the path to a `.env` file in the project root (this file is gitignored):

```bash
# backend/.env
GOOGLE_AUTH_JSON_PATH=/Users/yourname/private/google-service-account.json
```

Finally, start both Flask and Celery (in separate terminals):

```bash
just run      # Flask server
just celery   # Celery worker
```

**Why this approach?**
- Credentials stored outside the repo can't be accidentally committed
- The `.env` file works across git worktrees and shell sessions
- Restricted permissions (700/600) prevent other users from reading the credentials
- Both Flask and Celery automatically load from `.env`

### For Docker deployment

Add the environment variable to your Docker Compose configuration or pass it when running the container:

```yaml
environment:
  - GOOGLE_AUTH_JSON_PATH=/app/credentials/service-account.json
volumes:
  - ./credentials.json:/app/credentials/service-account.json:ro
```

### Verify the configuration

You can verify the credentials are correctly configured by checking the `/health` endpoint - it returns JSON including a `service_account_email` field. If it shows the email address (not "UNKNOWN"), the configuration is working.

Alternatively, check the Assembly Data page in the backoffice, which also displays the service account email.

## Troubleshooting

### "IsADirectoryError: Is a directory: '.'"

This error means `GOOGLE_AUTH_JSON_PATH` is not set or is set to a directory instead of a file. Make sure the variable points to the actual JSON file path.

### "Permission denied" when accessing a spreadsheet

Make sure you've shared the Google Spreadsheet with the service account email address (found in the `client_email` field of the JSON file).
