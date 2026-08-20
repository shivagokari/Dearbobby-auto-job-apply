import os
import json
import sys
import logging
from resume_parser import parse_resume
from portals import naukri, indeed, foundit

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dearbobby_main")

def main():
    logger.info("Starting DearBobby Job Auto-Apply Assistant...")
    
    # 1. Check profile.json
    profile_path = "profile.json"
    if not os.path.exists(profile_path):
        logger.error(f"Configuration file '{profile_path}' is missing. Please create it from the template.")
        sys.exit(1)
        
    try:
        with open(profile_path, mode="r", encoding="utf-8") as f:
            profile = json.load(f)
    except json.JSONDecodeError as jde:
        logger.error(f"Error parsing profile.json: {jde}")
        sys.exit(1)
        
    # Check if the user hasn't replaced the template defaults
    personal = profile.get("personal", {})
    if personal.get("email") == "bobby.shaheed@example.com" or personal.get("phone") == "+919876543210":
        logger.error("WARNING: It looks like you are using the default values in profile.json.")
        logger.error("Please fill in your actual details (email, phone, target_titles, etc.) before running.")
        sys.exit(1)
        
    # 2. Find and parse resume
    # Check for resume.pdf or resume.docx
    resume_path = None
    possible_resumes = ["resume.pdf", "resume.docx", "resume.doc"]
    for pr in possible_resumes:
        if os.path.exists(pr):
            resume_path = pr
            break
            
    if not resume_path:
        logger.error("No resume file found! Please drop 'resume.pdf' or 'resume.docx' in the project folder.")
        sys.exit(1)
        
    logger.info(f"Parsing resume: {resume_path}...")
    try:
        raw_text, resume_keywords = parse_resume(resume_path)
        logger.info(f"Resume parsed successfully. Extracted {len(resume_keywords)} keywords.")
    except Exception as e:
        logger.error(f"Failed to parse resume: {e}")
        sys.exit(1)
        
    # 3. Trigger automation portals
    try:
        active_portals = profile.get("search_preferences", {}).get("portals", ["naukri"])
        if isinstance(active_portals, str):
            active_portals = [active_portals]
            
        if "all" in active_portals:
            active_portals = ["naukri", "indeed", "foundit"]
            
        logger.info(f"Active portals selected for this run: {', '.join(active_portals)}")
        
        for portal_name in active_portals:
            p_name = portal_name.lower().strip()
            if p_name == "naukri":
                logger.info(">>> Starting Naukri.com automation run...")
                naukri.run(profile, resume_keywords)
            elif p_name == "indeed":
                logger.info(">>> Starting Indeed India automation run...")
                indeed.run(profile, resume_keywords)
            elif p_name == "foundit":
                logger.info(">>> Starting Foundit India automation run...")
                foundit.run(profile, resume_keywords)
            else:
                logger.warning(f"Unrecognized portal '{portal_name}'. Skipping.")

    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting gracefully.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during the automation run: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
