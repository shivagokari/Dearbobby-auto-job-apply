import os
import re

# Hardcoded list of standard English stopwords to avoid external package dependencies
STOPWORDS = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself",
    "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this", "that",
    "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because",
    "as", "until", "while", "of", "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just",
    "don", "should", "now", "also"
}

def tokenize(text: str) -> set[str]:
    """
    Tokenizes raw text into a set of lowercase keywords.
    Preserves technical tokens like node.js, c++, c#, ci/cd, .net, etc.
    """
    if not text:
        return set()
    
    # Regex explanation:
    # \.?[a-zA-Z0-9]+        - Match optional leading dot (for .net), followed by alphanumeric chars
    # (?:[+#./-][a-zA-Z0-9]+)* - Match optional sub-parts starting with +, #, ., /, or - followed by alphanumeric (e.g. node.js, ci/cd)
    # [+#]*                  - Match trailing + or # (for c++, c#)
    pattern = r'\.?[a-zA-Z0-9]+(?:[+#./-][a-zA-Z0-9]+)*[+#]*'
    
    tokens = re.findall(pattern, text.lower())
    
    # Filter out stopwords and purely numeric tokens (unless relevant, but usually year numbers aren't key skills)
    # We also discard single character tokens unless they are common programming languages like 'c' or 'r'
    filtered_tokens = set()
    for token in tokens:
        # Strip trailing punctuation and leading dashes/slashes, keeping leading dots (e.g., .net)
        token = token.rstrip(".-/").lstrip("-/")
        if not token:
            continue
        if token in STOPWORDS:
            continue
        if token.isdigit() and len(token) != 4:  # Keep 4-digit years maybe, but discard others
            continue
        if len(token) == 1 and token not in {"c", "r"}:
            continue
        filtered_tokens.add(token)
        
    return filtered_tokens

def parse_resume(path: str) -> tuple[str, set[str]]:
    """
    Parses a PDF or DOCX resume, returning the raw text and a set of lowercase keywords.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Resume file not found at path: {path}")
        
    _, ext = os.path.splitext(path.lower())
    raw_text = ""
    
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            raw_text = "\n".join(pages_text)
            
    elif ext in (".docx", ".doc"):
        import docx2txt
        raw_text = docx2txt.process(path)
        
    else:
        raise ValueError(f"Unsupported resume file format: {ext}. Only PDF and DOCX are supported.")
        
    keyword_set = tokenize(raw_text)
    return raw_text, keyword_set
