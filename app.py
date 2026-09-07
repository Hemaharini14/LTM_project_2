import streamlit as st

from src.data_loader import (
    load_university_data,
    load_cost_data
)

from src.recommender import prepare_recommendations


st.set_page_config(
    page_title="EduBridge",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 EduBridge")
st.subheader("Smart University Recommendation System")


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

try:
    university_df = load_university_data()
    cost_df = load_cost_data()

except Exception as e:
    st.error("Error loading datasets")
    st.exception(e)
    st.stop()


# --------------------------------------------------
# MERGE DATA
# --------------------------------------------------

try:

    merged_df = prepare_recommendations(
        university_df,
        cost_df
    )

except Exception as e:

    st.error("Error merging datasets")
    st.exception(e)
    st.stop()


# --------------------------------------------------
# MATCH ANALYSIS
# --------------------------------------------------

matched = merged_df["Cost of Living Index"].notna().sum()

unmatched = len(merged_df) - matched

match_percentage = (
    matched / len(merged_df) * 100
)


# --------------------------------------------------
# DATASET OVERVIEW
# --------------------------------------------------

st.header("📊 Dataset Overview")

col1, col2, col3, col4 = st.columns(4)


with col1:
    st.metric(
        "Universities",
        len(university_df)
    )


with col2:
    st.metric(
        "Countries",
        len(cost_df)
    )


with col3:
    st.metric(
        "Matched Universities",
        matched
    )


with col4:
    st.metric(
        "Match Rate",
        f"{match_percentage:.1f}%"
    )


# --------------------------------------------------
# MATCH STATUS
# --------------------------------------------------

if match_percentage >= 90:

    st.success(
        f"Excellent! {matched} universities "
        f"({match_percentage:.1f}%) have cost-of-living data."
    )

elif match_percentage >= 70:

    st.warning(
        f"{matched} universities matched "
        f"({match_percentage:.1f}%)."
    )

else:

    st.error(
        f"Only {matched} universities matched "
        f"({match_percentage:.1f}%). "
        "Country-name normalization is required."
    )


# --------------------------------------------------
# MERGED DATA
# --------------------------------------------------

st.header("🔗 University + Cost of Living")

display_columns = [
    "University",
    "Location",
    "Overall Score",
    "University Rank",
    "Cost of Living Index",
    "Rent Index",
    "Cost of Living Plus Rent Index"
]

display_columns = [
    col
    for col in display_columns
    if col in merged_df.columns
]


st.dataframe(
    merged_df[display_columns].head(20),
    use_container_width=True,
    hide_index=True
)


# --------------------------------------------------
# UNMATCHED COUNTRIES
# --------------------------------------------------

with st.expander("⚠️ Check universities without cost data"):

    unmatched_df = merged_df[
        merged_df["Cost of Living Index"].isna()
    ]

    st.write(
        f"Universities without cost data: "
        f"**{len(unmatched_df)}**"
    )

    if len(unmatched_df) > 0:

        st.dataframe(
            unmatched_df[
                ["University", "Location"]
            ].drop_duplicates(),
            use_container_width=True,
            hide_index=True
        )