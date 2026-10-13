#!/usr/bin/env python3
r"""
preprocess.py
Cleans the real "Smart Waste Inventory Dataset" (Kaggle, by wildlearner)
and calculates two new columns needed for the rest of the pipeline:
    Waste_Qty          -- units of stock that were actually spoiled
    Waste_Status       -- "Spoiled" / "Not Spoiled" (readable version of IsSpoiled)

Source: https://www.kaggle.com/datasets/wildlearner/smart-waste-inventory-dataset

Run:
    python src\preprocess.py
"""

import argparse
import os

import pandas as pd

VALID_CATEGORIES = ["Snacks", "Bakery", "Dairy", "Produce", "Meat"]
VALID_ACTIONS = ["donate", "none", "monitor", "discount"]
VALID_LOCATIONS = ["Chennai", "Kanpur", "Mumbai", "Delhi", "Bangalore"]

# Columns dropped because they are blank for 656 of 1000 rows (65.6%) --
# too sparse to fill in responsibly without inventing data.
DROPPED_COLUMNS = ["Zone", "TemperatureSupport"]

FINAL_COLUMNS = [
    "StoreID", "ItemName", "Brand", "Category", "StoreLocation",
    "ArrivalDate", "ExpiryDate", "DaysUntilExpiry",
    "StockQty", "DailySaleAvg", "SpoilageChance",
    "IsSpoiled", "Waste_Status", "Waste_Qty",
    "SuggestedAction", "OnPromotion", "TemperatureSensitive",
    "DistanceToNearestStore", "AvgDailySaleInNearbyStores",
]


def clean(input_path, output_path):
    report = {}

    df = pd.read_csv(input_path, dtype=str)
    report["Rows read"] = len(df)

    # ---- STEP 1: remove duplicate rows ----
    before = len(df)
    df = df.drop_duplicates()
    report["Duplicate rows removed"] = before - len(df)

    # ---- STEP 2: drop the mostly-blank columns ----
    df = df.drop(columns=[c for c in DROPPED_COLUMNS if c in df.columns])

    # ---- STEP 3: tidy text ----
    for col in ["Category", "StoreLocation", "SuggestedAction"]:
        df[col] = df[col].str.strip()
    df["Category"] = df["Category"].str.title()
    df["StoreLocation"] = df["StoreLocation"].str.title()
    df["SuggestedAction"] = df["SuggestedAction"].str.lower()
    df["ItemName"] = df["ItemName"].str.strip()
    df["Brand"] = df["Brand"].str.strip()
    df["StoreID"] = df["StoreID"].str.strip()

    # ---- STEP 4: convert dates and numbers to proper types ----
    df["ArrivalDate"] = pd.to_datetime(df["ArrivalDate"], format="%d-%m-%Y", errors="coerce")
    df["ExpiryDate"] = pd.to_datetime(df["ExpiryDate"], format="%d-%m-%Y", errors="coerce")
    for col in ["StockQty", "DaysUntilExpiry", "DailySaleAvg", "SpoilageChance",
                "DistanceToNearestStore", "AvgDailySaleInNearbyStores"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["IsSpoiled"] = df["IsSpoiled"].str.strip().str.lower().map({"true": True, "false": False})
    df["OnPromotion"] = df["OnPromotion"].str.strip().str.title()
    df["TemperatureSensitive"] = df["TemperatureSensitive"].str.strip().str.lower().map(
        {"true": True, "false": False})

    # ---- STEP 5: drop rows that cannot be identified ----
    before = len(df)
    df = df.dropna(subset=["StoreID", "ItemName", "Category", "StoreLocation",
                            "ArrivalDate", "ExpiryDate", "IsSpoiled"])
    report["Dropped: missing key fields or unreadable dates"] = before - len(df)

    # ---- STEP 6: validate values ----
    rules = {
        "unknown category": ~df["Category"].isin(VALID_CATEGORIES),
        "unknown store location": ~df["StoreLocation"].isin(VALID_LOCATIONS),
        "unknown suggested action": ~df["SuggestedAction"].isin(VALID_ACTIONS),
        "stock quantity zero or negative": df["StockQty"] <= 0,
        "spoilage chance outside 0-1": (df["SpoilageChance"] < 0) | (df["SpoilageChance"] > 1),
        "expiry date before arrival date": df["ExpiryDate"] < df["ArrivalDate"],
    }
    bad_rows = pd.Series(False, index=df.index)
    for name, mask in rules.items():
        report["Invalid: " + name] = int(mask.sum())
        bad_rows = bad_rows | mask
    report["Dropped: invalid rows (total)"] = int(bad_rows.sum())
    df = df[~bad_rows].copy()

    # ---- STEP 7: calculate the two new columns the rest of the pipeline needs ----
    # Waste_Qty: units of stock actually spoiled. The source file has no direct
    # "quantity wasted" column, so this is a documented derived metric:
    # the full stock batch counts as wasted only if it was marked spoiled.
    df["Waste_Qty"] = df["StockQty"].where(df["IsSpoiled"], 0).astype(int)
    df["Waste_Status"] = df["IsSpoiled"].map({True: "Spoiled", False: "Not Spoiled"})

    # ---- STEP 8: sort and save ----
    df = df.sort_values(["ArrivalDate", "StoreLocation", "Category", "StoreID"]).reset_index(drop=True)
    df = df[FINAL_COLUMNS]
    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    df.to_csv(output_path, index=False, date_format="%Y-%m-%d")
    report["Rows saved (cleaned)"] = len(df)

    return df, report


def self_check(df):
    checks = {
        "No duplicate rows": df.duplicated().sum() == 0,
        "No missing values in any column": df.isna().sum().sum() == 0,
        "Waste_Qty equals StockQty exactly when Spoiled, else 0":
            ((df["Waste_Status"] == "Spoiled") == (df["Waste_Qty"] == df["StockQty"])).all()
            and ((df["Waste_Status"] == "Not Spoiled") == (df["Waste_Qty"] == 0)).all(),
        "SpoilageChance is between 0 and 1": df["SpoilageChance"].between(0, 1).all(),
        "ExpiryDate is never before ArrivalDate": (df["ExpiryDate"] >= df["ArrivalDate"]).all(),
    }
    return checks


def main():
    parser = argparse.ArgumentParser(description="Clean the real smart waste inventory dataset.")
    parser.add_argument("--input", default="data/raw/enhanced_smart_waste_dataset_v1.csv")
    parser.add_argument("--output", default="data/cleaned/waste_cleaned.csv")
    args = parser.parse_args()

    df, report = clean(args.input, args.output)

    print("===== CLEANING REPORT =====")
    for name, value in report.items():
        print("%-55s %d" % (name, value))

    print("\n===== FIRST 5 CLEANED ROWS =====")
    print(df[["StoreID", "ItemName", "Category", "StoreLocation", "ArrivalDate",
               "StockQty", "Waste_Status", "Waste_Qty", "SpoilageChance"]].head(5).to_string(index=False))

    print("\n===== WASTE SUMMARY =====")
    print("Total items     : %d" % len(df))
    print("Spoiled items   : %d (%.1f%%)" % (
        (df["Waste_Status"] == "Spoiled").sum(),
        (df["Waste_Status"] == "Spoiled").mean() * 100))
    print("Total units wasted (Waste_Qty) : %d" % df["Waste_Qty"].sum())

    print("\n===== SELF-CHECK =====")
    all_ok = True
    for name, ok in self_check(df).items():
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        all_ok = all_ok and bool(ok)

    print("\nSaved to: %s" % args.output)
    print("RESULT: %s" % ("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"))


if __name__ == "__main__":
    main()