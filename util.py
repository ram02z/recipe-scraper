def singularise_word(word):
    SINGULAR_SUFFIX = [
        ("us", "us"),
        ("ss", "ss"),
        ("is", "is"),
        ("'s", "'s"),
        ("ies", "y"),
        ("es", "e"),
        ("s", ""),
    ]
    for suffix, singular_suffix in SINGULAR_SUFFIX:
        if word.endswith(suffix):
            return word[: -len(suffix)] + singular_suffix
    return word
