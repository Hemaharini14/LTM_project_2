import os

from openai import OpenAI
from pydantic import BaseModel


class ExtractedPreferences(BaseModel):
    country: str | None = None
    field_of_study: str | None = None
    fee_min: float | None = None
    fee_max: float | None = None
    full_name: str | None = None
    undergraduate_degree: str | None = None
    graduation_year: int | None = None
    skills: list[str] = []
    certifications: list[str] = []


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Free OpenRouter models, tried in order. Free endpoints share an upstream
# pool and return 429s or provider errors unpredictably, so we fall through
# to the next one. Every id keeps its ":free" suffix so no call can bill.
FREE_MODELS = (
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
    "openrouter/free"
)

SYSTEM_PROMPT = (
    "You extract a student's higher-education preferences from "
    "resume text or a free-text description of what they're "
    "looking for. Fill in only the fields you can support from "
    "the text — leave anything not mentioned or not clearly "
    "implied as null. "
    "'country' is the country they explicitly want to STUDY in next — "
    "never their current home address, nationality or employer's "
    "location, which say nothing about where they intend to study. "
    "This field holds exactly one country, never a list: if more than "
    "one is named, give only the first one mentioned rather than "
    "joining them with 'or' or a comma. "
    "'field_of_study' is a plain-language subject area suitable for "
    "searching real academic programmes with (e.g. 'Computer Science', "
    "'Finance', 'Business'), not the literal title or abbreviation of a "
    "degree already held. If no forward-looking interest is stated, "
    "infer one plain-language field from their degree and work "
    "background instead of copying the degree title verbatim — "
    "'B.Com (Hons)' should become 'Commerce' or 'Finance', not be "
    "repeated as-is. "
    "'fee_min'/'fee_max' are an annual tuition budget range in US "
    "dollars, if mentioned. Always give 'country' as the full official "
    "country name — 'United States', not 'US' or 'USA'; 'United "
    "Kingdom', not 'UK'. "
    "From a resume also take 'full_name', 'undergraduate_degree' "
    "(e.g. 'B.E. Electronics and Communication Engineering', the exact "
    "degree title as written — unlike field_of_study, this one should "
    "stay literal), 'graduation_year' as a four-digit year, 'skills' as "
    "a list of technical skills, and 'certifications' as a list of "
    "named certifications. Use empty lists when none are present."
)

# The country has to match the dataset spelling exactly, or the student's
# choice silently falls back to "any country" in the UI.
COUNTRY_ALIASES = {
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "uae": "United Arab Emirates"
}


def normalize_country(country):
    if not country:
        return country

    return COUNTRY_ALIASES.get(country.strip().lower(), country.strip())


def extract_preferences(text: str) -> ExtractedPreferences:
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file "
            "(see .env.example)."
        )

    # Same fix as src/rag.py: free OpenRouter models occasionally hang
    # instead of erroring, and the SDK's default timeout is ~10 minutes —
    # long enough to leave a résumé upload stuck with no feedback and
    # never reach the fallback below.
    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=20.0,
        max_retries=1,
    )

    errors = []

    for model in FREE_MODELS:

        try:
            completion = client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                response_format=ExtractedPreferences
            )

            parsed = completion.choices[0].message.parsed

            if parsed is not None:
                parsed.country = normalize_country(parsed.country)
                return parsed

            errors.append(f"{model}: empty response")

        except Exception as error:
            errors.append(f"{model}: {type(error).__name__}")

    raise RuntimeError(
        "All free OpenRouter models failed or are rate-limited. "
        + "; ".join(errors)
    )
