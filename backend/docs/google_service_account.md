# Google Service Account

To work with Google Spreadsheets we need to set up a service account. The high level instructions are:

- ensure there is a google cloud project
- create a new service account in that project
- give that service account access to the Google Sheets API
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
