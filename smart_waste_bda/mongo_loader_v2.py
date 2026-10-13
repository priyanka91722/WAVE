#!/usr/bin/env python3
r"""
mongo_loader.py
Loads the processed results into MongoDB.

Database:   smart_waste
Collections:
    location_statistics -- waste totals/averages/spoilage risk per location
    waste_statistics     -- waste by category, daily trend, by promotion (tagged by metric_type)
    cluster_results       -- K-Means cluster assignment per location
    spoilage_events       -- individual items that actually spoiled
    spoilage_predictions -- ML model's predicted risk for every item (NEW)

Run:
    python mongo_loader_v2.py
"""

import csv
import glob
import os

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "smart_waste"

SPARK_OUTPUT_DIR = "mongo_input_v2"
CLEANED_CSV = os.path.join("data", "cleaned", "waste_cleaned.csv")


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
    by_location = {r["StoreLocation"]: r for r in read_csv("by_location")}
    avg_by_location = {r["StoreLocation"]: r for r in read_csv("avg_by_location")}
    spoilage_by_location = {r["StoreLocation"]: r for r in read_csv("spoilage_by_location")}

    location_docs = []
    for loc in by_location:
        doc = {"StoreLocation": loc}
        doc.update(clean_row(by_location[loc]))
        doc.update(clean_row(avg_by_location.get(loc, {})))
        doc.update(clean_row(spoilage_by_location.get(loc, {})))
        doc.pop("StoreLocation", None)
        doc = {"StoreLocation": loc, **doc}
        location_docs.append(doc)

    db.location_statistics.drop()
    db.location_statistics.insert_many(location_docs)
    print("location_statistics  : inserted %d documents" % len(location_docs))

    # ---------- 2. waste_statistics (by category + daily trend + by promotion) ----------
    waste_docs = []
    for row in read_csv("by_category"):
        d = clean_row(row)
        d["metric_type"] = "by_category"
        waste_docs.append(d)
    for row in read_csv("daily_trend"):
        d = clean_row(row)
        d["metric_type"] = "daily_trend"
        waste_docs.append(d)
    for row in read_csv("by_promotion"):
        d = clean_row(row)
        d["metric_type"] = "by_promotion"
        waste_docs.append(d)

    db.waste_statistics.drop()
    db.waste_statistics.insert_many(waste_docs)
    print("waste_statistics     : inserted %d documents" % len(waste_docs))

    # ---------- 3. cluster_results ----------
    cluster_docs = [clean_row(r) for r in read_csv("cluster_results")]
    db.cluster_results.drop()
    db.cluster_results.insert_many(cluster_docs)
    print("cluster_results      : inserted %d documents" % len(cluster_docs))

    # ---------- 4. spoilage_events (only items that actually spoiled) ----------
    spoilage_docs = []
    with open(CLEANED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Waste_Status"] == "Spoiled":
                spoilage_docs.append({
                    "StoreID": row["StoreID"],
                    "ItemName": row["ItemName"],
                    "Category": row["Category"],
                    "StoreLocation": row["StoreLocation"],
                    "ArrivalDate": row["ArrivalDate"],
                    "Waste_Qty": to_number(row["Waste_Qty"]),
                    "SpoilageChance": to_number(row["SpoilageChance"]),
                })

    db.spoilage_events.drop()
    db.spoilage_events.insert_many(spoilage_docs)
    print("spoilage_events      : inserted %d documents" % len(spoilage_docs))

    # ---------- 5. spoilage_predictions (NEW -- the ML model's output) ----------
    prediction_docs = [clean_row(r) for r in read_csv("spoilage_predictions")]
    db.spoilage_predictions.drop()
    db.spoilage_predictions.insert_many(prediction_docs)
    print("spoilage_predictions : inserted %d documents" % len(prediction_docs))

    # ---------- Verification ----------
    print("\n===== VERIFICATION =====")
    for name in ["location_statistics", "waste_statistics", "cluster_results",
                 "spoilage_events", "spoilage_predictions"]:
        print("%-20s -> %d documents" % (name, db[name].count_documents({})))

    client.close()


if __name__ == "__main__":
    main()