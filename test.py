import re
def _find_production_form(sentence: str, form: str):
    import unicodedata
    normalized_sentence = unicodedata.normalize("NFC", str(sentence or ""))
    normalized_form = unicodedata.normalize("NFC", str(form or "")).strip()
    pieces = re.split(r"\s+", normalized_form)
    pattern = r"\s+".join(re.escape(piece) for piece in pieces)
    if normalized_form[0].isalnum():
        pattern = rf"(?<!\w){pattern}"
    if normalized_form[-1].isalnum():
        pattern = rf"{pattern}(?!\w)"
    return re.search(pattern, normalized_sentence, flags=re.IGNORECASE)

missing_form = "Goditi"
tts_example = "Goditi la festa!"
sentence_gap = "_____ la festa!"

gap_matches = list(re.finditer(r"(?<!_)_____(?!_)", sentence_gap))
gap_match = gap_matches[0]
before = sentence_gap[:gap_match.start()]
after = sentence_gap[gap_match.end():]
print(f"before={repr(before)} after={repr(after)}")
if not ((before and before[-1].isalnum()) or (after and after[0].isalnum())):
    completed = f"{before}{missing_form}{after}"
    print(f"completed={repr(completed)}")

print("find:", _find_production_form(tts_example, missing_form))
