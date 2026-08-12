import re
from resume_parser import tokenize

def parse_experience_range(exp_str: str) -> tuple[float | None, float | None]:
    """
    Parses experience range from an experience string (e.g. '2 - 7 Yrs', '5+ years').
    Returns (min_exp, max_exp).
    """
    if not exp_str:
        return None, None
        
    s = exp_str.lower()
    
    # Pattern for "2 - 7 years" or "2 to 7 Yrs"
    range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years|yrs|yr|year)?', s)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))
        
    # Pattern for "5+ years" or "5+ yrs"
    plus_match = re.search(r'(\d+(?:\.\d+)?)\s*\+\s*(?:years|yrs|yr|year)?', s)
    if plus_match:
        return float(plus_match.group(1)), None
        
    # Pattern for "minimum 3 years" or "3 years exp"
    single_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:years|yrs|yr|year)', s)
    if single_match:
        return float(single_match.group(1)), None
        
    return None, None

def find_experience_in_text(text: str) -> tuple[float | None, float | None]:
    """
    Scans a block of text for patterns matching experience ranges.
    Returns the first matching (min_exp, max_exp).
    """
    if not text:
        return None, None
        
    # Look for "2-5 years", "2 to 5 yrs", "3+ years of experience", etc.
    patterns = [
        r'\b(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years|yrs|yr|year)\b',
        r'\b(\d+)\s*\+\s*(?:years|yrs|yr|year)\b',
        r'(?:experience|exp)\s*(?:of|required)?\s*[:\-]?\s*(\d+)\s*(?:years|yrs|yr|year)?\b'
    ]
    
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            groups = match.groups()
            if len(groups) == 2 and groups[1] is not None:
                return float(groups[0]), float(groups[1])
            elif len(groups) >= 1 and groups[0] is not None:
                # If it's like "3+", min is 3, max is None
                return float(groups[0]), None
                
    return None, None

def score_job(job: dict, profile: dict, resume_keywords: set[str]) -> dict:
    """
    Scores a job posting against the user's profile and resume.
    Returns: {
        "score": float,
        "breakdown": {
            "title_score": float,
            "experience_score": float,
            "keyword_score": float
        },
        "reasons": list[str],
        "excluded": bool
    }
    """
    job_title = job.get("title", "")
    jd_text = job.get("description", "")
    
    reasons = []
    
    # ----------------------------------------------------
    # Hard-filter: Exclude keywords
    # ----------------------------------------------------
    exclude_keywords = profile.get("search_preferences", {}).get("exclude_keywords", [])
    
    # Perform case-insensitive word boundary check for each exclude keyword
    for kw in exclude_keywords:
        pattern = rf"\b{re.escape(kw.lower())}\b"
        if re.search(pattern, job_title.lower()) or re.search(pattern, jd_text.lower()):
            reasons.append(f"Hard-filtered: matched exclude keyword '{kw}'")
            return {
                "score": 0.0,
                "breakdown": {"title_score": 0.0, "experience_score": 0.0, "keyword_score": 0.0},
                "reasons": reasons,
                "excluded": True
            }

    # ----------------------------------------------------
    # 1. Job Title Similarity (35% weight)
    # ----------------------------------------------------
    target_titles = profile.get("search_preferences", {}).get("target_titles", [])
    job_title_tokens = tokenize(job_title)
    
    max_title_similarity = 0.0
    best_matching_title = None
    
    for target in target_titles:
        target_tokens = tokenize(target)
        if not target_tokens:
            continue
        # Overlap: fraction of target title tokens present in job title
        overlap_tokens = target_tokens & job_title_tokens
        similarity = len(overlap_tokens) / len(target_tokens)
        if similarity > max_title_similarity:
            max_title_similarity = similarity
            best_matching_title = target
            
    title_score = max_title_similarity * 35.0
    if max_title_similarity > 0:
        reasons.append(f"Title similarity matches '{best_matching_title}' ({max_title_similarity:.0%} overlap, +{title_score:.1f}/35)")
    else:
        reasons.append(f"No similarity with target titles (+0.0/35)")

    # ----------------------------------------------------
    # 2. Experience Match (25% weight)
    # ----------------------------------------------------
    user_exp = float(profile.get("experience", {}).get("total_years", 0))
    is_fresher = bool(profile.get("experience", {}).get("is_fresher", False))
    if is_fresher:
        user_exp = 0.0
    
    # Try parsing from job's experience field first, then fall back to scanning the description text
    min_exp, max_exp = parse_experience_range(job.get("experience", ""))
    if min_exp is None and max_exp is None:
        min_exp, max_exp = find_experience_in_text(jd_text)
        
    experience_score = 25.0  # default to pass if no range stated
    
    if min_exp is not None:
        if is_fresher:
            if min_exp <= 1:
                experience_score = 25.0
                reasons.append(f"Experience fit: User is marked as Fresher, meeting entry-level requirement {min_exp}-{max_exp if max_exp else ''}y (+25.0/25)")
            else:
                experience_score = 0.0
                reasons.append(f"Experience misfit: Job requires {min_exp}y+ experience, user is marked as Fresher (+0.0/25)")
        else:
            if max_exp is not None:
                # Check if user exp falls within min/max
                # Allow minor tolerance (e.g. user has slightly more experience, but not under min)
                if min_exp <= user_exp <= max_exp:
                    reasons.append(f"Experience fit: User exp {user_exp}y is within JD range {min_exp}-{max_exp}y (+25.0/25)")
                elif user_exp > max_exp:
                    # Overqualified: give partial points or pass depending on range
                    # Let's count it as a pass because recruiters rarely filter out minor overqualification automatically,
                    # but if user exp is way higher (e.g. range is 1-3y, user has 8y), give 0.
                    if user_exp - max_exp <= 2.0:
                        reasons.append(f"Experience fit: User exp {user_exp}y slightly exceeds JD range {min_exp}-{max_exp}y (+25.0/25)")
                    else:
                        experience_score = 0.0
                        reasons.append(f"Experience misfit: User exp {user_exp}y exceeds JD range {min_exp}-{max_exp}y (+0.0/25)")
                else:
                    experience_score = 0.0
                    reasons.append(f"Experience misfit: User exp {user_exp}y is below JD range {min_exp}-{max_exp}y (+0.0/25)")
            else:
                # Only min experience is specified (e.g., "3+ years")
                if user_exp >= min_exp:
                    reasons.append(f"Experience fit: User exp {user_exp}y meets JD min requirement {min_exp}y+ (+25.0/25)")
                else:
                    experience_score = 0.0
                    reasons.append(f"Experience misfit: User exp {user_exp}y is below JD min requirement {min_exp}y+ (+0.0/25)")
    else:
        reasons.append(f"Experience requirement not stated in JD, default to pass (+25.0/25)")

    # ----------------------------------------------------
    # 3. Keyword Match (40% weight)
    # ----------------------------------------------------
    # Merge resume keywords and explicit skills in profile
    combined_user_keywords = resume_keywords.copy()
    
    # Add skills explicitly listed in profile.json
    skills_config = profile.get("skills", {})
    for skill_list in ["primary", "secondary"]:
        for skill in skills_config.get(skill_list, []):
            combined_user_keywords.update(tokenize(skill))
            
    jd_tokens = tokenize(jd_text)
    matched_keywords = combined_user_keywords & jd_tokens
    
    target_matches = int(profile.get("matcher_settings", {}).get("target_keyword_matches", 15))
    if len(matched_keywords) >= target_matches:
        keyword_score = 40.0
    else:
        keyword_score = (len(matched_keywords) / target_matches) * 40.0 if target_matches > 0 else 40.0
        
    matched_list_str = ", ".join(list(matched_keywords)[:12])
    if len(matched_keywords) > 12:
        matched_list_str += ", ..."
        
    reasons.append(
        f"Keyword overlap: Matched {len(matched_keywords)} keywords. "
        f"({matched_list_str}) (+{keyword_score:.1f}/40)"
    )

    # Compute profile skills match percentage
    user_skills_set = set()
    skills_config = profile.get("skills", {})
    for skill_list in ["primary", "secondary"]:
        for skill in skills_config.get(skill_list, []):
            user_skills_set.add(skill.lower().strip())
            
    jd_text_lower = jd_text.lower()
    matched_profile_skills = []
    for skill in user_skills_set:
        if skill:
            pattern = rf"\b{re.escape(skill)}\b"
            if re.search(pattern, jd_text_lower):
                matched_profile_skills.append(skill)
                
    total_profile_skills = len(user_skills_set)
    profile_skills_match = (len(matched_profile_skills) / total_profile_skills * 100.0) if total_profile_skills > 0 else 0.0
    
    # Calculate resume keyword match ratio relative to target matches
    resume_keywords_match = (len(matched_keywords) / target_matches * 100.0) if target_matches > 0 else 100.0
    
    # Take the best match percentage
    skill_match_pct = max(profile_skills_match, resume_keywords_match)

    total_score = title_score + experience_score + keyword_score
    # Cap score at 100
    total_score = min(100.0, total_score)
    
    return {
        "score": round(total_score, 1),
        "breakdown": {
            "title_score": round(title_score, 1),
            "experience_score": round(experience_score, 1),
            "keyword_score": round(keyword_score, 1)
        },
        "reasons": reasons,
        "excluded": False,
        "matched_keywords": list(matched_keywords),
        "skill_match_pct": round(skill_match_pct, 1)
    }
