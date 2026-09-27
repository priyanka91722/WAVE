r"""
preprocess.py
Cleans the raw waste dataset and calculates bin utilization.

Run from the project folder, for example:
    python src\preprocess.py
    python src\preprocess.py --input data\raw\waste_full.csv --output data\cleaned\waste_cleaned_full.csv
"""

import argparse
import os

import pandas as pd

VALID_TYPES = ["Organic", "Plastic", "Paper", "Glass", "Metal"]
VALID_STATUS = ["Collected", "Pending"]
VALID_OVERFLOW = ["Yes", "No"]
MAX_WASTE_KG = 1000

FINAL_COLUMNS = [
    "Bin_ID", "Date", "Location", "Waste_Type", "Waste_Generated", "Bin_Capacity",
    "Collection_Status", "Collection_Date", "Overflow_Status", "Bin_Utilization_Pct",
]


def convert_dates(series):
    """Try YYYY-MM-DD first, then DD/MM/YYYY. Anything else becomes missing (NaT)."""
    first = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    second = pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")
    return first.fillna(second)


def clean(input_path, output_path):
    report = {}

    # ---- Read everything as text first, so nothing is changed silently ----
    df = pd.read_csv(input_path, dtype=str)
    report["Rows read"] = len(df)

    # ---- STEP 1: remove duplicate records ----
    before = len(df)
    df = df.drop_duplicates()
    report["Duplicate rows removed"] = before - len(df)

    # ---- STEP 2: tidy the text (spaces and capital letters) ----
    for col in ["Location", "Waste_Type", "Collection_Status", "Overflow_Status"]:
        df[col] = df[col].str.strip().str.title()
    df["Bin_ID"] = df["Bin_ID"].str.strip().str.upper()

    # ---- STEP 3: convert dates and numbers to proper types ----
    df["Date"] = convert_dates(df["Date"])
    df["Collection_Date"] = convert_dates(df["Collection_Date"])
    df["Waste_Generated"] = pd.to_numeric(df["Waste_Generated"], errors="coerce")
    df["Bin_Capacity"] = pd.to_numeric(df["Bin_Capacity"], errors="coerce")

    # ---- STEP 4: drop rows that cannot be identified ----
    before = len(df)
    df = df.dropna(subset=["Bin_ID", "Date", "Location", "Waste_Type"])
    report["Dropped: missing Bin_ID/Date/Location/Waste_Type (or unreadable Date)"] = before - len(df)

    # ---- STEP 5: validate values (missing values are not judged here) ----
    rules = {
        "unknown waste type": ~df["Waste_Type"].isin(VALID_TYPES),
        "waste not between 0 and %d kg" % MAX_WASTE_KG:
            (df["Waste_Generated"] <= 0) | (df["Waste_Generated"] > MAX_WASTE_KG),
        "bin capacity is zero or negative": df["Bin_Capacity"] <= 0,
        "unknown collection status":
            df["Collection_Status"].notna() & ~df["Collection_Status"].isin(VALID_STATUS),
        "unknown overflow status":
            df["Overflow_Status"].notna() & ~df["Overflow_Status"].isin(VALID_OVERFLOW),
        "collection date before waste date": df["Collection_Date"] < df["Date"],
    }
    bad_rows = pd.Series(False, index=df.index)
    for name, mask in rules.items():
        report["Invalid: " + name] = int(mask.sum())
        bad_rows = bad_rows | mask
    report["Dropped: invalid rows (total)"] = int(bad_rows.sum())
    df = df[~bad_rows].copy()

    # ---- STEP 6: fill the missing values that can be worked out ----
    # 6a. Missing waste amount -> average of the same location + waste type
    was_missing = df["Waste_Generated"].isna()
    average = df.groupby(["Location", "Waste_Type"])["Waste_Generated"].transform("mean")
    df["Waste_Generated"] = df["Waste_Generated"].fillna(average).round(1)
    report["Filled: Waste_Generated"] = int((was_missing & df["Waste_Generated"].notna()).sum())

    # 6b. Missing bin capacity -> the usual capacity of the same bin
    was_missing = df["Bin_Capacity"].isna()
    usual = df.groupby("Bin_ID")["Bin_Capacity"].transform("median")
    df["Bin_Capacity"] = df["Bin_Capacity"].fillna(usual)
    report["Filled: Bin_Capacity"] = int((was_missing & df["Bin_Capacity"].notna()).sum())

    # Rows that still have no waste amount or capacity cannot be used.
    before = len(df)
    df = df.dropna(subset=["Waste_Generated", "Bin_Capacity"]).copy()
    report["Dropped: could not be filled"] = before - len(df)
    df["Bin_Capacity"] = df["Bin_Capacity"].round().astype(int)

    # 6c. Missing collection status -> Collected if there is a collection date
    no_status = df["Collection_Status"].isna()
    df.loc[no_status, "Collection_Status"] = (
        df.loc[no_status, "Collection_Date"].notna().map({True: "Collected", False: "Pending"})
    )
    report["Filled: Collection_Status"] = int(no_status.sum())

    # 6d. Collected but no collection date -> use the waste date
    no_date = (df["Collection_Status"] == "Collected") & df["Collection_Date"].isna()
    df.loc[no_date, "Collection_Date"] = df.loc[no_date, "Date"]
    report["Filled: Collection_Date"] = int(no_date.sum())

    # ---- STEP 7: calculate bin utilization (%) ----
    df["Bin_Utilization_Pct"] = (df["Waste_Generated"] / df["Bin_Capacity"] * 100).round(2)

    # 7b. Missing overflow status -> Yes if utilization is above 100%
    no_overflow = df["Overflow_Status"].isna()
    df.loc[no_overflow, "Overflow_Status"] = (
        (df.loc[no_overflow, "Bin_Utilization_Pct"] > 100).map({True: "Yes", False: "No"})
    )
    report["Filled: Overflow_Status"] = int(no_overflow.sum())

    # ---- STEP 8: sort and save ----
    df = df.sort_values(["Date", "Location", "Waste_Type", "Bin_ID"]).reset_index(drop=True)
    df = df[FINAL_COLUMNS]
    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    df.to_csv(output_path, index=False, date_format="%Y-%m-%d")
    report["Rows saved (cleaned)"] = len(df)

    return df, report


def self_check(df):
    """Simple checks that prove the cleaned data is good."""
    pending_ok = ((df["Collection_Status"] == "Pending") == df["Collection_Date"].isna()).all()
    checks = {
        "No duplicate rows": df.duplicated().sum() == 0,
        "No missing values (Collection_Date may be empty only for Pending)":
            df.drop(columns=["Collection_Date"]).isna().sum().sum() == 0 and pending_ok,
        "Bin_Utilization_Pct column exists": "Bin_Utilization_Pct" in df.columns,
        "All utilization values are above 0": (df["Bin_Utilization_Pct"] > 0).all(),
        "All collection dates are on/after the waste date":
            (df["Collection_Date"].isna() | (df["Collection_Date"] >= df["Date"])).all(),
    }
    return checks


def main():
    parser = argparse.ArgumentParser(description="Clean the raw waste dataset.")
    parser.add_argument("--input", default="data/raw/waste_sample.csv", help="raw CSV")
    parser.add_argument("--output", default="data/cleaned/waste_cleaned.csv", help="cleaned CSV")
    args = parser.parse_args()

    df, report = clean(args.input, args.output)

    print("===== CLEANING REPORT =====")
    for name, value in report.items():
        print("%-72s %d" % (name, value))

    print("\n===== FIRST 5 CLEANED ROWS =====")
    print(df.head(5).to_string(index=False))

    print("\n===== BIN UTILIZATION (%) =====")
    print("Minimum: %.2f | Average: %.2f | Maximum: %.2f" % (
        df["Bin_Utilization_Pct"].min(), df["Bin_Utilization_Pct"].mean(), df["Bin_Utilization_Pct"].max()))
    print("Overflow records (Overflow_Status = Yes): %d" % (df["Overflow_Status"] == "Yes").sum())

    print("\n===== SELF-CHECK =====")
    all_ok = True
    for name, ok in self_check(df).items():
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        all_ok = all_ok and bool(ok)

    print("\nSaved to: %s" % args.output)
    print("RESULT: %s" % ("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"))


if __name__ == "__main__":
    main()