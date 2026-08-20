import os
import csv
import json
import time
import random
import logging

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError
from matcher import evaluate_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dearbobby_indeed")

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_FILE = os.path.join(WORKSPACE_ROOT, "indeed_session.json")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "applied_log.csv")

SELECTORS = {
    "search_title": "#text-input-what",
    "search_location": "#text-input-where",
    "search_button": "button[type='submit']",
    "job_card": "div.job_seen_beacon, td.resultContent",
    "job_title": "h2.jobTitle a, a.jcs-JobTitle",
    "company_name": "[data-testid='company-name'], span.companyName",
    "location": "[data-testid='text-location'], div.companyLocation",
    "posted_date": "[data-testid='myJobsStateDate'], span.date",
    "jd_container": "#jobDescriptionText, div.jobsearch-JobComponent-description",
    "apply_button": "button#indeedApplyButton, div[id*='indeedApply'] button, button.jobsearch-IndeedApplyButton-newDesign"
}

def parse_freshness_to_days(posted_text: str) -> float:
    if not posted_text:
        return 0.0
    txt = posted_text.lower().strip()
    if "just posted" in txt or "today" in txt or "employer" in txt:
        return 0.0
    import re
    match = re.search(r"(\d+)\+?\s*day", txt)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+)\+?\s*hour", txt)
    if match:
        return float(match.group(1)) / 24.0
    return 0.0

def load_processed_urls() -> set:
    processed = set()
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("url")
                    if url:
                        processed.add(url)
        except Exception as e:
            logger.warning(f"Failed to read applied_log.csv: {e}")
    return processed

def log_application(job: dict, score_details: dict, applied: bool):
    file_exists = os.path.exists(LOG_FILE)
    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "company": job.get("company", "Unknown"),
        "title": job.get("title", "Unknown"),
        "location": job.get("location", "Unknown"),
        "score": score_details.get("score", 0.0),
        "applied": "Yes" if applied else "No",
        "reasons": " | ".join(score_details.get("reasons", [])),
        "url": job.get("apply_url", ""),
        "portal": "Indeed"
    }
    try:
        with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            fieldnames = ["timestamp", "company", "title", "location", "score", "applied", "reasons", "url", "portal"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logger.error(f"Failed to write to applied_log.csv: {e}")

def handle_screening_questions(page: Page, profile: dict, resume_keywords: set):
    try:
        labels = page.locator("label, legend, fieldset label").all()
        answers = profile.get("screening_answers", {})
        experience = profile.get("experience", {})
        is_fresher = experience.get("is_fresher", False)
        
        for label_loc in labels:
            try:
                label_text = label_loc.inner_text().lower()
                if not label_text:
                    continue
                
                parent = label_loc.locator("xpath=..")
                input_field = parent.locator("input, select, textarea").first
                if not input_field.is_visible():
                    continue

                has_skill = False
                matched_skill = "general skills"
                for skill in resume_keywords:
                    if len(skill) > 2 and skill in label_text:
                        has_skill = True
                        matched_skill = skill
                        break

                # 1. Why Interested
                if "interested" in label_text or "why this role" in label_text or "cover letter" in label_text:
                    val = str(answers.get("why_interested", "")) or f"I am passionate about this role and have hands-on experience with {matched_skill.title()}."
                    input_field.fill(val)

                # 2. Expected CTC
                elif "expected" in label_text and ("ctc" in label_text or "salary" in label_text):
                    val = str(answers.get("expected_ctc", "")) or ("As per company standards" if is_fresher else "")
                    if val:
                        input_field.fill(val)

                # 3. Current CTC
                elif "current" in label_text and ("ctc" in label_text or "salary" in label_text):
                    val = "0 (Fresher)" if is_fresher else (str(answers.get("current_ctc", "")) or str(experience.get("current_ctc", "")))
                    if val:
                        input_field.fill(val)

                # 4. Notice Period / Joining
                elif "notice" in label_text or "joining" in label_text or "earliest" in label_text:
                    val = str(answers.get("earliest_joining_date", "Immediate"))
                    input_field.fill(val)

                # 5. Experience
                elif "experience" in label_text or "years" in label_text:
                    val = "0" if is_fresher else (str(answers.get("years_of_relevant_experience", "")) or str(round(experience.get("total_years", 3.0))))
                    input_field.fill(val)

                else:
                    radios = parent.locator("input[type='radio']").all()
                    if radios and len(radios) >= 2:
                        target_match = "yes" if has_skill else "no"
                        clicked = False
                        for radio in radios:
                            r_val = radio.get_attribute("value") or ""
                            r_id = radio.get_attribute("id") or ""
                            if target_match in r_val.lower() or target_match in r_id.lower():
                                radio.click()
                                clicked = True
                                break
                        if not clicked:
                            radios[0].click()

                    elif input_field.element_handle().as_element().tag_name == "select":
                        options = input_field.locator("option").all()
                        target_match = "yes" if has_skill else "no"
                        matched_opt = None
                        for opt in options:
                            if target_match in opt.inner_text().lower():
                                matched_opt = opt.get_attribute("value")
                                break
                        if matched_opt:
                            input_field.select_option(matched_opt)
                        elif len(options) > 1:
                            input_field.select_option(index=1)

                    elif input_field.element_handle().as_element().tag_name in ["input", "textarea"]:
                        val = f"Yes, I have experience with {matched_skill.title()}." if has_skill else "No, but I am a fast learner."
                        input_field.fill(val)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error handling Indeed screening questions: {e}")

def search_jobs(page: Page, title: str, location: str) -> list:
    url = f"https://in.indeed.com/jobs?q={title}&l={location}"
    logger.info(f"Navigating to Indeed India: {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    jobs = []
    cards = page.locator(SELECTORS["job_card"]).all()
    logger.info(f"Found {len(cards)} job cards on Indeed page.")
    
    for card in cards:
        try:
            title_elem = card.locator(SELECTORS["job_title"]).first
            if not title_elem.is_visible():
                continue
            
            job_title = title_elem.inner_text().strip()
            href = title_elem.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = "https://in.indeed.com" + href
                
            company_elem = card.locator(SELECTORS["company_name"]).first
            company = company_elem.inner_text().strip() if company_elem.is_visible() else "Unknown"
            
            loc_elem = card.locator(SELECTORS["location"]).first
            loc = loc_elem.inner_text().strip() if loc_elem.is_visible() else location
            
            date_elem = card.locator(SELECTORS["posted_date"]).first
            posted_text = date_elem.inner_text().strip() if date_elem.is_visible() else "Anytime"
            
            jobs.append({
                "title": job_title,
                "company": company,
                "location": loc,
                "posted_time": posted_text,
                "apply_url": href,
                "card_elem": card
            })
        except Exception as e:
            logger.warning(f"Error parsing Indeed card: {e}")
            
    return jobs

def run(profile: dict, resume_keywords: set):
    logger.info("Initializing Playwright session for Indeed India...")
    search_prefs = profile.get("search_preferences", {})
    titles = search_prefs.get("target_titles", ["Digital Marketing Specialist"])
    locations = search_prefs.get("target_locations", ["Hyderabad"])
    max_apps = profile.get("auto_apply_settings", {}).get("max_applications_per_run", 5)
    threshold = float(profile.get("auto_apply_settings", {}).get("match_threshold", 60))
    freshness_setting = search_prefs.get("freshness", "anytime")

    processed_urls = load_processed_urls()
    applications_submitted = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        
        if os.path.exists(SESSION_FILE):
            try:
                context = browser.new_context(storage_state=SESSION_FILE)
                logger.info("Loaded cached Indeed session storage state.")
            except Exception:
                context = browser.new_context()
        else:
            context = browser.new_context()
            
        page = context.new_page()

        try:
            for title in titles:
                for location in locations:
                    if applications_submitted >= max_apps:
                        break
                    
                    jobs = search_jobs(page, title, location)
                    for job in jobs:
                        if applications_submitted >= max_apps:
                            break
                            
                        url = job.get("apply_url")
                        if not url or url in processed_urls:
                            if url:
                                logger.info(f"==> [SKIPPED - DUPLICATE] Title: '{job['title']}' | Company: '{job['company']}' (Indeed)")
                            continue
                            
                        logger.info(f"Evaluating job card: '{job['title']}' at '{job['company']}' (Indeed)")
                        
                        # Freshness check
                        posted_text = job.get("posted_time", "Anytime")
                        if freshness_setting != "anytime":
                            days_ago = parse_freshness_to_days(posted_text)
                            max_days = 1 if freshness_setting == "1_day" else (3 if freshness_setting == "3_days" else (7 if freshness_setting == "7_days" else 30))
                            if days_ago > max_days:
                                logger.info(f"==> [SKIPPED - FRESHNESS] Title: '{job['title']}' | Company: '{job['company']}' | Posted: {posted_text}")
                                log_application(job, {"score": 0.0, "reasons": [f"Freshness Filter: > {max_days} days"]}, False)
                                continue

                        # Open JD
                        try:
                            job["card_elem"].click()
                            page.wait_for_timeout(2500)
                        except Exception:
                            page.goto(url, wait_until="domcontentloaded")
                            page.wait_for_timeout(2500)

                        jd_loc = page.locator(SELECTORS["jd_container"]).first
                        jd_text = jd_loc.inner_text() if jd_loc.is_visible() else ""

                        score_details = evaluate_job(job, jd_text, profile, resume_keywords)
                        skill_match_pct = score_details.get("skill_match_pct", 0.0)
                        title_score = score_details["breakdown"].get("title_score", 0.0)
                        is_skill_match_pass = (skill_match_pct >= 40.0 and title_score > 0.0)

                        if (score_details["score"] < threshold and not is_skill_match_pass) or score_details.get("excluded"):
                            logger.info(f"==> [SKIPPED] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 (Indeed)")
                            log_application(job, score_details, False)
                            processed_urls.add(url)
                            continue

                        # Check Easily Apply
                        apply_btn = page.locator(SELECTORS["apply_button"]).first
                        if not apply_btn.is_visible():
                            logger.info(f"==> [SKIPPED - EXTERNAL REDIRECT] Title: '{job['title']}' | Company: '{job['company']}' (Indeed)")
                            log_application(job, score_details, False)
                            processed_urls.add(url)
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)
                        handle_screening_questions(page, profile, resume_keywords)

                        applications_submitted += 1
                        logger.info(f"==> [APPLIED #{applications_submitted}] Title: '{job['title']}' | Company: '{job['company']}' | Score: {score_details['score']}/100 (Indeed)")
                        log_application(job, score_details, True)
                        processed_urls.add(url)

                        delay = random.uniform(15, 30)
                        logger.info(f"Pacing delay: Waiting {delay:.1f}s before next application...")
                        page.wait_for_timeout(int(delay * 1000))

        finally:
            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
            browser.close()
            logger.info("Indeed automation run completed.")
