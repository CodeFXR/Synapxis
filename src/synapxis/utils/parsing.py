import re
from typing import List

def extract_links(content: str) -> List[str]:
    """Extracts all [[Wikilinks]] from a string."""
    if not content:
        return []
    matches = re.findall(r"\[\[(.*?)\]\]", content)
    return [m.split("|")[0].strip() for m in matches if m.strip()]

def extract_tags(content: str) -> List[str]:
    """Extracts all #hashtags from a string."""
    if not content:
        return []
    # Matches #tag but allows alphanumeric and underscores. 
    # Ignores if part of a url like anchor # link
    # Simple regex for now: #word
    matches = re.findall(r"#(\w+)", content)
    # Remove duplicates and lowercase
    return list(set(m.lower() for m in matches))
