import pandas as pd
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "dataset"


def read_csv_safely(file_path):
    """
    Read CSV files using multiple possible encodings.
    """

    encodings = [
        "utf-8",
        "utf-8-sig",
        "cp1252",
        "latin1"
    ]

    for encoding in encodings:
        try:
            return pd.read_csv(file_path, encoding=encoding)

        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"Could not determine encoding for {file_path}"
    )


def clean_dataframe(df):
    """
    Basic dataset cleaning.
    """

    # Remove completely empty columns
    df = df.dropna(axis=1, how="all")

    # Remove duplicate rows
    df = df.drop_duplicates()

    # Clean column names
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
    )

    return df


def load_university_data():

    file_path = DATA_DIR / "CleanData_universityRanking.csv"

    df = read_csv_safely(file_path)

    return clean_dataframe(df)


def load_cost_data():

    file_path = DATA_DIR / "Cost_of_Living_Index_by_Country_2024.csv"

    df = read_csv_safely(file_path)

    return clean_dataframe(df)


def load_city_data():

    file_path = DATA_DIR / "worldcities.csv"

    df = read_csv_safely(file_path)

    return clean_dataframe(df)


def load_qs_data():

    file_path = (
        DATA_DIR /
        "QS World University Rankings 2025 (Top global universities).csv"
    )

    df = read_csv_safely(file_path)

    return clean_dataframe(df)