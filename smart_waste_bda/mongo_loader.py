#!/usr/bin/env python3
r"""
mongo_loader.py
Loads the important PROCESSED RESULTS (not raw data) into MongoDB so the
dashboard (Checkpoint 8) can read them quickly, without re-running Spark.

Run (from Windows, inside the project folder):
    python mongo_loader.py
"""

import csv
import glob
import os

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "smart_waste"

SPARK_OUTPUT_DIR = "mongo_input"
CLEANED_CSV = os.path.join("data", "cleaned", "waste_cleaned_full.csv")


def read_csv(folder):
    matches = glob.glob(os.path.join(SPARK_OUTPUT_DIR, folder, "part-*.csv"))
    if not matches:
        raise FileNotFoundError("No CSV found in %s -- did you run 'hdfs dfs -get' for it?" % folder)
    with open(matches[0], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_number(value):
    try:
        return float(value) if "." in value else int(value)
    except (ValueError, TypeError):
        return value


def clean_row(row):
    return {k: to_number(v) for k, v in row.items()}


def main():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]

    # ---------- 1. location_statistics ----------
    by_location = {r["Location"]: r for r in read_csv("by_location")}
    avg_by_location = {r["Location"]: r for r in read_csv("avg_by_location")}
    utilization = {r["Location"]: r for r in read_csv("utilization_by_location")}

    location_docs = []
    for loc in by_location:
        doc = {"Location": loc}
        doc.update(clean_row(by_location[loc]))
        doc.update(clean_row(avg_by_location.get(loc, {})))
        doc.update(clean_row(utilization.get(loc, {})))
        doc.pop("Location", None)
        doc = {"Location": loc, **doc}
        location_docs.append(doc)

    db.location_statistics.drop()
    db.location_statistics.insert_many(location_docs)
    print("location_statistics : inserted %d documents" % len(location_docs))

    # ---------- 2. waste_statistics (by type + daily trend + monthly trend) ----------
    waste_docs = []
    for row in read_csv("by_type"):
        d = clean_row(row)
        d["metric_type"] = "by_waste_type"
        waste_docs.append(d)
    for row in read_csv("daily_trend"):
        d = clean_row(row)
        d["metric_type"] = "daily_trend"
        waste_docs.append(d)
    for row in read_csv("monthly_trend"):
        d = clean_row(row)
        d["metric_type"] = "monthly_trend"
        waste_docs.append(d)

    db.waste_statistics.drop()
    db.waste_statistics.insert_many(waste_docs)
    print("waste_statistics    : inserted %d documents" % len(waste_docs))

    # ---------- 3. cluster_results ----------
    cluster_docs = [clean_row(r) for r in read_csv("cluster_results")]
    db.cluster_results.drop()
    db.cluster_results.insert_many(cluster_docs)
    print("cluster_results     : inserted %d documents" % len(cluster_docs))

    # ---------- 4. overflow_events (only the rows that actually overflowed) ----------
    overflow_docs = []
    with open(CLEANED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Overflow_Status"] == "Yes":
                overflow_docs.append({
                    "Bin_ID": row["Bin_ID"],
                    "Date": row["Date"],
                    "Location": row["Location"],
                    "Waste_Type": row["Waste_Type"],
                    "Waste_Generated": to_number(row["Waste_Generated"]),
                    "Bin_Utilization_Pct": to_number(row["Bin_Utilization_Pct"]),
                })

    db.overflow_events.drop()
    db.overflow_events.insert_many(overflow_docs)
    print("overflow_events     : inserted %d documents" % len(overflow_docs))

    # ---------- Verification ----------
    print("\n===== VERIFICATION =====")
    for name in ["location_statistics", "waste_statistics", "cluster_results", "overflow_events"]:
        print("%-20s -> %d documents" % (name, db[name].count_documents({})))

    print("\nSample location_statistics document:")
    print(db.location_statistics.find_one({}, {"_id": 0}))

    print("\nSample overflow_events document:")
    print(db.overflow_events.find_one({}, {"_id": 0}))

    client.close()


if __name__ == "__main__":
    main()