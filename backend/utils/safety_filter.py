def is_safe_query(query: str) -> bool:
    """Prevent harmful instructions."""
    unsafe_keywords = [
        "suicide", "drugs", "alcohol", "gambling",
        "haram", "racism", "self-harm", "porn", "kill"
    ]
    return not any(word in query.lower() for word in unsafe_keywords)
