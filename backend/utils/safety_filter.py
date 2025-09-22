import re

def is_safe_query(query: str) -> bool:
    """Prevent harmful instructions with more nuanced filtering."""
    # Convert to lowercase for case-insensitive matching
    lower_query = query.lower()
    
    # List of unsafe keywords with context consideration
    unsafe_patterns = [
        r"\b(suicide|kill myself|end my life|want to die)\b",
        r"\b(self-harm|self injury|cutting myself)\b",
        r"\b(abuse|overdose|poison)\b",
        # Less restrictive patterns for substances that might be discussed in recovery context
        r"\b(use|buy|get|make)(.*\b)(heroin|cocaine|meth|fentanyl|lsd)\b",
    ]
    
    # Check for unsafe patterns
    for pattern in unsafe_patterns:
        if re.search(pattern, lower_query):
            return False
    
    # Additional context-based filtering could be added here
    
    return True