#!/usr/bin/env python3
r"""
app.py
Streamlit dashboard for the Smart Waste Management project.

This ONLY reads already-processed results from MongoDB and draws charts.
It does NOT re-run HDFS, MapReduce, PySpark, or K-Means -- all the real
Big Data processing already happened in earlier checkpoints. This file
is purely for visualization.

Run:
    streamlit run app.py
"""

import pandas as pd
import streamlit as st
from pymongo import MongoClient

st.set_page_config(page_title="Smart Waste Management Dashboard", layout="wide")

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "smart_waste"


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
    overflow_df = pd.DataFrame(list(db.overflow_events.find({}, {"_id": 0})))
    return location_df, waste_df, cluster_df, overflow_df


st.title("🗑️ Smart Waste Management — Big Data Dashboard")
st.caption("All figures below come from MongoDB, which was populated by HDFS -> MapReduce -> PySpark -> K-Means. "
           "This page only displays results; it performs no processing itself.")

try:
    location_df, waste_df, cluster_df, overflow_df = load_collections()
except Exception as e:
    st.error("Could not connect to MongoDB. Make sure MongoDB is running and "
             "mongo_loader.py has been run at least once.\n\nDetails: %s" % e)
    st.stop()

# Merge Waste_Level into location_df so location-level charts can be colored by cluster
merged_df = location_df.merge(
    cluster_df[["Location", "cluster", "Waste_Level", "Overflow_Freq_Pct"]],
    on="Location", how="left"
)

# =====================================================================
# TOP ROW: KPI CARDS
# =====================================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Waste Generated", "%.0f kg" % location_df["Total_Waste_Kg"].sum())
col2.metric("Locations Monitored", len(location_df))
col3.metric("Avg Bin Utilization", "%.1f%%" % location_df["Avg_Utilization_Pct"].mean())
col4.metric("Recent Overflow Events", len(overflow_df))

st.divider()

# =====================================================================
# 1. WASTE BY LOCATION
# =====================================================================
st.subheader("1. Waste by Location")
st.bar_chart(location_df.set_index("Location")["Total_Waste_Kg"].sort_values(ascending=False))

# =====================================================================
# 2. WASTE BY WASTE TYPE
# =====================================================================
st.subheader("2. Waste by Waste Type")
type_df = waste_df[waste_df["metric_type"] == "by_waste_type"]
st.bar_chart(type_df.set_index("Waste_Type")["Total_Waste_Kg"].sort_values(ascending=False))

# =====================================================================
# 3. WASTE TREND OVER TIME
# =====================================================================
st.subheader("3. Waste Trend Over Time")
trend_choice = st.radio("View trend by:", ["Monthly", "Daily"], horizontal=True)
if trend_choice == "Monthly":
    monthly_df = waste_df[waste_df["metric_type"] == "monthly_trend"].sort_values("Month")
    st.line_chart(monthly_df.set_index("Month")["Total_Waste_Kg"])
else:
    daily_df = waste_df[waste_df["metric_type"] == "daily_trend"].sort_values("Date")
    st.line_chart(daily_df.set_index("Date")["Total_Waste_Kg"])

# =====================================================================
# 4. BIN UTILIZATION
# =====================================================================
st.subheader("4. Bin Utilization by Location")
st.bar_chart(location_df.set_index("Location")["Avg_Utilization_Pct"].sort_values(ascending=False))

# =====================================================================
# 5. HIGH-WASTE AREAS
# =====================================================================
st.subheader("5. High-Waste Areas")
avg_total = location_df["Total_Waste_Kg"].mean()
threshold = avg_total * 1.10
high_waste = location_df[location_df["Total_Waste_Kg"] > threshold].sort_values(
    "Total_Waste_Kg", ascending=False)
st.write("Average total waste across all locations: **%.2f kg**. "
         "A location counts as high-waste if it's more than 10%% above this." % avg_total)
st.dataframe(high_waste[["Location", "Total_Waste_Kg"]], use_container_width=True, hide_index=True)

# =====================================================================
# 6. K-MEANS CLUSTERS
# =====================================================================
st.subheader("6. Location Clusters (K-Means)")
col_a, col_b = st.columns([2, 1])
with col_a:
    st.scatter_chart(merged_df, x="Total_Waste_Kg", y="Avg_Utilization_Pct", color="Waste_Level")
with col_b:
    for level in ["High", "Medium", "Low"]:
        locs = merged_df[merged_df["Waste_Level"] == level]["Location"].tolist()
        if locs:
            st.write("**%s:** %s" % (level, ", ".join(locs)))

st.dataframe(
    merged_df[["Location", "Total_Waste_Kg", "Avg_Utilization_Pct", "Overflow_Freq_Pct", "Waste_Level"]]
    .sort_values("Total_Waste_Kg", ascending=False),
    use_container_width=True, hide_index=True
)

# =====================================================================
# 7. RECENT OVERFLOW EVENTS
# =====================================================================
st.subheader("7. Recent Overflow Events")
recent_overflows = overflow_df.sort_values("Date", ascending=False).head(20)
st.dataframe(recent_overflows, use_container_width=True, hide_index=True)

st.caption("Showing the 20 most recent overflow events out of %d total recorded." % len(overflow_df))