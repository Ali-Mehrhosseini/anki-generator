import re
import unicodedata
def _normalize_production_sentence(value: str) -> str:
    normalized = unicodedata.normalize("NFC", str(value or ""))
    normalized = " ".join(normalized.split())
    return re.sub(r"\s+([,.;:!?])", r"\1", normalized)

c = _normalize_production_sentence("Goditi la festa!")
t = _normalize_production_sentence("Goditi la festa!")
print(c == t)
