import os
import csv
import time
import random
import logging
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError

from matcher import score_job

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("naukri_portal")

# Centralized selectors for Naukri's DOM
# These are isolated here to make updates easy when Naukri's markup changes.
SELECTORS = {
    # Authentication
    "login_url": "https://www.naukri.com/nlogin/login",
    "dashboard_url": "https://www.naukri.com/mnjuser/homepage",
    "profile_indicator": "a[href*='/mnjuser/profile'], div.nNavbar, .nI-gns-s-name",
    
    # Search Results Page (SRP)
    # Naukri uses 'srp-jobtuple-container' or 'cust-job-tuple' in their modern design.
    "job_card": "div.srp-jobtuple-container, article.jobTuple, div.cust-job-tuple",
    
    # Inner job card selectors (relative to card element)
    "job_title": "a.title, a.job-tuple-title, .title",
    "company_name": "a.comp-name, .companyName, .company-name, [title*='Jobs at']",
    "location": "span.locWdth, span.location, li.location, .loc",
    "experience": "span.exp-wrap, span.exp, li.experience, .exp",
    
    # Job Detail Page (JDP)
    # Where full JD, apply button, and already applied messages are located.
    "jd_text": "section.job-desc, div.jd-desc, .job-desc, [class*='job-desc']",
    "apply_button": "button#apply-button, button.apply-button, button.apply-btn, .apply-btn",
    "already_applied": "span.applied-message, .applied-status, button.applied, .already-applied",
    "screening_questions": "div.screening-questions-container, div.modal-content, form.screening-form, .modal-body",
    "salary": "span.salary, li.salary, div.salary, [class*='salary'], .salary, .salary-label, span.loc + span + span"
}

SESSION_FILE = "naukri_session.json"
LOG_FILE = "applied_log.csv"

def find_otp_element(page: Page):
    selectors = [
        "input[placeholder*='OTP']", 
        "input[placeholder*='verification']", 
        "input[placeholder*='code']",
        "input[name*='otp']", 
        "input#otp", 
        "input.otp-input",
        "input[type='text']", # general fallback if there is only one text input visible
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                return loc
        except Exception:
            pass
    return None

def find_verify_button(page: Page):
    selectors = [
        "button[type='submit']",
        "button.verify-btn",
        "button.blue-btn",
        ".loginBtn",
        "button:has-text('Verify')",
        "button:has-text('Submit')",
        "button:has-text('Login')"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                return loc
        except Exception:
            pass
    return None

def ensure_logged_in(context: BrowserContext, page: Page) -> bool:
    """
    Checks if a persistent session exists and is valid.
    If not, opens Naukri login page and waits for user to log in manually or via dashboard.
    Saves the session state for future runs.
    """
    session_exists = os.path.exists(SESSION_FILE)
    
    if session_exists:
        logger.info("Session file found. Verifying login state...")
        try:
            page.goto(SELECTORS["dashboard_url"], timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # Look for profile indicator
            if page.locator(SELECTORS["profile_indicator"]).first.is_visible(timeout=5000):
                logger.info("Session is valid. Logged in successfully.")
                return True
            else:
                logger.warning("Session file exists but profile indicator not found. Session might be expired.")
        except Exception as e:
            logger.warning(f"Error checking login status: {e}. Assuming session expired.")
            
    # Session doesn't exist or is invalid. Trigger login.
    logger.info("Starting fresh browser session for manual login.")
    page.goto(SELECTORS["login_url"])
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Set up file path for handshake communication
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    handshake_path = os.path.join(workspace_root, "login_handshake.json")
    
    # Initialize handshake status
    with open(handshake_path, "w", encoding="utf-8") as f:
        json.dump({"status": "waiting_for_credentials"}, f)
        
    logger.info("Please log in manually inside the browser or enter credentials on the dashboard.")
    
    try:
        for i in range(600):  # 10 minutes timeout
            if page.is_closed():
                break
                
            # A. Check if logged in directly inside headed window
            try:
                if page.locator(SELECTORS["profile_indicator"]).first.is_visible(timeout=500):
                    logger.info("Manual login detected! Saving storage state...")
                    context.storage_state(path=SESSION_FILE)
                    logger.info(f"Session saved to {SESSION_FILE}")
                    
                    with open(handshake_path, "w", encoding="utf-8") as f:
                        json.dump({"status": "success"}, f)
                    return True
            except Exception:
                pass
                
            # B. Check for remote actions from dashboard in login_handshake.json
            if os.path.exists(handshake_path):
                try:
                    with open(handshake_path, "r", encoding="utf-8") as f:
                        handshake = json.load(f)
                except Exception:
                    handshake = {}
                    
                status = handshake.get("status")
                
                if status == "mobile_submitted":
                    mobile = handshake.get("mobile")
                    logger.info(f"Received remote mobile number for OTP login: '{mobile}'")
                    try:
                        # Switch to OTP login page if necessary
                        otp_btn = page.locator("button.otpButton, button:has-text('Use OTP to Login')").first
                        if otp_btn.is_visible(timeout=1000):
                            otp_btn.click()
                            page.wait_for_timeout(1000)
                            
                        # Fill mobile number
                        page.locator("input.mobileInputt, input[placeholder*='mobile number']").first.fill(mobile)
                        page.wait_for_timeout(500)
                        
                        # Click Get OTP button
                        get_otp_btn = page.locator("button.sndbtn, button:has-text('Get OTP')").first
                        get_otp_btn.click()
                        
                        page.wait_for_timeout(5000)
                        
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "processing"}, f)
                    except Exception as e:
                        logger.error(f"Error submitting remote mobile: {e}")
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "waiting_for_credentials", "error": str(e)}, f)
                            
                elif status == "credentials_submitted":
                    username = handshake.get("username")
                    password = handshake.get("password")
                    
                    logger.info(f"Received remote credentials for '{username}'. Filling fields...")
                    try:
                        # Clear and fill credentials
                        page.locator("input#usernameField").fill(username)
                        page.locator("input#passwordField").fill(password)
                        
                        # Find and click login submit button
                        login_btn = page.locator("button[type='submit']").first
                        login_btn.click()
                        
                        page.wait_for_timeout(5000)
                        
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "processing"}, f)
                    except Exception as e:
                        logger.error(f"Error submitting remote credentials: {e}")
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "waiting_for_credentials", "error": str(e)}, f)
                            
                elif status == "otp_submitted":
                    otp = handshake.get("otp")
                    logger.info(f"Received remote OTP: '{otp}'. Filling field...")
                    try:
                        otp_loc = find_otp_element(page)
                        if otp_loc:
                            otp_loc.fill(otp)
                            
                            verify_btn = find_verify_button(page)
                            if verify_btn:
                                verify_btn.click()
                                page.wait_for_timeout(5000)
                                
                                with open(handshake_path, "w", encoding="utf-8") as f:
                                    json.dump({"status": "processing"}, f)
                            else:
                                raise Exception("Verify button not found on OTP page.")
                        else:
                            raise Exception("OTP input field not found on page.")
                    except Exception as e:
                        logger.error(f"Error submitting remote OTP: {e}")
                        static_dir = os.path.join(workspace_root, "static")
                        scr_path = os.path.join(static_dir, "login_verification.png")
                        page.screenshot(path=scr_path)
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "waiting_for_otp", "screenshot": "/static/login_verification.png", "error": str(e)}, f)
                            
                elif status == "processing":
                    # Check if login resolved to homepage/dashboard
                    if page.locator(SELECTORS["profile_indicator"]).first.is_visible(timeout=500):
                        logger.info("Manual login detected! Saving storage state...")
                        context.storage_state(path=SESSION_FILE)
                        logger.info(f"Session saved to {SESSION_FILE}")
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "success"}, f)
                        return True
                        
                    # Check if OTP page is active
                    otp_loc = find_otp_element(page)
                    if otp_loc:
                        logger.info("OTP verification required. Saving screen preview...")
                        static_dir = os.path.join(workspace_root, "static")
                        os.makedirs(static_dir, exist_ok=True)
                        scr_path = os.path.join(static_dir, "login_verification.png")
                        page.screenshot(path=scr_path)
                        
                        with open(handshake_path, "w", encoding="utf-8") as f:
                            json.dump({"status": "waiting_for_otp", "screenshot": "/static/login_verification.png"}, f)
                    else:
                        # Check for inline error text on login form page
                        try:
                            err_loc = page.locator(".error-message, .err-msg, [class*='error-']").first
                            if err_loc.is_visible(timeout=500):
                                err_msg = err_loc.inner_text().strip()
                                if err_msg:
                                    logger.warning(f"Login error message: '{err_msg}'")
                                    with open(handshake_path, "w", encoding="utf-8") as f:
                                        json.dump({"status": "waiting_for_credentials", "error": err_msg}, f)
                                    continue
                        except Exception:
                            pass
                            
                        # If still just loading/waiting or general error, fall back to credentials edit screen
                        if i % 12 == 0 and i > 0:
                            static_dir = os.path.join(workspace_root, "static")
                            scr_path = os.path.join(static_dir, "login_verification.png")
                            page.screenshot(path=scr_path)
                            with open(handshake_path, "w", encoding="utf-8") as f:
                                json.dump({"status": "waiting_for_credentials", "screenshot": "/static/login_verification.png", "error": "Login failed or still loading. Please check credentials."}, f)
                                
            page.wait_for_timeout(1000)
            
        logger.error("Login timeout or browser closed. Exiting.")
        if os.path.exists(handshake_path):
            os.remove(handshake_path)
        return False
    except Exception as e:
        logger.error(f"Error during login verification: {e}")
        if os.path.exists(handshake_path):
            os.remove(handshake_path)
        return False

def slugify(text: str) -> str:
    """
    Converts string to a clean URL slug (lowercase, words separated by hyphens).
    """
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')

def parse_freshness_to_days(text: str) -> float:
    """
    Parses a Naukri posted time string (e.g. '1 day ago', '3 days ago', '1 week ago', 'today')
    into a number of days ago. Returns a float representing days.
    """
    s = text.lower().strip()
    if not s:
        return 9999.0
        
    if "just now" in s or "few hours" in s or "hour" in s or "today" in s:
        return 0.0
        
    # Pattern for "X day(s) ago"
    day_match = re.search(r'(\d+)\s*day', s)
    if day_match:
        return float(day_match.group(1))
        
    # Pattern for "X week(s) ago"
    week_match = re.search(r'(\d+)\s*week', s)
    if week_match:
        return float(week_match.group(1)) * 7.0
        
    # Pattern for "X month(s) ago"
    month_match = re.search(r'(\d+)\s*month', s)
    if month_match:
        return float(month_match.group(1)) * 30.0
        
    if "week" in s:
        return 7.0
    if "month" in s:
        return 30.0
        
    return 9999.0

def search_jobs(page: Page, title: str, location: str) -> list[dict]:
    """
    Navigates to Naukri's search page and extracts job cards details.
    """
    title_slug = slugify(title)
    
    if location:
        loc_slug = slugify(location)
        search_url = f"https://www.naukri.com/{title_slug}-jobs-in-{loc_slug}"
    else:
        search_url = f"https://www.naukri.com/{title_slug}-jobs"
        
    logger.info(f"Navigating to search page: {search_url}")
    
    jobs = []
    try:
        page.goto(search_url)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        
        # Wait a brief moment for dynamic card containers to render
        page.wait_for_timeout(3000)
        
        cards = page.locator(SELECTORS["job_card"]).all()
        logger.info(f"Found {len(cards)} job cards on page.")
        
        for idx, card in enumerate(cards):
            try:
                # Extracts elements relative to this card
                title_loc = card.locator(SELECTORS["job_title"]).first
                title_text = title_loc.inner_text(timeout=2000).strip()
                apply_url = title_loc.get_attribute("href")
                
                # In case apply_url doesn't start with http
                if apply_url and apply_url.startswith("/"):
                    apply_url = "https://www.naukri.com" + apply_url
                
                company_loc = card.locator(SELECTORS["company_name"]).first
                company_text = company_loc.inner_text(timeout=1000).strip() if company_loc.is_visible() else "Unknown Company"
                
                location_loc = card.locator(SELECTORS["location"]).first
                location_text = location_loc.inner_text(timeout=1000).strip() if location_loc.is_visible() else ""
                
                experience_loc = card.locator(SELECTORS["experience"]).first
                experience_text = experience_loc.inner_text(timeout=1000).strip() if experience_loc.is_visible() else ""
                
                # Extract posted date/freshness text
                post_date_loc = card.locator("span.job-post-day, .job-post-day, span.date").first
                post_date_text = "Anytime"
                try:
                    if post_date_loc.is_visible(timeout=500):
                        post_date_text = post_date_loc.inner_text().strip()
                except Exception:
                    pass

                jobs.append({
                    "title": title_text,
                    "company": company_text,
                    "location": location_text,
                    "experience": experience_text,
                    "apply_url": apply_url,
                    "description": "",  # Full description will be extracted from job page itself
                    "posted_time": post_date_text
                })
            except Exception as card_err:
                logger.warning(f"Skipping malformed job card #{idx+1} due to parsing error: {card_err}")
                continue
                
    except Exception as search_err:
        logger.error(f"Error searching jobs for {title} in {location}: {search_err}")
        
    return jobs

def get_already_processed_urls() -> set[str]:
    """
    Reads applied_log.csv to get a set of job URLs that have already been evaluated/applied.
    """
    processed = set()
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("apply_url") or row.get("url")
                    if url:
                        processed.add(url)
        except Exception as e:
            logger.warning(f"Could not read existing applied log: {e}")
    return processed

def log_application(job: dict, score_details: dict, applied: bool):
    """
    Appends job evaluation and apply outcome to the applied_log.csv file.
    """
    file_exists = os.path.exists(LOG_FILE)
    
    row = {
        "timestamp": datetime.now().isoformat(),
        "portal": "Naukri",
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "experience": job.get("experience", ""),
        "score": score_details.get("score", 0.0),
        "applied": "Yes" if applied else "No",
        "apply_url": job.get("apply_url", ""),
        "reasons": " | ".join(score_details.get("reasons", []))
    }
    
    try:
        with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logger.error(f"Failed to write to applied log: {e}")

def _handle_screening_questions(page: Page, job: dict, profile: dict, resume_keywords: set[str], score_details: dict):
    """
    Best-effort fill of screening questions modal/form.
    Uses dynamic cover letter/why interested generation if match details are available.
    Leaves unrecognized fields alone so user can intervene.
    """
    try:
        # Check if any screening modal/container is present
        modal = page.locator(SELECTORS["screening_questions"]).first
        if not modal.is_visible(timeout=2000):
            return
            
        logger.info("Screening questions detected. Attempting to autofill...")
        
        # Find all questions (usually labels paired with inputs/selects)
        # We look for form groups or standard question labels
        labels = page.locator("label, .question-label, .questionText").all()
        answers = profile.get("screening_answers", {})
        experience = profile.get("experience", {})
        
        for label_loc in labels:
            try:
                label_text = label_loc.inner_text().lower()
                if not label_text:
                    continue
                
                # Check for input element connected to this label or nested nearby
                # Commonly, Naukri has input/select in the same sibling block
                # Let's find inputs/selects relative to the label
                # In XPath: following-sibling::*[self::input or self::select or self::textarea] or similar
                # Let's find inputs matching by input name or nearby id
                for_id = label_loc.get_attribute("for")
                input_field = None
                if for_id:
                    input_field = page.locator(f"#{for_id}").first
                    
                if not input_field or not input_field.is_visible():
                    # Fallback: check children or adjacent inputs
                    # Search within sibling structure
                    # We can use parent-child search
                    parent = label_loc.locator("xpath=..")
                    input_field = parent.locator("input, select, textarea").first
                
                if not input_field or not input_field.is_visible():
                    continue
                    
                input_type = input_field.get_attribute("type") or ""
                input_type = input_type.lower()
                
                # 0. Why Interested / Cover letter (autofill dynamically based on matched keywords)
                if "interested" in label_text or "why this role" in label_text or "why do you want" in label_text or "suitability" in label_text or "cover letter" in label_text:
                    val = ""
                    if score_details and score_details.get("matched_keywords"):
                        matched = score_details["matched_keywords"]
                        top_matched = [m.title() for m in matched[:8]]
                        skills_str = ", ".join(top_matched)
                        title_val = job.get("title", "this position")
                        val = (
                            f"I am highly interested in the {title_val} role because it aligns perfectly with my background. "
                            f"I have hands-on experience and key matching skills that will enable me to contribute effectively, "
                            f"specifically in: {skills_str}."
                        )
                    else:
                        val = str(answers.get("why_interested", ""))
                        
                    if val:
                        input_field.fill(val)
                        logger.info(f"Filled Why Interested dynamically for question: '{label_text.strip()}'")
                
                # 1. Notice Period / Earliest Joining
                elif "notice" in label_text or "joining" in label_text or "earliest" in label_text:
                    # Notice period can be numeric input or dropdown select
                    val = str(experience.get("notice_period_days", 30))
                    if input_field.element_handle().as_element().tag_name == "select":
                        # For select dropdowns, try to select option matching the value
                        options = input_field.locator("option").all()
                        matched_opt = None
                        for opt in options:
                            opt_text = opt.inner_text().lower()
                            if val in opt_text or "30" in opt_text:  # default check
                                matched_opt = opt.get_attribute("value")
                                break
                        if matched_opt:
                            input_field.select_option(matched_opt)
                    else:
                        input_field.fill(val)
                    logger.info(f"Filled Notice Period for question: '{label_text.strip()}'")
                    
                # 2. Expected CTC
                elif "expected" in label_text and ("ctc" in label_text or "salary" in label_text):
                    val = str(answers.get("expected_ctc", ""))
                    if val:
                        input_field.fill(val)
                        logger.info(f"Filled Expected CTC for question: '{label_text.strip()}'")
                        
                # 3. Current CTC
                elif "current" in label_text and ("ctc" in label_text or "salary" in label_text):
                    val = str(experience.get("current_ctc", ""))
                    if val:
                        input_field.fill(val)
                        logger.info(f"Filled Current CTC for question: '{label_text.strip()}'")
                        
                # 4. Years of experience
                elif "experience" in label_text or "relevant" in label_text:
                    val = str(answers.get("years_of_relevant_experience", ""))
                    if val:
                        input_field.fill(val)
                        logger.info(f"Filled Experience for question: '{label_text.strip()}'")
                        
                # 5. Relocation Willingness (Yes/No radio/checkbox)
                elif "relocate" in label_text or "relocation" in label_text:
                    if profile.get("personal", {}).get("relocation_willingness", True):
                        # Find radio button for 'yes'
                        yes_radio = parent.locator("input[value*='yes'], input[value*='Yes'], input[id*='yes'], input[id*='Yes']").first
                        if yes_radio.is_visible():
                            yes_radio.click()
                            logger.info(f"Selected 'Yes' for relocation question: '{label_text.strip()}'")
                            
                # 6. Generic Custom Screening Question Fallback
                else:
                    # Determine if user has the skill in their resume or profile
                    has_skill = False
                    matched_skill = "general skills"
                    for skill in resume_keywords:
                        if len(skill) > 2 and skill in label_text:
                            has_skill = True
                            matched_skill = skill
                            break
                            
                    # Is it a Radio Button Yes/No choice?
                    radios = parent.locator("input[type='radio']").all()
                    if radios and len(radios) >= 2:
                        clicked = False
                        for radio in radios:
                            r_val = radio.get_attribute("value") or ""
                            r_id = radio.get_attribute("id") or ""
                            r_label = ""
                            try:
                                r_label = page.locator(f"label[for='{r_id}']").inner_text().lower()
                            except Exception:
                                pass
                            
                            target_match = "yes" if has_skill else "no"
                            if target_match in r_val.lower() or target_match in r_id.lower() or target_match in r_label:
                                radio.click()
                                logger.info(f"Answered '{target_match.upper()}' to radio question: '{label_text.strip()}'")
                                clicked = True
                                break
                        if not clicked:
                            # click yes by default for custom constraints if we are unsure
                            radios[0].click()
                            
                    # Is it a Select dropdown?
                    elif input_field.element_handle().as_element().tag_name == "select":
                        options = input_field.locator("option").all()
                        matched_opt = None
                        target_match = "yes" if has_skill else "no"
                        for opt in options:
                            opt_text = opt.inner_text().lower()
                            if target_match in opt_text:
                                matched_opt = opt.get_attribute("value")
                                break
                        if matched_opt:
                            input_field.select_option(matched_opt)
                            logger.info(f"Selected option matching '{target_match}' for question: '{label_text.strip()}'")
                        elif len(options) > 1:
                            input_field.select_option(index=1)
                            
                    # Is it a Text/Textarea input?
                    elif input_field.element_handle().as_element().tag_name in ["input", "textarea"]:
                        if any(term in label_text for term in ["year", "how many", "experience", "how long"]):
                            val = str(round(experience.get("total_years", 3.0))) if has_skill else "0"
                            input_field.fill(val)
                            logger.info(f"Answered '{val}' (years) to text question: '{label_text.strip()}'")
                        else:
                            val = f"Yes, I have experience with {matched_skill.title()}." if has_skill else "No, but I am a fast learner."
                            input_field.fill(val)
                            logger.info(f"Answered text response to question: '{label_text.strip()}'")
                            
            except Exception as e:
                logger.warning(f"Error handling individual screening question label: {e}")
                
        # Give a small delay so user can inspect and manually complete if needed
        logger.info("Questions autofilled. Waiting 5 seconds for user confirmation/intervention if necessary...")
        page.wait_for_timeout(5000)
        
    except Exception as e:
        logger.warning(f"Error in screening questions handler: {e}")

def apply_to_job(context: BrowserContext, page: Page, job: dict, profile: dict, resume_keywords: set[str], app_index: int) -> bool:
    """
    Opens the job detail page, extracts full description, scores the job,
    and applies if it matches threshold. Returns True if applied.
    """
    url = job.get("apply_url")
    if not url:
        logger.warning(f"Skipping job: No apply URL found for {job.get('title')} at {job.get('company')}")
        return False
        
    logger.info(f"Checking details for job: {job.get('title')} at {job.get('company')}")
    
    try:
        page.goto(url)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000) # Give dynamic text time to render
        
        # Check if the job posting is expired
        try:
            body_text_lower = page.locator("body").inner_text(timeout=2000).lower()
            if "job you are looking for is expired" in body_text_lower or "job is expired" in body_text_lower:
                logger.info("This job posting is expired. Skipping.")
                log_application(job, {
                    "score": 0.0,
                    "breakdown": {"title_score": 0.0, "experience_score": 0.0, "keyword_score": 0.0},
                    "reasons": ["Job posting is expired"],
                    "excluded": True
                }, False)
                return False
        except Exception:
            pass
            
        # 1. Check if already applied
        applied_msg = page.locator(SELECTORS["already_applied"]).first
        if applied_msg.is_visible(timeout=2000):
            logger.info("Already applied to this job. Logging and skipping.")
            # Log as not applied during this run, but record score details
            log_application(job, {"score": 100.0, "reasons": ["Already applied in a prior session"]}, False)
            return False
            
        # 2. Extract full job description and salary
        jd_loc = page.locator(SELECTORS["jd_text"]).first
        if jd_loc.is_visible():
            job["description"] = jd_loc.inner_text().strip()
        else:
            # Fallback: get all body text or main container text
            job["description"] = page.locator("body").inner_text()
            
        salary_loc = page.locator(SELECTORS["salary"]).first
        salary_text = "Not Disclosed"
        if salary_loc.is_visible():
            try:
                salary_text = salary_loc.inner_text(timeout=1000).strip()
            except Exception:
                pass
        job["salary"] = salary_text
            
        # 3. Score the job
        threshold = float(profile.get("auto_apply_settings", {}).get("match_threshold", 60))
        score_details = score_job(job, profile, resume_keywords)
        
        logger.info(f"Job Score: {score_details['score']}/100 (Threshold: {threshold})")
        for reason in score_details["reasons"]:
            logger.info(f" - {reason}")
            
        # 4. Handle matching result
        skill_match_pct = score_details.get("skill_match_pct", 0.0)
        title_score = score_details["breakdown"].get("title_score", 0.0)
        is_skill_match_pass = (skill_match_pct >= 40.0 and title_score > 0.0)
        
        if (score_details["score"] < threshold and not is_skill_match_pass) or score_details["excluded"]:
            status_tag = "[EXCLUDED]" if score_details["excluded"] else "[SKIPPED]"
            logger.info(f"==> {status_tag} Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 (Skill Match: {skill_match_pct}%) | Salary: {salary_text}")
            log_application(job, score_details, False)
            return False
            
        # Log if we bypassed total score threshold via skill match percentage
        if score_details["score"] < threshold and is_skill_match_pass:
            logger.info(f"==> [MATCH OVERRIDE] Total score {score_details['score']} < {threshold}, but skill match is {skill_match_pct}% (>= 40%) and job title is related. Proceeding to apply.")
            
        # If auto-apply is disabled in settings, log and skip apply step
        if not profile.get("auto_apply_settings", {}).get("enabled", False):
            logger.info(f"==> [SKIPPED - AUTO-APPLY DISABLED] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 | Salary: {salary_text}")
            log_application(job, score_details, False)
            return False
            
        # 5. Apply
        apply_btn = page.locator(SELECTORS["apply_button"]).first
        if not apply_btn.is_visible():
            logger.warning("Apply button not found on page. Could be already applied, expired, or custom DOM structure.")
            return False
            
        btn_text = apply_btn.inner_text().lower()
        if "apply on company site" in btn_text or "apply on website" in btn_text:
            logger.info(f"==> [SKIPPED - EXTERNAL REDIRECT] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 | Salary: {salary_text}")
            log_application(job, score_details, False)
            return False
            
        # Prepare to detect external redirection after clicking
        # Wait up to 5 seconds to see if it redirects to an external site or opens a new tab
        logger.info("Clicking Apply button...")
        
        # Listener for new tabs
        new_page = None
        try:
            with context.expect_page(timeout=5000) as new_page_info:
                apply_btn.click()
            new_page = new_page_info.value
        except TimeoutError:
            # No new page opened. Standard behavior for inline apply.
            pass
            
        if new_page:
            # An external page opened. Close it and skip.
            logger.info(f"==> [SKIPPED - EXTERNAL TAB] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 | Salary: {salary_text}")
            new_page.close()
            log_application(job, score_details, False)
            return False
            
        # Wait for page updates (redirection, modals, etc.)
        page.wait_for_timeout(3000)
        
        # Check if the main page URL redirected away from naukri.com
        current_url = page.url
        if "naukri.com" not in current_url:
            logger.info(f"==> [SKIPPED - EXTERNAL REDIRECT] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 | Salary: {salary_text}")
            log_application(job, score_details, False)
            return False
            
        # Handle screening questions modal if it pops up
        _handle_screening_questions(page, job, profile, resume_keywords, score_details)
        
        # Look for confirmation of success or if the button text changed to "Applied"
        page.wait_for_timeout(3000)
        
        # Check if confirmation elements are visible, or button has changed to 'Applied'
        success = False
        try:
            # 1. Check if the "already-applied" span/indicator is now visible on the page
            if page.locator("span#already-applied, .already-applied").first.is_visible(timeout=2000):
                success = True
            
            # 2. Check if the apply button itself now contains "applied"
            elif apply_btn.is_visible():
                new_btn_text = apply_btn.inner_text().lower()
                if "applied" in new_btn_text:
                    success = True
            
            # 3. Check for general body text success indicators
            if not success:
                success_indicators = [
                    "applied successfully", "application sent", "successfully applied", 
                    "already applied", "applied on", "applied"
                ]
                body_text = page.locator("body").inner_text().lower()
                for ind in success_indicators:
                    if ind in body_text:
                        success = True
                        break
        except Exception as e:
            logger.warning(f"Error checking application success state: {e}")
            
        if success:
            logger.info(f"==> [APPLIED #{app_index + 1}] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 | Salary: {salary_text}")
            log_application(job, score_details, True)
            return True
        else:
            logger.warning(f"==> [WARNING] Could not confirm if application was submitted successfully. Title: '{job['title']}' | Company: '{job['company']}'")
            # Log as not applied, but record
            log_application(job, score_details, False)
            return False
            
    except Exception as e:
        logger.error(f"Error applying to job {job.get('title')} at {job.get('company')}: {e}")
        # Log failure reason
        log_application(job, {"score": 0.0, "reasons": [f"Error occurred: {str(e)}"]}, False)
        return False

def run(profile: dict, resume_keywords: set[str]):
    """
    Main entry point for Naukri automation.
    Loops through combinations of target titles and locations.
    """
    logger.info("Initializing Naukri automation...")
    
    # Load settings
    auto_apply_cfg = profile.get("auto_apply_settings", {})
    max_apps = int(auto_apply_cfg.get("max_applications_per_run", 5))
    delay_range = [15, 30]
    
    target_titles = profile.get("search_preferences", {}).get("target_titles", [])
    target_locations = profile.get("search_preferences", {}).get("target_locations", [""])
    
    if not target_titles:
        logger.error("No target titles defined in search_preferences. Exiting.")
        return
        
    processed_urls = get_already_processed_urls()
    logger.info(f"Loaded {len(processed_urls)} already processed URLs from log.")
    
    applications_submitted = 0
    
    with sync_playwright() as p:
        # Launch headed chromium browser
        logger.info("Launching chromium browser (headed mode)...")
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        
        # Load session state if it exists
        if os.path.exists(SESSION_FILE):
            context = browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1366, "height": 768})
        else:
            context = browser.new_context(viewport={"width": 1366, "height": 768})
            
        page = context.new_page()
        
        # Ensure user is logged in
        if not ensure_logged_in(context, page):
            logger.error("Authentication failed. Closing browser.")
            browser.close()
            return
            
        # Loop titles x locations
        break_outer = False
        for title in target_titles:
            if break_outer:
                break
                
            for location in target_locations:
                if applications_submitted >= max_apps:
                    logger.info(f"Reached limit of {max_apps} applications for this run. Stopping.")
                    break_outer = True
                    break
                    
                logger.info(f"Starting job search for title: '{title}' and location: '{location}'")
                jobs = search_jobs(page, title, location)
                
                if not jobs:
                    logger.info("No jobs found or error searching this combination.")
                    continue
                    
                for job in jobs:
                    if applications_submitted >= max_apps:
                        logger.info(f"Reached limit of {max_apps} applications for this run. Stopping.")
                        break_outer = True
                        break
                        
                    url = job.get("apply_url")
                    if not url:
                        continue
                        
                    logger.info(f"Evaluating job card: '{job['title']}' at '{job['company']}'")
                        
                    # Apply freshness constraint if configured
                    freshness_setting = profile.get("search_preferences", {}).get("freshness", "anytime")
                    posted_text = job.get("posted_time", "Anytime")
                    if freshness_setting != "anytime":
                        days_ago = parse_freshness_to_days(posted_text)
                        max_days_allowed = 99999
                        if freshness_setting == "1_day":
                            max_days_allowed = 1
                        elif freshness_setting == "3_days":
                            max_days_allowed = 3
                        elif freshness_setting == "7_days":
                            max_days_allowed = 7
                        elif freshness_setting == "30_days":
                            max_days_allowed = 30
                            
                        if days_ago > max_days_allowed:
                            logger.info(f"==> [SKIPPED - FRESHNESS] Title: '{job['title']}' | Company: '{job['company']}' | Posted: {posted_text} (> {max_days_allowed} days ago)")
                            # Log it in applied_log as skipped due to freshness
                            log_application(job, {
                                "score": 0.0,
                                "breakdown": {"title_score": 0.0, "experience_score": 0.0, "keyword_score": 0.0},
                                "reasons": [f"Freshness Filter: Job posted {posted_text} (> {max_days_allowed} days ago)"],
                                "excluded": True
                            }, False)
                            continue
                        
                    if url in processed_urls:
                        logger.info(f"==> [SKIPPED - DUPLICATE] Title: '{job['title']}' | Company: '{job['company']}' (Already processed in prior session)")
                        continue
                        
                    # Add to processed list for this run
                    processed_urls.add(url)
                    
                    # Open JDP and evaluate/apply
                    applied = apply_to_job(context, page, job, profile, resume_keywords, applications_submitted)
                    
                    if applied:
                        applications_submitted += 1
                        
                        # Wait random human-like delay between positive submissions
                        sleep_time = random.uniform(delay_range[0], delay_range[1])
                        logger.info(f"Sleeping for {sleep_time:.1f} seconds to simulate human pacing...")
                        time.sleep(sleep_time)
                        
                    # A small baseline delay to avoid overloading the browser page transitions
                    time.sleep(2)
                    
        if applications_submitted >= max_apps:
            logger.info(f"Automation completed. Reached your run limit of {max_apps} applications.")
        else:
            logger.info("Automation completed. All matching jobs for your target roles and locations have been processed. No more applications are there for this role.")
        page.wait_for_timeout(5000) # Give user a moment to look
        browser.close()
