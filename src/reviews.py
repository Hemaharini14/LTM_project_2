import os
from urllib.parse import quote_plus

import truststore


truststore.inject_into_ssl()


# Subreddits where prospective-student discussion actually lives.
SEARCH_SUBREDDITS = "ApplyingToCollege+college+gradadmissions+IntltoUSA"


def get_linkedin_alumni_url(school_name: str) -> str:
    """
    Deep link into LinkedIn's own people search.

    We deliberately do not scrape LinkedIn: it forbids automated
    collection, and alumni profiles are real people's personal data.
    Sending the student to LinkedIn's own search gets them the same
    result without collecting anything.
    """

    return (
        "https://www.linkedin.com/search/results/people/?keywords="
        + quote_plus(school_name)
    )


def get_reddit_search_url(school_name: str) -> str:
    return (
        "https://www.reddit.com/search/?q="
        + quote_plus(f"{school_name} review")
    )


def reddit_client():
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    import praw

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=os.getenv("REDDIT_USER_AGENT", "edubridge/1.0"),
        check_for_async=False
    )


def fetch_reddit_reviews(school_name: str, limit: int = 5):
    """
    Real student discussion from Reddit's official API.

    Returns [] when credentials are absent or the call fails, so the
    detail page falls back to the deep links rather than breaking.
    """

    client = reddit_client()

    if client is None:
        return []

    try:
        submissions = client.subreddit(SEARCH_SUBREDDITS).search(
            f'"{school_name}"',
            sort="relevance",
            limit=limit
        )

        return [
            {
                "title": submission.title,
                "excerpt": (submission.selftext or "")[:300],
                "score": submission.score,
                "subreddit": str(submission.subreddit),
                "url": f"https://www.reddit.com{submission.permalink}"
            }
            for submission in submissions
        ]

    except Exception:
        return []


def get_reviews(school_name: str):
    reddit_reviews = fetch_reddit_reviews(school_name)

    return {
        "reddit_reviews": reddit_reviews,
        "reddit_search_url": get_reddit_search_url(school_name),
        "linkedin_alumni_url": get_linkedin_alumni_url(school_name),
        "reddit_configured": reddit_client() is not None
    }
