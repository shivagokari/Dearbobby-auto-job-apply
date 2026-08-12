# DearBobby Automation — Naukri Job Auto-Apply Assistant

DearBobby Automation is a personal productivity tool designed to automate the process of searching and applying for jobs on Naukri.com using your own credentials and resume. 

It runs a headed (visible) browser session via Playwright, matches job postings against your resume and profile using a custom scoring algorithm, and applies only to matches that cross your specified score threshold (e.g., 60/100).

---

## Project Structure

```text
dearbobby-automation/
├── profile.json            # Your personal info, skills, preferences, and screening templates
├── resume_parser.py        # Resume parser utilizing pdfplumber and docx2txt
├── matcher.py              # Resume scoring and JD evaluation logic
├── portals/
│   ├── __init__.py
│   └── naukri.py           # Playwright browser automation for Naukri.com
├── main.py                 # Orchestrator and config-validation runner
├── applied_log.csv         # Audit log containing scored and applied jobs (created at runtime)
└── README.md               # Setup and usage guide
```

---

## Setup Instructions

### 1. Prerequisites
Make sure you have **Python 3.11+** installed on your system.

### 2. Install Dependencies
Install the required packages using pip:
```bash
pip install playwright pdfplumber docx2txt
```

### 3. Install Playwright Web Drivers
Download the Chromium browser binaries used by Playwright:
```bash
playwright install chromium
```

---

## How to Configure

### 1. Configure your Profile
Open `profile.json` in a text editor and fill in your details:
- **`personal`**: Name, email, phone, current city, and relocation willingness.
- **`experience`**: Total years of experience, current title/company/CTC, notice period, and detailed past roles.
- **`skills`**: Explicit primary and secondary skills list.
- **`search_preferences`**:
  - `target_titles`: List of titles you are targeting (e.g. `["Python Developer", "Backend Engineer"]`).
  - `target_locations`: List of cities or `"Remote"`.
  - `exclude_keywords`: Core keywords to filter out (e.g. `["intern", "freshers", "qa"]`). If any of these are in the job title or JD, the job is scored 0 and skipped immediately.
- **`matcher_settings`**:
  - `target_keyword_matches`: The number of matching resume keywords required to get the full 40/40 score (default is `15`).
- **`auto_apply_settings`**:
  - `enabled`: Set to `true` to let the script click the "Apply" button. Keep as `false` for testing dry runs.
  - `match_threshold`: The minimum score required (out of 100) to apply (default `60`).
  - `max_applications_per_run`: Limit to avoid mass-submitting (default `5`).
  - `delay_between_applications_seconds`: A `[min, max]` range (e.g. `[30, 90]`) to randomize application delays, mimicking human browsing speed.

### 2. Add your Resume
Drop your resume in the root folder. The script searches for files named `resume.pdf` or `resume.docx`.

---

## Running the Assistant

Execute the orchestrator:
```bash
python main.py
```

### First-Time Run (Manual Login)
1. On the first run, the tool will open a headed Chromium window and navigate to the Naukri login page.
2. The script will wait (up to 10 minutes) for you to log in manually. **Your credentials are never entered, read, or stored by the script.**
3. Once you log in and reach the Naukri homepage, the script detects the dashboard page and saves the session cookies and state to `naukri_session.json`.
4. The browser will close and proceed to run the search.

### Subsequent Runs
1. In future runs, the script loads `naukri_session.json` to restore your session automatically.
2. It runs completely hands-free while keeping the browser window visible so you can observe the actions.
3. If the session expires or is logged out, the script will automatically open the login page again for you to re-authenticate.

---

## Core Matcher Rules (Scoring Model)

The match score is calculated out of **100 points**:

1. **Exclusion Check (Hard-filter)**:
   If the job title or description contains any of your configured `exclude_keywords` (case-insensitive, matched at word boundaries), the score becomes **0** immediately.
2. **Job Title Similarity (35 points)**:
   Calculates Jaccard token overlap between your `target_titles` and the job's title. If the job title contains all keywords of your best matching target title, it gets `35/35`.
3. **Experience Range Match (25 points)**:
   Scans the JD text or metadata for years of experience.
   - If no range is specified, defaults to a pass (**25 points**).
   - If a range is specified (e.g., "3-6 years"), it passes (**25 points**) if your `total_years` is within that range. If you fall below, it gets `0/25`.
4. **Resume Keyword Overlap (40 points)**:
   Tokenizes the JD and matches it against the keyword set extracted from your resume and the skills specified in `profile.json`. Scoring is normalized against `target_keyword_matches`. If you match at least 15 keywords, you receive `40/40`.

---

## Extension: Adding Indeed & Foundit

This project is built using modular patterns, making it easy to extend. To add new job boards (e.g., Indeed, Foundit):

### Step 1: Create a new Portal Module
Create a new file in the `portals/` folder, such as `portals/indeed.py`. It should follow the same interface:
```python
def run(profile: dict, resume_keywords: set[str]):
    # 1. Open headed browser context
    # 2. Authenticate (using a saved indeed_session.json or manual login pause)
    # 3. Loop over search combinations
    # 4. Scrape job listings, apply scorer, and submit applications
    # 5. Log actions to applied_log.csv
```

### Step 2: Update the Orchestrator
Import the new portal in `main.py` and run it:
```python
from portals import indeed, naukri

def main():
    # ... loading and parsing ...
    naukri.run(profile, resume_keywords)
    indeed.run(profile, resume_keywords)
```
Since the `matcher.py` and `resume_parser.py` modules are completely generic, they will work out of the box with any job descriptions and titles scraped from Indeed, Foundit, or any other portals.
