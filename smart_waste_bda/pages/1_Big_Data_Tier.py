import requests
import pandas as pd
import streamlit as st
from pymongo import MongoClient

st.set_page_config(page_title="Big Data Tier", layout="wide")
from style import inject_css
inject_css()

NAMENODE = "http://localhost:9870/webhdfs/v1"
YARN = "http://localhost:8088/ws/v1/cluster"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "smart_waste"
COLLECTIONS = ["location_statistics", "waste_statistics", "cluster_results",
               "spoilage_events", "spoilage_predictions"]


def get_json(url):
    try:
        r = requests.get(url, timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def hdfs_list(path):
    data = get_json(f"{NAMENODE}{path}?op=LISTSTATUS")
    if not data:
        return None
    return data["FileStatuses"]["FileStatus"]


def card(title, status, value, desc):
    colors = {"LIVE": "#22c55e", "BATCH": "#f59e0b", "OFFLINE": "#ef4444"}
    color = colors[status]
    st.markdown(
        f"""
        <div style="border:1px solid rgba(128,128,128,0.4);border-radius:12px;
                    padding:16px;text-align:center;height:170px">
            <div style="font-weight:600;font-size:18px">{title}</div>
            <div style="color:{color};font-size:12px;font-weight:700;
                        letter-spacing:1px;margin:4px 0">&#9679; {status}</div>
            <div style="font-size:24px;font-weight:700;margin:6px 0">{value}</div>
            <div style="font-size:12px;opacity:0.7">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------- collect live data ----------
cleaned = hdfs_list("/smart_waste/cleaned")
outputs = hdfs_list("/smart_waste/output")
metrics = get_json(f"{YARN}/metrics")

mongo_ok, counts = False, {}
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    client.admin.command("ping")
    db = client[DB_NAME]
    counts = {c: db[c].count_documents({}) for c in COLLECTIONS}
    mongo_ok = True
except Exception:
    pass

# ---------- page ----------
st.markdown("<h1 style='text-align:center'>Big Data Tier Status</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;opacity:0.7'>Live health check of the components "
    "behind this project</p>",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    if cleaned is not None:
        total_kb = sum(f["length"] for f in cleaned if f["type"] == "FILE") / 1024
        card("Hadoop HDFS", "LIVE", f"{len(cleaned)} files / {total_kb:,.0f} KB",
             "Cleaned dataset stored in /smart_waste/cleaned")
    else:
        card("Hadoop HDFS", "OFFLINE", "Not reachable", "Start: start-dfs.sh in WSL")
with c2:
    if metrics is not None and outputs is not None:
        card("MapReduce on YARN", "LIVE", f"{len(outputs)} job outputs",
             "Hadoop Streaming jobs, results in /smart_waste/output")
    elif outputs is not None:
        card("MapReduce on YARN", "OFFLINE", f"{len(outputs)} job outputs",
             "YARN is stopped; outputs are still in HDFS")
    else:
        card("MapReduce on YARN", "OFFLINE", "Not reachable", "Start: start-yarn.sh in WSL")
with c3:
    card("Apache Spark", "BATCH", "7 analyses + 2 models",
         "PySpark aggregations, K-Means and Random Forest run as batch jobs")
with c4:
    if mongo_ok:
        card("MongoDB", "LIVE", f"{sum(counts.values()):,} documents",
             f"Database {DB_NAME}, {len(COLLECTIONS)} collections")
    else:
        card("MongoDB", "OFFLINE", "Not reachable", "Check the MongoDB Windows service")

st.markdown("---")
st.markdown("<h3 style='text-align:center'>Data pipeline</h3>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center'>Kaggle dataset &rarr; Python preprocessing &rarr; "
    "<b>HDFS</b> &rarr; <b>MapReduce</b> + <b>PySpark</b> (K-Means, Random Forest) "
    "&rarr; <b>MongoDB</b> &rarr; Dashboard</p>",
    unsafe_allow_html=True,
)

left, right = st.columns(2)
with left:
    st.markdown("<h4 style='text-align:center'>Files in HDFS</h4>", unsafe_allow_html=True)
    if cleaned:
        df = pd.DataFrame(
            [{"File": f["pathSuffix"], "Size (KB)": round(f["length"] / 1024, 1)}
             for f in cleaned if f["type"] == "FILE"]
        )
        st.table(df)
    else:
        st.info("HDFS not reachable.")
    st.markdown("<h4 style='text-align:center'>MapReduce job outputs</h4>", unsafe_allow_html=True)
    if outputs:
        st.table(pd.DataFrame({"Output folder": [f["pathSuffix"] for f in outputs]}))
    else:
        st.info("No output folders found.")
with right:
    st.markdown("<h4 style='text-align:center'>MongoDB collections</h4>", unsafe_allow_html=True)
    if mongo_ok:
        st.table(pd.DataFrame({"Collection": list(counts.keys()),
                               "Documents": list(counts.values())}))
    else:
        st.info("MongoDB not reachable.")
    if metrics:
        m = metrics["clusterMetrics"]
        st.markdown("<h4 style='text-align:center'>YARN cluster</h4>", unsafe_allow_html=True)
        st.table(pd.DataFrame({"Metric": ["Active nodes", "Applications completed since YARN start"],
                               "Value": [m["activeNodes"], m["appsCompleted"]]}))

st.caption("Status is read live from the HDFS and YARN web endpoints and from MongoDB each time this page loads.")