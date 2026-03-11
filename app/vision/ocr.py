"""OCR extraction for Moroccan identity documents and diplomas using Claude Vision.

Handles:
- CIN (Carte d'Identite Nationale) front side: name, DOB, city, CIN number
- CIN back side: address, gender, expiration, marital status
- Diplomas and certifications: degree, institution, year, field, honors
"""

import json
import logging
import re
from datetime import datetime

from app.agent.claude_client import chat_with_image
from app.agent.prompts import CIN_FRONT_EXTRACTION, CIN_BACK_EXTRACTION, DIPLOMA_EXTRACTION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CIN_PATTERN = re.compile(r"^[A-Z]{1,2}\d{5,7}$")

# Date patterns we recognize, mapped to their strptime format strings.
# Order matters: more specific patterns first.
_DATE_FORMATS = [
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%d/%m/%Y"),       # DD/MM/YYYY
    (re.compile(r"^\d{2}-\d{2}-\d{4}$"), "%d-%m-%Y"),       # DD-MM-YYYY
    (re.compile(r"^\d{2}\.\d{2}\.\d{4}$"), "%d.%m.%Y"),     # DD.MM.YYYY
    (re.compile(r"^\d{4}/\d{2}/\d{2}$"), "%Y/%m/%d"),       # YYYY/MM/DD
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),       # YYYY-MM-DD
    (re.compile(r"^\d{4}\.\d{2}\.\d{2}$"), "%Y.%m.%d"),     # YYYY.MM.DD
    (re.compile(r"^\d{2}/\d{2}/\d{2}$"), "%d/%m/%y"),       # DD/MM/YY
    (re.compile(r"^\d{2}-\d{2}-\d{2}$"), "%d-%m-%y"),       # DD-MM-YY
]


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from a response string."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Drop the closing fence
        text = text.rsplit("```", 1)[0]
    # In case the opening fence was ```json (without newline after ```)
    if text.startswith("json"):
        text = text[4:]
    return text.strip()


def _parse_json_response(raw: str) -> dict:
    """Best-effort parse of a JSON response from the model.

    Handles markdown fences, leading/trailing whitespace, and common quirks.
    Returns an empty dict if parsing fails entirely.
    """
    cleaned = _strip_code_fences(raw)

    # First try: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Second try: find the first { ... } block in the text
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    logger.error("Failed to parse JSON from model response: %s", raw[:300])
    return {}


# ---------------------------------------------------------------------------
# Public validation helpers
# ---------------------------------------------------------------------------

def validate_cin_number(cin: str) -> bool:
    """Validate a Moroccan CIN number format.

    Valid formats: 1-2 uppercase letters followed by 5-7 digits.
    Examples: AB123456, BK456789, B123456, BE12345, J1234567
    """
    if not cin or not isinstance(cin, str):
        return False
    return bool(_CIN_PATTERN.match(cin.strip().upper()))


def validate_date_format(date_str: str) -> str | None:
    """Normalize a date string to DD/MM/YYYY format.

    Handles DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD, YYYY/MM/DD,
    YYYY.MM.DD, and two-digit year variants. Returns None if the string
    cannot be parsed into a valid date.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()

    for pattern, fmt in _DATE_FORMATS:
        if pattern.match(cleaned):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                continue

    # Last resort: try dateutil-style loose parsing is deliberately omitted
    # to keep dependencies minimal; log and return None.
    logger.warning("Could not normalize date string: %s", date_str)
    return None


# ---------------------------------------------------------------------------
# Vision extraction functions
# ---------------------------------------------------------------------------

async def extract_cin_front(image_data: bytes, media_type: str = "image/jpeg") -> dict:
    """Extract data from the front side of a Moroccan CIN card.

    Returns a dict with keys:
        full_name_arabic, full_name_latin, date_of_birth, city_of_birth, cin_number
    Each value is a string or None. Returns {} on total failure.
    """
    try:
        raw = await chat_with_image(
            system=CIN_FRONT_EXTRACTION,
            messages=[],
            image_data=image_data,
            media_type=media_type,
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
        )
        logger.info("CIN front raw response length: %d", len(raw))

        data = _parse_json_response(raw)
        if not data:
            return {}

        # Post-process: validate and normalize fields
        cin = data.get("cin_number")
        if cin and isinstance(cin, str):
            cin_clean = cin.strip().upper()
            if validate_cin_number(cin_clean):
                data["cin_number"] = cin_clean
            else:
                logger.warning("Extracted CIN number failed validation: %s", cin)
                # Keep the raw value so the caller can still use it

        dob = data.get("date_of_birth")
        if dob and isinstance(dob, str):
            normalized = validate_date_format(dob)
            if normalized:
                data["date_of_birth"] = normalized

        return data

    except Exception as e:
        logger.error("CIN front extraction failed: %s", e, exc_info=True)
        return {}


async def extract_cin_back(image_data: bytes, media_type: str = "image/jpeg") -> dict:
    """Extract data from the back side of a Moroccan CIN card.

    Returns a dict with keys:
        address, gender, expiration_date, marital_status
    Each value is a string or None. Returns {} on total failure.
    """
    try:
        raw = await chat_with_image(
            system=CIN_BACK_EXTRACTION,
            messages=[],
            image_data=image_data,
            media_type=media_type,
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
        )
        logger.info("CIN back raw response length: %d", len(raw))

        data = _parse_json_response(raw)
        if not data:
            return {}

        # Normalize gender to single letter
        gender = data.get("gender")
        if gender and isinstance(gender, str):
            g = gender.strip().upper()
            if g in ("M", "MALE", "MASCULIN", "ذكر"):
                data["gender"] = "M"
            elif g in ("F", "FEMALE", "FEMININ", "FÉMININ", "أنثى"):
                data["gender"] = "F"
            # Otherwise keep whatever was extracted

        # Normalize expiration date if present
        exp = data.get("expiration_date")
        if exp and isinstance(exp, str):
            normalized = validate_date_format(exp)
            if normalized:
                data["expiration_date"] = normalized

        return data

    except Exception as e:
        logger.error("CIN back extraction failed: %s", e, exc_info=True)
        return {}


async def extract_diploma(image_data: bytes, media_type: str = "image/jpeg") -> dict:
    """Extract diploma or certification information from an image.

    Returns a dict with keys:
        degree_name, field_of_study, institution, city, year, honors, type
    Each value is a string or None. Returns {} on total failure.
    """
    try:
        raw = await chat_with_image(
            system=DIPLOMA_EXTRACTION,
            messages=[],
            image_data=image_data,
            media_type=media_type,
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
        )
        logger.info("Diploma raw response length: %d", len(raw))

        data = _parse_json_response(raw)
        if not data:
            return {}

        # Normalize year to a plain 4-digit string if possible
        year = data.get("year")
        if year and isinstance(year, str):
            # Extract a 4-digit year from strings like "2019-2020" or "Juin 2020"
            match = re.search(r"((?:19|20)\d{2})", year.strip())
            if match:
                data["year"] = match.group(1)

        # Normalize type to one of the expected values
        doc_type = data.get("type")
        if doc_type and isinstance(doc_type, str):
            t = doc_type.strip().lower()
            valid_types = {"diploma", "certification", "attestation", "license"}
            if t not in valid_types:
                # Best-effort mapping
                if "diplom" in t or "diplôm" in t:
                    data["type"] = "diploma"
                elif "certif" in t:
                    data["type"] = "certification"
                elif "attest" in t:
                    data["type"] = "attestation"
                elif "licen" in t:
                    data["type"] = "license"
                # Otherwise keep the raw value

        return data

    except Exception as e:
        logger.error("Diploma extraction failed: %s", e, exc_info=True)
        return {}
