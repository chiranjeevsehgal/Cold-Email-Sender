# Bulk Email Sender

A desktop GUI app that reads a CSV of contacts and sends each one a
personalized email built from a template.

---

## 1. Requirements

- Python 3.8+
- Tkinter (comes bundled with Python on Windows/macOS; on Linux you may
  need to install it separately — see Troubleshooting below)
- One optional third-party package: `python-dotenv` (only needed if you
  want to pre-fill SMTP settings from a `.env` file)

## 2. Install

```bash
# 1. (Recommended) create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

If you don't want to bother with `.env` support at all, you can skip
`pip install` entirely — the app still runs with plain Python, you'll
just type SMTP details into the GUI each time instead of having them
pre-filled.

## 3. Configure SMTP credentials (optional but recommended)

```bash
cp .env.example .env
```

Edit `.env` and fill in your real sender email, app password, and SMTP
server details. This file is loaded automatically when the app starts
and just pre-fills the "SMTP Settings" tab — you can still change
anything in the GUI before sending, and nothing is sent anywhere until
you click **Start Sending**.

**Important:** if your email provider has 2-factor authentication
enabled (Gmail, Outlook, Yahoo all do by default now), you cannot use
your normal login password here — you must generate an **app
password** from your account's security settings and use that instead.

Never share your `.env` file or commit it to git — add it to
`.gitignore`.

## 4. Prepare your CSV

You have two options:

- **Use the built-in generator:** in the app's "CSV Data" tab, click
  "Create Sample CSV..." to save a ready-made `sample_contacts.csv`
  with the correct headers and two example rows, which you can edit
  and load right back in.
- **Use the one included here:** `sample_contacts.csv` ships alongside
  this script as a starting template.

The CSV needs a header row. Column names are matched case-insensitively
and a few common variants are accepted:

| Data          | Accepted header names                              |
|---------------|-----------------------------------------------------|
| First name    | `First Name`, `FirstName`, `First`                   |
| Last name     | `Last Name`, `LastName`, `Last`, `Surname`           |
| Company       | `Company`, `Company Name`, `Organization`            |
| Email         | `Email`, `Email Address`, `E-mail`, `Mail`           |

Example `contacts.csv`:

```csv
First Name,Last Name,Company,Email
Aditi,Sharma,Nimbus Tech,aditi.sharma@example.com
Rahul,Verma,Blue Orbit,rahul.verma@example.com
```

Only the **Email** column is strictly required for the app to load the
file; the others default to blank if missing.

## 5. Run the app

```bash
python bulk_email_sender.py
```

## 6. Using the app

The app has four tabs, meant to be used in order:

1. **CSV Data** — click "Browse CSV..." and select your file. A preview
   table shows the detected first name / last name / company / email
   for each row, plus a count of valid email addresses found.

2. **Email Template** — write your subject and body using placeholders:
   - `{first_name}`
   - `{last_name}`
   - `{full_name}` (first + last combined)
   - `{company}`
   - `{email}`

   Example:
   ```
   Subject: Hello {first_name}, quick note for {company}

   Hi {first_name},

   I hope things are going well at {company}...
   ```
   Click "Preview with first row" to see exactly what will be sent to
   your first contact, with placeholders filled in.

3. **SMTP Settings** — pick a provider preset (Gmail, Outlook, Yahoo)
   or enter your own server/port, then enter your sender email and app
   password. Click "Send Test Email to Myself" first to confirm your
   credentials work before doing a real send.

4. **Send** — set an optional delay between emails (helps avoid being
   rate-limited or flagged as spam), choose whether to skip rows with
   invalid/missing emails, then click "Start Sending". Progress, a live
   log, and a running sent/skipped/failed count are shown. You can
   click "Stop" at any time to halt after the current email.

## 7. Notes & good practices

- **Rate limits:** most providers (especially Gmail) cap how many
  emails you can send per day from a single account and may throttle
  or block rapid sending. Keep the delay at 1+ second and avoid
  sending to huge lists from a personal account.
- **Deliverability:** cold/bulk email to people who haven't opted in
  can violate your provider's terms of service and anti-spam laws
  (e.g. CAN-SPAM, GDPR) depending on your audience and jurisdiction —
  make sure you have a legitimate basis to email each recipient.
- **Testing:** always run "Send Test Email to Myself" and "Preview
  with first row" before a real bulk send.
- Credentials are only ever used locally to connect to your SMTP
  provider — nothing is sent to any third-party server by this app.

## 8. Troubleshooting

- **"tkinter not found" on Linux:**
  ```bash
  sudo apt-get install python3-tk
  ```
- **Authentication errors with Gmail/Outlook/Yahoo:** you're almost
  certainly using your regular password instead of an app password, or
  "less secure app access" / 2FA app-password generation hasn't been
  set up on the account yet.
- **Emails landing in spam:** this is normal for bulk sends from a
  personal SMTP account with no sending reputation. Keep volumes low
  and personalize the content — this tool is best suited for small to
  moderate personalized outreach, not marketing-scale blasts.