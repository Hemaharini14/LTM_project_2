import html
import re
import time

import feedparser

import truststore


# The corporate proxy this project runs behind presents its own TLS
# certificate, which certifi does not trust. Without this, every feed
# fetch fails; see the project's network notes.
truststore.inject_into_ssl()


FEEDS = [
    ("Times Higher Education", "https://www.timeshighereducation.com/news/rss"),
    ("Inside Higher Ed", "https://www.insidehighered.com/rss.xml"),
    ("The PIE News", "https://thepienews.com/feed/"),
    ("Study International", "https://www.studyinternational.com/feed/")
]

# Fetching all four feeds takes ~6s, which is too slow to repeat on every
# dashboard load. Headlines change far more slowly than that.
CACHE_TTL_SECONDS = 900

# e.g. "jane.doe@in... Mon, 09/21/2026 - 03:00 AM Byline(s) Jane Doe"
BYLINE_NOISE = re.compile(
    r"\S*@\S*|"
    r"\b\w{3},\s*\d{2}/\d{2}/\d{4}\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM)|"
    r"Byline\(s\).*?(?=[A-Z][a-z]{3,}\s|$)",
    re.IGNORECASE
)

_cache = {"fetched_at": 0.0, "articles": []}


def fetch_news(limit=12):
    """
    Pull education headlines from public RSS feeds. A feed that is
    unreachable is skipped rather than failing the dashboard, since
    this runs behind a proxy that blocks hosts unpredictably.
    """

    age = time.time() - _cache["fetched_at"]

    if _cache["articles"] and age < CACHE_TTL_SECONDS:
        return _cache["articles"][:limit]

    articles = []

    for source_name, url in FEEDS:

        try:
            parsed = feedparser.parse(url)

        except Exception:
            continue

        for entry in parsed.entries[:limit]:

            title = clean_text(entry.get("title", ""))

            articles.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": clean_summary(entry.get("summary", ""), title),
                "source": source_name
            })

    if articles:
        _cache["articles"] = articles
        _cache["fetched_at"] = time.time()

    return articles[:limit]


def strip_html(text):
    result = []
    inside_tag = False

    for character in text:

        if character == "<":
            inside_tag = True
        elif character == ">":
            inside_tag = False
        elif not inside_tag:
            result.append(character)

    return "".join(result).strip()


def clean_text(text):
    """Tags out, entities decoded (&#8217; would otherwise render raw)."""

    return " ".join(html.unescape(strip_html(text)).split())


def clean_summary(summary, title):
    """
    Several feeds prefix the description with the headline and a byline
    block, which reads as duplicated noise next to the title.
    """

    text = clean_text(summary)

    if title and text.lower().startswith(title.lower()):
        text = text[len(title):].lstrip(" -–—:")

    text = " ".join(BYLINE_NOISE.sub("", text).split())

    # What survives is often just the author's name repeated. Too short to
    # be a real summary means there was no summary — show the headline alone.
    if len(text) < 40:
        return ""

    return text[:240]
