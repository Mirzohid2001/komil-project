# Test Automation Tools

This project includes several tools for automating test creation and management. Here's how to use them:

## 1. Automatic Daily Test Generation

Tests are automatically generated each day for all user roles. Each test contains 30 questions specific to the role.

### Setup on Windows

The system can be configured to automatically generate tests at 1:00 AM every day:

1. Run the provided batch file as Administrator:
   ```
   create_windows_task.bat
   ```

2. This will create a Windows Scheduled Task that runs daily at 1:00 AM.

3. To verify the task was created:
   ```
   schtasks /query /tn "ZavodDailyTestGeneration"
   ```

4. To delete the task:
   ```
   schtasks /delete /tn "ZavodDailyTestGeneration" /f
   ```

### Setup on Linux/Unix

If running on Linux/Unix systems, use crontab:

1. Install django-crontab:
   ```
   pip install django-crontab
   ```

2. Edit the crontab manually:
   ```
   crontab -e
   ```

3. Add this line:
   ```
   0 1 * * * cd /path/to/project && /path/to/venv/bin/python manage.py generate_daily_tests
   ```

### Manual Generation

To manually generate tests for all roles:
```
python manage.py generate_daily_tests
```

Options:
- `--force`: Override any tests already generated for today
- `--test_roles [roles]`: Generate tests only for specific roles (e.g., `--test_roles оператор инженер`)

## 2. Import Tests from Google Sheets

You can import tests from structured Google Sheets.

### Setup

1. Follow the instructions in `setup_google_api.md` to set up Google API access
2. Create a Google Sheet following the structure in `google_sheets_template_example.txt`
3. Share the sheet with your service account

### Usage

```
python manage.py import_tests_from_google --sheet_id=YOUR_SHEET_ID --credentials=path/to/credentials.json --test_role=оператор
```

Parameters:
- `--sheet_id`: ID of your Google Sheet (required)
- `--credentials`: Path to credentials.json file (required)
- `--test_role`: Role for the test (default: оператор)

## 3. Import Tests from Google Forms

You can also import tests directly from Google Forms.

### Setup

1. Same Google API setup as for Google Sheets
2. Make sure your Google Form has multiple-choice questions

### Usage

```
python manage.py import_tests_from_google_forms --form_id=YOUR_FORM_ID --credentials=path/to/credentials.json --test_role=оператор
```

Parameters:
- `--form_id`: ID of your Google Form (required)
- `--credentials`: Path to credentials.json file (required)
- `--test_title`: Custom title for the test (optional)
- `--test_description`: Custom description for the test (optional)
- `--test_role`: Role for the test (default: оператор)
- `--passing_score`: Passing score percentage (default: 70)
- `--time_limit`: Time limit in minutes (default: 30)

## Troubleshooting

If tests don't have questions, check:
1. The correct format is being used for import
2. The scheduled task is properly configured
3. Run the command manually to check for any errors:
   ```
   python manage.py generate_daily_tests --force
   ``` 