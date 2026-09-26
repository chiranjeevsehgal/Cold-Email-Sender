"""
Bulk Email Sender (Tkinter GUI)
--------------------------------
Reads a CSV file containing columns like:
    First Name, Last Name, Company, Email

Lets you write an email template using placeholders:
    {first_name}, {last_name}, {full_name}, {company}, {email}

Then sends a personalized email to every row via SMTP.

Requirements: Python 3.8+, standard library only (tkinter, smtplib, csv, email).

Run:
    python bulk_email_sender.py
"""

import csv
import os
import re
import smtplib
import ssl
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads variables from a .env file in the working directory, if present
except ImportError:
    pass  # python-dotenv not installed; will still work with real environment variables


# ----------------------------- Config helpers ----------------------------- #

# Common SMTP presets (server, port, use_tls)
SMTP_PRESETS = {
    "Gmail": ("smtp.gmail.com", 587, True),
    "Outlook / Office365": ("smtp.office365.com", 587, True),
    "Yahoo": ("smtp.mail.yahoo.com", 587, True),
    "Custom": ("", 587, True),
}

# Column name aliases -> normalized key
COLUMN_ALIASES = {
    "first_name": ["first name", "firstname", "first"],
    "last_name": ["last name", "lastname", "last", "surname"],
    "company": ["company", "company name", "organization", "organisation"],
    "email": ["email", "email address", "e-mail", "mail"],
}

PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


def normalize_header(header):
    return header.strip().lower()


def map_columns(fieldnames):
    """
    Given the raw CSV header row, return a dict mapping our normalized
    keys (first_name, last_name, company, email) to the ACTUAL header
    string used in the CSV, so we can pull values from each row.
    """
    normalized = {normalize_header(h): h for h in fieldnames}
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[key] = normalized[alias]
                break
    return mapping


def build_row_context(row, mapping):
    """Build the placeholder dict for a single CSV row."""
    first = row.get(mapping.get("first_name", ""), "").strip()
    last = row.get(mapping.get("last_name", ""), "").strip()
    company = row.get(mapping.get("company", ""), "").strip()
    email = row.get(mapping.get("email", ""), "").strip()
    full_name = (first + " " + last).strip()
    return {
        "first_name": first,
        "last_name": last,
        "full_name": full_name,
        "company": company,
        "email": email,
    }


def render_template(template, context):
    """Replace {placeholder} tokens with values from context. Unknown
    placeholders are left as-is (rather than raising an error)."""
    def repl(match):
        key = match.group(1)
        return str(context.get(key, match.group(0)))
    return PLACEHOLDER_PATTERN.sub(repl, template)


def is_valid_email(addr):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr))


# --------------------------------- App ------------------------------------ #

class BulkEmailApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bulk Email Sender")
        self.geometry("880x720")
        self.minsize(760, 620)

        self.csv_path = tk.StringVar()
        self.rows = []          # list of dict rows from CSV
        self.column_mapping = {}  # normalized_key -> actual header
        self.stop_requested = False
        self.sending_thread = None

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_data = ttk.Frame(notebook)
        self.tab_template = ttk.Frame(notebook)
        self.tab_smtp = ttk.Frame(notebook)
        self.tab_send = ttk.Frame(notebook)

        notebook.add(self.tab_data, text="1. CSV Data")
        notebook.add(self.tab_template, text="2. Email Template")
        notebook.add(self.tab_smtp, text="3. SMTP Settings")
        notebook.add(self.tab_send, text="4. Send")

        self._build_data_tab()
        self._build_template_tab()
        self._build_smtp_tab()
        self._build_send_tab()

    # ---- Tab 1: CSV ----------------------------------------------------
    def _build_data_tab(self):
        frame = self.tab_data

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Entry(top, textvariable=self.csv_path, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(top, text="Browse CSV...", command=self.browse_csv).pack(side="left")
        ttk.Button(top, text="Create Sample CSV...", command=self.create_sample_csv).pack(side="left", padx=(8, 0))

        info = ttk.Label(
            frame,
            text=("Expected columns (any order, case-insensitive): "
                  "First Name, Last Name, Company, Email"),
            foreground="#555",
        )
        info.pack(fill="x", padx=10)

        self.mapping_label = ttk.Label(frame, text="No file loaded.", foreground="#555")
        self.mapping_label.pack(fill="x", padx=10, pady=(4, 10))

        # Preview table
        columns = ("first_name", "last_name", "company", "email")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, width=180, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.row_count_label = ttk.Label(frame, text="Rows loaded: 0")
        self.row_count_label.pack(anchor="w", padx=10, pady=(0, 10))

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.load_csv(path)
        except Exception as e:
            messagebox.showerror("Error loading CSV", str(e))

    def create_sample_csv(self):
        path = filedialog.asksaveasfilename(
            title="Save sample CSV as",
            defaultextension=".csv",
            initialfile="sample_contacts.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["First Name", "Last Name", "Company", "Email"])
                writer.writerow(["Aditi", "Sharma", "Nimbus Tech", "aditi.sharma@example.com"])
                writer.writerow(["Rahul", "Verma", "Blue Orbit", "rahul.verma@example.com"])
            messagebox.showinfo(
                "Sample CSV created",
                f"Sample file created at:\n{path}\n\n"
                "Open it, replace the example rows with your real contacts, "
                "then load it back in with 'Browse CSV...'."
            )
            if messagebox.askyesno("Load now?", "Load this sample file now?"):
                self.load_csv(path)
        except Exception as e:
            messagebox.showerror("Error creating sample CSV", str(e))

    def load_csv(self, path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            mapping = map_columns(fieldnames)

            missing = [k for k in ("first_name", "company", "email") if k not in mapping]
            if "email" not in mapping:
                raise ValueError(
                    "Could not find an Email column in the CSV. "
                    f"Columns found: {fieldnames}"
                )

            rows = [dict(r) for r in reader]

        self.csv_path.set(path)
        self.rows = rows
        self.column_mapping = mapping

        mapped_str = ", ".join(f"{k} -> '{v}'" for k, v in mapping.items())
        missing_str = f"  (missing/not found: {', '.join(missing)})" if missing else ""
        self.mapping_label.config(text=f"Detected columns: {mapped_str}{missing_str}")

        # Populate preview
        for item in self.tree.get_children():
            self.tree.delete(item)
        valid_count = 0
        for row in rows[:500]:  # cap preview for performance
            ctx = build_row_context(row, mapping)
            self.tree.insert("", "end", values=(
                ctx["first_name"], ctx["last_name"], ctx["company"], ctx["email"]
            ))
            if is_valid_email(ctx["email"]):
                valid_count += 1

        total_valid = sum(
            1 for r in rows if is_valid_email(build_row_context(r, mapping)["email"])
        )
        self.row_count_label.config(
            text=f"Rows loaded: {len(rows)}  |  Valid email addresses: {total_valid}"
        )

    # ---- Tab 2: Template -------------------------------------------------
    def _build_template_tab(self):
        frame = self.tab_template

        ttk.Label(frame, text="Subject:").pack(anchor="w", padx=10, pady=(10, 0))
        self.subject_entry = ttk.Entry(frame)
        self.subject_entry.insert(0, "Hello {first_name}, quick note from us")
        self.subject_entry.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(
            frame,
            text=("Body (use placeholders: {first_name} {last_name} {full_name} "
                  "{company} {email}):"),
        ).pack(anchor="w", padx=10)

        self.body_text = scrolledtext.ScrolledText(frame, wrap="word", height=18)
        self.body_text.insert("1.0", (
            "Hi {first_name},\n\n"
            "I hope things are going well at {company}.\n\n"
            "I'm reaching out to connect and share something I think might interest "
            "you and the team at {company}.\n\n"
            "Best regards,\n"
            "Your Name"
        ))
        self.body_text.pack(fill="both", expand=True, padx=10, pady=10)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btn_row, text="Preview with first row", command=self.preview_template).pack(side="left")

        self.preview_box = scrolledtext.ScrolledText(frame, wrap="word", height=8, state="disabled")
        self.preview_box.pack(fill="both", padx=10, pady=(0, 10))

    def preview_template(self):
        if not self.rows:
            messagebox.showinfo("No data", "Load a CSV first (Tab 1).")
            return
        ctx = build_row_context(self.rows[0], self.column_mapping)
        subject = render_template(self.subject_entry.get(), ctx)
        body = render_template(self.body_text.get("1.0", "end-1c"), ctx)
        preview = f"To: {ctx['email']}\nSubject: {subject}\n\n{body}"

        self.preview_box.config(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", preview)
        self.preview_box.config(state="disabled")

    # ---- Tab 3: SMTP -------------------------------------------------
    def _build_smtp_tab(self):
        frame = self.tab_smtp
        PADX = 10
        PADY = 6

        ttk.Label(frame, text="Provider preset:").grid(row=0, column=0, sticky="w", padx=PADX, pady=PADY)
        self.preset_var = tk.StringVar(value="Gmail")
        preset_combo = ttk.Combobox(
            frame, textvariable=self.preset_var, values=list(SMTP_PRESETS.keys()),
            state="readonly", width=25
        )
        preset_combo.grid(row=0, column=1, sticky="w", padx=PADX, pady=PADY)
        preset_combo.bind("<<ComboboxSelected>>", self.apply_preset)

        ttk.Label(frame, text="SMTP Server:").grid(row=1, column=0, sticky="w", padx=PADX, pady=PADY)
        self.server_entry = ttk.Entry(frame, width=35)
        self.server_entry.insert(0, os.environ.get("SMTP_SERVER", SMTP_PRESETS["Gmail"][0]))
        self.server_entry.grid(row=1, column=1, sticky="w", padx=PADX, pady=PADY)

        ttk.Label(frame, text="Port:").grid(row=2, column=0, sticky="w", padx=PADX, pady=PADY)
        self.port_entry = ttk.Entry(frame, width=10)
        self.port_entry.insert(0, os.environ.get("SMTP_PORT", str(SMTP_PRESETS["Gmail"][1])))
        self.port_entry.grid(row=2, column=1, sticky="w", padx=PADX, pady=PADY)

        self.tls_var = tk.BooleanVar(value=os.environ.get("SMTP_USE_TLS", "true").lower() != "false")
        ttk.Checkbutton(frame, text="Use STARTTLS", variable=self.tls_var).grid(
            row=3, column=1, sticky="w", padx=PADX, pady=PADY
        )

        ttk.Label(frame, text="Your Email (sender):").grid(row=4, column=0, sticky="w", padx=PADX, pady=PADY)
        self.sender_entry = ttk.Entry(frame, width=35)
        self.sender_entry.insert(0, os.environ.get("SENDER_EMAIL", ""))
        self.sender_entry.grid(row=4, column=1, sticky="w", padx=PADX, pady=PADY)

        ttk.Label(frame, text="Password / App Password:").grid(row=5, column=0, sticky="w", padx=PADX, pady=PADY)
        self.password_entry = ttk.Entry(frame, width=35, show="*")
        self.password_entry.insert(0, os.environ.get("SENDER_PASSWORD", ""))
        self.password_entry.grid(row=5, column=1, sticky="w", padx=PADX, pady=PADY)

        note = ttk.Label(
            frame,
            text=("Note: for Gmail/Yahoo/Outlook with 2FA enabled, you must generate an\n"
                  "'App Password' in your account security settings — your normal\n"
                  "login password will not work."),
            foreground="#555", justify="left"
        )
        note.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))

        ttk.Button(frame, text="Send Test Email to Myself", command=self.send_test_email).grid(
            row=7, column=1, sticky="w", padx=10, pady=10
        )

    def apply_preset(self, event=None):
        preset = self.preset_var.get()
        server, port, tls = SMTP_PRESETS[preset]
        self.server_entry.delete(0, "end")
        self.server_entry.insert(0, server)
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, str(port))
        self.tls_var.set(tls)

    def get_smtp_config(self):
        server = self.server_entry.get().strip()
        port_str = self.port_entry.get().strip()
        sender = self.sender_entry.get().strip()
        password = self.password_entry.get()
        use_tls = self.tls_var.get()

        if not server or not port_str or not sender or not password:
            raise ValueError("Please fill in all SMTP fields (server, port, sender email, password).")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError("Port must be a number.")
        if not is_valid_email(sender):
            raise ValueError("Sender email address looks invalid.")
        return server, port, sender, password, use_tls

    def connect_smtp(self):
        server, port, sender, password, use_tls = self.get_smtp_config()
        if port == 465 and not use_tls:
            smtp = smtplib.SMTP_SSL(server, port, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(server, port)
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
        smtp.login(sender, password)
        return smtp, sender

    def send_test_email(self):
        try:
            smtp, sender = self.connect_smtp()
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = sender
            msg["Subject"] = "Test email from Bulk Email Sender"
            msg.attach(MIMEText("This is a test email. If you received this, your SMTP settings work!", "plain"))
            smtp.sendmail(sender, [sender], msg.as_string())
            smtp.quit()
            messagebox.showinfo("Success", f"Test email sent to {sender}.")
        except Exception as e:
            messagebox.showerror("SMTP Error", str(e))

    # ---- Tab 4: Send -------------------------------------------------
    def _build_send_tab(self):
        frame = self.tab_send

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Delay between emails (seconds):").pack(side="left")
        self.delay_entry = ttk.Entry(top, width=6)
        self.delay_entry.insert(0, "1")
        self.delay_entry.pack(side="left", padx=(6, 20))

        self.skip_invalid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top, text="Skip rows with invalid/missing email", variable=self.skip_invalid_var
        ).pack(side="left")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        self.send_button = ttk.Button(btn_row, text="Start Sending", command=self.start_sending)
        self.send_button.pack(side="left")
        self.stop_button = ttk.Button(btn_row, text="Stop", command=self.stop_sending, state="disabled")
        self.stop_button.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(0, 10))

        self.status_label = ttk.Label(frame, text="Idle.")
        self.status_label.pack(anchor="w", padx=10)

        ttk.Label(frame, text="Log:").pack(anchor="w", padx=10, pady=(10, 0))
        self.log_box = scrolledtext.ScrolledText(frame, wrap="word", height=18, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, message):
        self.log_box.config(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def start_sending(self):
        if not self.rows:
            messagebox.showinfo("No data", "Load a CSV first (Tab 1).")
            return
        try:
            self.get_smtp_config()
        except ValueError as e:
            messagebox.showerror("SMTP settings incomplete", str(e))
            return

        try:
            delay = float(self.delay_entry.get())
        except ValueError:
            messagebox.showerror("Invalid delay", "Delay must be a number.")
            return

        confirm = messagebox.askyesno(
            "Confirm send",
            f"You are about to send emails to up to {len(self.rows)} recipients.\n\nContinue?"
        )
        if not confirm:
            return

        self.stop_requested = False
        self.send_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress["value"] = 0
        self.progress["maximum"] = len(self.rows)

        self.sending_thread = threading.Thread(target=self._send_worker, args=(delay,), daemon=True)
        self.sending_thread.start()

    def stop_sending(self):
        self.stop_requested = True
        self.log("Stop requested — will halt after the current email.")

    def _send_worker(self, delay):
        subject_template = self.subject_entry.get()
        body_template = self.body_text.get("1.0", "end-1c")

        try:
            smtp, sender = self.connect_smtp()
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("SMTP Error", str(e)))
            self.after(0, self._reset_send_ui)
            return

        sent, skipped, failed = 0, 0, 0

        for i, row in enumerate(self.rows, start=1):
            if self.stop_requested:
                self.after(0, lambda: self.log("Stopped by user."))
                break

            ctx = build_row_context(row, self.column_mapping)
            email_addr = ctx["email"]

            if not is_valid_email(email_addr):
                skipped += 1
                if self.skip_invalid_var.get():
                    self.after(0, lambda a=email_addr: self.log(f"Skipped (invalid email): '{a}'"))
                    self.after(0, self._advance_progress, i)
                    continue

            try:
                subject = render_template(subject_template, ctx)
                body = render_template(body_template, ctx)

                msg = MIMEMultipart()
                msg["From"] = sender
                msg["To"] = email_addr
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                smtp.sendmail(sender, [email_addr], msg.as_string())
                sent += 1
                self.after(0, lambda a=email_addr: self.log(f"Sent to {a}"))
            except Exception as e:
                failed += 1
                self.after(0, lambda a=email_addr, err=e: self.log(f"FAILED for {a}: {err}"))

            self.after(0, self._advance_progress, i)
            time.sleep(max(delay, 0))

        try:
            smtp.quit()
        except Exception:
            pass

        self.after(0, lambda: self.status_label.config(
            text=f"Done. Sent: {sent}  Skipped: {skipped}  Failed: {failed}"
        ))
        self.after(0, self._reset_send_ui)

    def _advance_progress(self, i):
        self.progress["value"] = i
        self.status_label.config(text=f"Processing {i}/{len(self.rows)}...")

    def _reset_send_ui(self):
        self.send_button.config(state="normal")
        self.stop_button.config(state="disabled")


if __name__ == "__main__":
    app = BulkEmailApp()
    app.mainloop()