import re
from datetime import datetime
from decimal import Decimal

_SMALL = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_WORD_PATTERN = "|".join([*_SMALL, *_TENS, "hundred", "thousand"])
_NUMBER_RUN = re.compile(rf"\b(?:{_WORD_PATTERN})(?:\s+(?:{_WORD_PATTERN}))*\b")
_OH_DIGIT = re.compile(r"\boh\s+(one|two|three|four|five|six|seven|eight|nine)\b")
_DOLLARS_AND_CENTS = re.compile(r"(\d+)\s*dollars?\s+and\s+(\d{1,2})\s*cents?")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# "Thirteen eighty" is how people say 1380.
_SPOKEN_HUNDREDS = re.compile(r"\b(\d{1,2}) (\d{2})\b")


def read_back_text(shop_name: str, estimate: Decimal, start_time: datetime) -> str:
    """The words the agent is asked to say, which `read_back_matches` always accepts."""
    hour = start_time.hour % 12 or 12
    period = "AM" if start_time.hour < 12 else "PM"
    day = start_time.strftime("%A")
    return (
        f"{shop_name}, ${estimate:,.2f}, starting {day} at {hour}:{start_time.minute:02d} {period}"
    )


def _words_to_digits(run: str) -> str:
    """Turn a run of number words into digits, keeping separate numbers apart, so "one thousand
    three hundred eighty" is 1380 and "five fifteen" stays 5 and 15."""
    numbers: list[int] = []
    total = 0
    group: int | None = None

    def flush() -> None:
        nonlocal total, group
        if group is not None or total:
            numbers.append(total + (group or 0))
        total, group = 0, None

    for word in run.split():
        if word == "hundred":
            group = (group or 1) * 100
        elif word == "thousand":
            total, group = (total + (group or 1)) * 1000, None
        else:
            value = _SMALL.get(word, _TENS.get(word, 0))
            joins_hundreds = group is not None and group > 0 and group % 100 == 0
            joins_tens = group is not None and group >= 20 and group % 10 == 0 and value < 10
            if group is None:
                group = value
            elif joins_hundreds or joins_tens:
                group += value
            else:
                flush()
                group = value
    flush()
    return " ".join(str(number) for number in numbers)


def _normalized(spoken: str) -> str:
    text = spoken.lower().replace("’", "'").replace("-", " ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"\b([ap])\.\s?m\b\.?", r"\1m", text)
    text = re.sub(r"\ba (hundred|thousand)\b", r"one \1", text)
    text = re.sub(r"\b(hundred|thousand) and\b", r"\1", text)
    text = _OH_DIGIT.sub(lambda match: f"0{_SMALL[match.group(1)]}", text)
    return _NUMBER_RUN.sub(lambda match: _words_to_digits(match.group()), text)


def _says_estimate(text: str, estimate: Decimal) -> bool:
    if any(Decimal(number) == estimate for number in _NUMBER.findall(text)):
        return True
    if any(
        Decimal(dollars) + Decimal(cents) / 100 == estimate
        for dollars, cents in _DOLLARS_AND_CENTS.findall(text)
    ):
        return True
    return any(
        Decimal(int(high) * 100 + int(low)) == estimate
        for high, low in _SPOKEN_HUNDREDS.findall(text)
    )


def _says_time(text: str, start_time: datetime) -> bool:
    hour = start_time.hour % 12 or 12
    minute = start_time.minute
    period = "am" if start_time.hour < 12 else "pm"
    # Only an afternoon hour is unmistakably 24-hour. "5:15" could be either.
    if start_time.hour > 12 and re.search(rf"\b{start_time.hour}:{minute:02d}(?!\d)", text):
        return True
    if minute == 0:
        if hour == 12 and re.search("noon" if period == "pm" else "midnight", text):
            return True
        if re.search(rf"\b{hour} ?o'?clock\b", text):
            return True
        clocks = [rf"\b{hour}:00(?!\d)\s*(am|pm)?\b", rf"\b{hour}\s*(am|pm)\b"]
    else:
        clocks = [rf"\b{hour}[: ]{minute:02d}(?!\d)\s*(am|pm)?\b"]
    return any(
        match.group(1) in (None, period) for clock in clocks for match in re.finditer(clock, text)
    )


def read_back_matches(spoken: str, shop_name: str, estimate: Decimal, start_time: datetime) -> bool:
    """Whether the agent said this shop, estimate, and time. It checks the details are present,
    not that nothing else was said, so a labor and parts breakdown still passes. The first word of
    a shop's name is enough, because that's what people shorten it to."""
    text = _normalized(spoken)
    says_shop = re.search(rf"\b{re.escape(shop_name.lower().split()[0])}\b", text) is not None
    return says_shop and _says_estimate(text, estimate) and _says_time(text, start_time)
