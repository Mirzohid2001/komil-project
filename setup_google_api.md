# Setting up Google API for Test Import

Follow these steps to set up Google API access for importing tests:

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "New Project" at the top right
3. Name your project (e.g., "Zavod Test Import") and click "Create"
4. Select your new project from the dropdown at the top

## 2. Enable Google Sheets API

1. From the dashboard, go to "APIs & Services" > "Library"
2. Search for "Google Sheets API"
3. Click on it and then click "Enable"

## 3. Create Service Account

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" and select "Service Account"
3. Enter a name for your service account (e.g., "test-importer")
4. Click "Create and Continue"
5. For the role, select "Basic" > "Viewer"
6. Click "Continue" and then "Done"

## 4. Create Service Account Key

1. On the Credentials page, click on your newly created service account
2. Go to the "Keys" tab
3. Click "Add Key" > "Create new key"
4. Select "JSON" and click "Create"
5. The key file will be downloaded to your computer
6. Save this file as `credentials.json` in your project directory

## 5. Prepare Your Google Sheet

1. Create a new Google Sheet
2. Set up the two worksheets as described in the template
3. Share the sheet with the service account email (it looks like `service-account-name@project-id.iam.gserviceaccount.com`)
4. Copy the Sheet ID from the URL (it's the long string in the URL between `/d/` and `/edit`)

## 6. Import Tests

Run the command:

```
python manage.py import_tests_from_google --sheet_id=YOUR_SHEET_ID --credentials=path/to/credentials.json --test_role=оператор
```

Replace:
- `YOUR_SHEET_ID` with the ID from step 5
- `path/to/credentials.json` with the path to your downloaded credentials file
- `оператор` with the role this test is for (e.g., 'оператор', 'админ', etc.) 