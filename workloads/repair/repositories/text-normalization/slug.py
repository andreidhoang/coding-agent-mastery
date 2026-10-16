"""Small owned demonstration repository with a reproducible normalization defect."""


def normalize_slug(text):
    """Return lowercase ASCII words separated by one hyphen."""
    return text.lower().strip().replace(" ", "-")
