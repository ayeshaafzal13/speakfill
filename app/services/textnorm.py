"""Text normalisation: Urdu/Arabic digits -> ASCII, spoken digit words -> digits."""
import re

_DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

DIGIT_WORDS = {
    # Roman Urdu / English
    "sifar": "0", "zero": "0", "seefar": "0",
    "ek": "1", "aik": "1", "one": "1",
    "do": "2", "two": "2",
    "teen": "3", "tin": "3", "three": "3",
    "char": "4", "chaar": "4", "four": "4",
    "panch": "5", "paanch": "5", "five": "5",
    "che": "6", "chay": "6", "chhe": "6", "chey": "6", "six": "6",
    "saat": "7", "sat": "7", "seven": "7",
    "aath": "8", "ath": "8", "eight": "8",
    "nau": "9", "nine": "9",
    # Urdu script
    "صفر": "0", "ایک": "1", "دو": "2", "تین": "3", "چار": "4",
    "پانچ": "5", "چھ": "6", "سات": "7", "آٹھ": "8", "نو": "9",
}

_MIN_RUN = 4  # need 4+ digit words in a row before we treat them as a number


def _strip(tok: str) -> str:
    return tok.strip(" ,.;:-،۔").lower()


def spoken_digits_to_numbers(text: str) -> str:
    """'ek teen char panch' -> '1345' (only for runs of 4+ digit words, so 'do' alone is safe)."""
    parts = re.split(r"(\s+)", text)
    out, i = [], 0
    while i < len(parts):
        tok = parts[i]
        if tok.strip() and (_strip(tok) in DIGIT_WORDS or re.fullmatch(r"\d", _strip(tok))):
            run, j, has_word = [], i, False
            while j < len(parts):
                t = parts[j]
                if not t.strip():  # whitespace between tokens
                    j += 1
                    continue
                s = _strip(t)
                if s in DIGIT_WORDS:
                    run.append(DIGIT_WORDS[s])
                    has_word = True
                elif re.fullmatch(r"\d", s):
                    run.append(s)
                else:
                    break
                j += 1
            if len(run) >= _MIN_RUN and has_word:
                out.append("".join(run) + " ")
                i = j
                continue
        out.append(tok)
        i += 1
    return "".join(out).strip()


def normalize_text(text: str) -> str:
    text = (text or "").translate(_DIGIT_MAP)
    text = text.replace("،", ",").replace("۔", ".")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return spoken_digits_to_numbers(text)
