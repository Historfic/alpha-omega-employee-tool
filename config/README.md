# config/

Place your Google service-account key file here as:

```
config/credentials.json
```

This file is gitignored (see the root `.gitignore`) and must never be committed.

## How to obtain `credentials.json`

1. Follow the walkthrough in [../docs/setup.md](../docs/setup.md) to create a
   Google Cloud project, enable the Sheets API, and create a service account.
2. Generate a JSON key for that service account and download it.
3. Save it to this folder as `credentials.json`.
4. Share each target spreadsheet with the service account's email address
   (granting at least Viewer access; Editor if the tool needs to write back).
5. Set `GOOGLE_APPLICATION_CREDENTIALS=config/credentials.json` in your `.env`
   (this is already the default in `.env.example`).
