import pandas as pd


def prepare_recommendations(university_df, cost_df):
    """
    Merge university ranking data with
    country cost-of-living information.
    """

    universities = university_df.copy()
    costs = cost_df.copy()

    # Clean country/location names
    universities["Location"] = (
        universities["Location"]
        .astype(str)
        .str.strip()
    )

    costs["Country"] = (
        costs["Country"]
        .astype(str)
        .str.strip()
    )

    # Convert numerical columns
    university_numeric_columns = [
        "Overall Teaching Score",
        "Research Score",
        "Research Quality",
        "Industry Income Score",
        "International Outlook Score",
        "Overall Score",
        "Rank"
    ]

    for column in university_numeric_columns:
        if column in universities.columns:
            universities[column] = pd.to_numeric(
                universities[column],
                errors="coerce"
            )

    cost_numeric_columns = [
        "Cost of Living Index",
        "Rent Index",
        "Cost of Living Plus Rent Index",
        "Groceries Index",
        "Restaurant Price Index",
        "Local Purchasing Power Index"
    ]

    for column in cost_numeric_columns:
        if column in costs.columns:
            costs[column] = pd.to_numeric(
                costs[column],
                errors="coerce"
            )

    # Merge university location with country
    merged = universities.merge(
        costs,
        left_on="Location",
        right_on="Country",
        how="left"
    )

    return merged


def calculate_score(
    df,
    academic_weight=70,
    affordability_weight=30
):
    """
    Calculate EduBridge recommendation score.
    """

    result = df.copy()

    # Academic component
    result["Academic Score"] = (
        result["Overall Score"].fillna(0)
    )

    # Lower cost = better affordability
    if "Cost of Living Index" in result.columns:

        max_cost = result["Cost of Living Index"].max()

        if max_cost > 0:
            result["Affordability Score"] = (
                100
                - (
                    result["Cost of Living Index"]
                    / max_cost
                    * 100
                )
            )
        else:
            result["Affordability Score"] = 0

    else:
        result["Affordability Score"] = 0

    # Final weighted score
    result["EduBridge Score"] = (
        result["Academic Score"] * academic_weight / 100
        +
        result["Affordability Score"]
        * affordability_weight / 100
    )

    result = result.sort_values(
        "EduBridge Score",
        ascending=False
    )

    return result