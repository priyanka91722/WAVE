#!/usr/bin/env python3
r"""
app.py
Streamlit dashboard for the Retail Waste & Spoilage Management project.

This ONLY reads already-processed results from MongoDB and draws charts.
It does NOT re-run HDFS, MapReduce, PySpark, K-Means, or the ML model --
all of that already happened in earlier checkpoints. This file is purely
for visualization.

Run:
    python -m streamlit run app.py
"""

import pandas as pd
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pymongo import MongoClient

st.set_page_config(page_title="Retail Waste & Spoilage Management", layout="wide")
from style import inject_css
inject_css()

# ---------- Global styling: center every text element on the page ----------
# This does NOT affect the matplotlib charts (already correctly centered)
# or the st.dataframe tables (centered separately via show_table() below,
# since tables render in their own component, outside this CSS's reach).
st.markdown("""
<style>
h1, h2, h3, h4, h5, h6, p, label,
div[data-testid="stCaptionContainer"],
div[data-testid="stMetric"],
div[data-testid="stMetricLabel"],
div[data-testid="stMetricValue"],
div[data-testid="stMetricDelta"],
.stMarkdown {
    text-align: center !important;
}
div[data-testid="stMetric"] {
    display: flex;
    flex-direction: column;
    align-items: center;
}
</style>
""", unsafe_allow_html=True)

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "smart_waste"

LEVEL_COLORS = {"Low": "#2ecc71", "Medium": "#f39c12", "High": "#e74c3c"}
PALETTE = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]


def show_table(df, columns=None):
    """Displays a dataframe with every column (text and numbers) centered,
    so nothing looks scattered or inconsistently aligned."""
    data = df[columns] if columns else df
    styled = data.style.set_properties(**{"text-align": "center"}) \
                        .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
    st.dataframe(styled, use_container_width=True, hide_index=True)


@st.cache_resource
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[DB_NAME]


@st.cache_data(ttl=60)
def load_collections():
    db = get_db()
    location_df = pd.DataFrame(list(db.location_statistics.find({}, {"_id": 0})))
    waste_df = pd.DataFrame(list(db.waste_statistics.find({}, {"_id": 0})))
    cluster_df = pd.DataFrame(list(db.cluster_results.find({}, {"_id": 0})))
    spoilage_df = pd.DataFrame(list(db.spoilage_events.find({}, {"_id": 0})))
    predictions_df = pd.DataFrame(list(db.spoilage_predictions.find({}, {"_id": 0})))
    return location_df, waste_df, cluster_df, spoilage_df, predictions_df


st.title("Retail Waste & Spoilage Management using Big Data Analytics")
st.caption("Data source: Smart Waste Inventory Dataset (Kaggle, by wildlearner)")

try:
    location_df, waste_df, cluster_df, spoilage_df, predictions_df = load_collections()
except Exception as e:
    st.error("Could not connect to MongoDB. Make sure MongoDB is running and "
             "mongo_loader_v2.py has been run at least once.\n\nDetails: %s" % e)
    st.stop()

merged_df = location_df.merge(
    cluster_df[["StoreLocation", "cluster", "Waste_Level"]],
    on="StoreLocation", how="left"
)

# =====================================================================
# TOP ROW: KPI CARDS
# =====================================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Units Wasted", "%.0f" % location_df["Total_Waste_Qty"].sum())
col2.metric("Store Locations", len(location_df))
col3.metric("Avg Spoilage Rate", "%.1f%%" % location_df["Spoilage_Rate_Pct"].mean())
col4.metric("Items Spoiled", len(spoilage_df))

st.divider()

# =====================================================================
# 1. WASTE BY LOCATION -- PIE CHART
# =====================================================================
st.subheader("1. Waste by Location (share of total)")
loc_sorted = location_df.sort_values("Total_Waste_Qty", ascending=False)
fig1, ax1 = plt.subplots(figsize=(6, 6))
ax1.pie(loc_sorted["Total_Waste_Qty"], labels=loc_sorted["StoreLocation"],
        autopct="%1.1f%%", colors=PALETTE, startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5})
ax1.set_title("Waste Share by Location")
col_a, col_b = st.columns([1, 1])
with col_a:
    st.pyplot(fig1)
with col_b:
    show_table(loc_sorted, ["StoreLocation", "Total_Waste_Qty", "Records"])
st.caption("Kanpur generates the largest share of total waste; Mumbai the smallest.")

# =====================================================================
# 2. WASTE BY CATEGORY -- DONUT CHART
# =====================================================================
st.subheader("2. Waste by Category")
category_df = waste_df[waste_df["metric_type"] == "by_category"].sort_values(
    "Total_Waste_Qty", ascending=False)
fig2, ax2 = plt.subplots(figsize=(6, 6))
ax2.pie(category_df["Total_Waste_Qty"], labels=category_df["Category"],
        autopct="%1.1f%%", colors=PALETTE, startangle=90,
        wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 1.5})
ax2.set_title("Waste Share by Category")
col_c, col_d = st.columns([1, 1])
with col_c:
    st.pyplot(fig2)
with col_d:
    show_table(category_df, ["Category", "Total_Waste_Qty"])
st.caption("Snacks account for the largest portion of waste; Dairy the smallest.")

# =====================================================================
# 3. DAILY WASTE TREND
# =====================================================================
st.subheader("3. Daily Waste Trend")
daily_df = waste_df[waste_df["metric_type"] == "daily_trend"].sort_values("ArrivalDate")
st.line_chart(daily_df.set_index("ArrivalDate")["Total_Waste_Qty"])
st.caption("Each point shows the total units wasted from items that arrived that day.")

# =====================================================================
# 4. WASTE BY PROMOTION STATUS
# =====================================================================
st.subheader("4. Waste by Promotion Status")
promo_df = waste_df[waste_df["metric_type"] == "by_promotion"]
promo_cols = st.columns(len(promo_df))
for col, (_, row) in zip(promo_cols, promo_df.iterrows()):
    label = "On Promotion" if row["OnPromotion"] == "Yes" else "Not on Promotion"
    col.metric(label, "%.0f units" % row["Total_Waste_Qty"],
               "%.1f%% avg spoilage chance" % (row["Avg_Spoilage_Chance"] * 100))
st.caption("Compares total waste and average spoilage chance between promoted and non-promoted items.")

# =====================================================================
# 5. SPOILAGE RISK BY LOCATION
# =====================================================================
st.subheader("5. Spoilage Risk by Location")
risk_sorted = location_df.sort_values("Spoilage_Rate_Pct", ascending=True)
bar_colors = ["#e74c3c" if v > 50 else "#f39c12" if v > 35 else "#2ecc71"
              for v in risk_sorted["Spoilage_Rate_Pct"]]
fig5, ax5 = plt.subplots(figsize=(8, 4))
ax5.barh(risk_sorted["StoreLocation"], risk_sorted["Spoilage_Rate_Pct"], color=bar_colors)
ax5.set_xlabel("Spoilage Rate (%)")
ax5.set_title("Spoilage Rate by Location")
st.pyplot(fig5)
st.caption("Red bars mark locations with the highest share of items spoiling; green marks the lowest.")

# =====================================================================
# 6. HIGH-WASTE LOCATIONS
# =====================================================================
st.subheader("6. High-Waste Locations")
avg_total = location_df["Total_Waste_Qty"].mean()
threshold = avg_total * 1.10
high_waste = location_df[location_df["Total_Waste_Qty"] > threshold].sort_values(
    "Total_Waste_Qty", ascending=False)
show_table(high_waste, ["StoreLocation", "Total_Waste_Qty"])
st.caption("Locations generating more than 10%% above the average total waste across all 5 locations.")

# =====================================================================
# 7. LOCATION CLUSTERS (K-MEANS)
# =====================================================================
st.subheader("7. Location Clusters (K-Means)")
col_e, col_f = st.columns([2, 1])
with col_e:
    st.scatter_chart(merged_df, x="Total_Waste_Qty", y="Spoilage_Rate_Pct", color="Waste_Level")
with col_f:
    level_counts = merged_df["Waste_Level"].value_counts()
    fig7, ax7 = plt.subplots(figsize=(4, 4))
    ax7.pie(level_counts.values, labels=level_counts.index, autopct="%1.0f%%",
            colors=[LEVEL_COLORS.get(l, "gray") for l in level_counts.index],
            wedgeprops={"edgecolor": "white", "linewidth": 1.5})
    ax7.set_title("Locations per Risk Level")
    st.pyplot(fig7)

show_table(merged_df.sort_values("Total_Waste_Qty", ascending=False),
           ["StoreLocation", "Total_Waste_Qty", "Spoilage_Rate_Pct", "Waste_Level"])
st.caption("Locations grouped by overall risk (waste volume combined with spoilage rate), not volume alone.")

# =====================================================================
# 8. RECENT SPOILAGE EVENTS
# =====================================================================
st.subheader("8. Recent Spoilage Events")
col_g, col_h = st.columns([1, 1])
with col_g:
    spoil_by_cat = spoilage_df["Category"].value_counts()
    fig8, ax8 = plt.subplots(figsize=(6, 4))
    ax8.bar(spoil_by_cat.index, spoil_by_cat.values, color=PALETTE)
    ax8.set_ylabel("Number of Spoiled Items")
    ax8.set_title("Spoiled Items by Category")
    st.pyplot(fig8)
with col_h:
    recent_spoilage = (
        spoilage_df.sort_values("ArrivalDate", ascending=False)
                   .drop_duplicates(subset=["ItemName", "StoreLocation"])
                   .head(10)
    )
    show_table(recent_spoilage, ["ItemName", "Category", "StoreLocation", "ArrivalDate"])
st.caption("Showing the 10 most recently arrived distinct items out of %d total recorded spoilage events."
           % len(spoilage_df))

# =====================================================================
# 9. SPOILAGE RISK PREDICTIONS (ML MODEL)
# =====================================================================
st.subheader("9. Spoilage Risk Predictions (Machine Learning)")
col_i, col_j = st.columns([1, 1])
with col_i:
    fig9, ax9 = plt.subplots(figsize=(6, 4))
    ax9.hist(predictions_df["Predicted_Spoilage_Prob"], bins=20, color="#9b59b6", edgecolor="white")
    ax9.set_xlabel("Predicted Spoilage Probability")
    ax9.set_ylabel("Number of Items")
    ax9.set_title("Distribution of Predicted Risk Scores")
    st.pyplot(fig9)
with col_j:
    top_risk = (
        predictions_df[predictions_df["Predicted_Spoiled"] == 0]
        .sort_values("Predicted_Spoilage_Prob", ascending=False)
        .drop_duplicates(subset=["ItemName", "StoreLocation"])
        .head(10)
    )
    show_table(top_risk, ["ItemName", "StoreLocation", "Predicted_Spoilage_Prob"])
st.caption("Left: how confident the model is across all 1,000 items. Right: items not yet marked "
           "spoiled that the model flags as highest-risk -- an early-warning view for action today.")