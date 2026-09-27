r"""
generate_dataset.py
Creates a simulated (fake but realistic) smart-waste dataset.
The file is deliberately a little "dirty" (duplicates, missing values,
wrong values) so that preprocess.py has something to clean.

Run from the project folder, for example:
    python src\generate_dataset.py
    python src\generate_dataset.py --days 365 --bins-per-type 5 --output data\raw\waste_full.csv
"""

import argparse
import csv
import os
import random
from datetime import date, timedelta

# 10 locations. The number is a "size factor" (bigger = more waste).
LOCATIONS = {
    "Market Area": 1.8,
    "Railway Station": 1.6,
    "Industrial Zone": 1.5,
    "Mall Complex": 1.4,
    "Residential Sector 1": 1.2,
    "Hospital Zone": 1.1,
    "Residential Sector 2": 1.0,
    "Bus Depot": 0.9,
    "School Zone": 0.6,
    "Central Park": 0.5,
}

# 5 waste types with the typical kg of waste per bin per day.
WASTE_TYPES = {"Organic": 40, "Plastic": 20, "Paper": 16, "Glass": 9, "Metal": 7}

HEADER = [
    "Bin_ID", "Date", "Location", "Waste_Type", "Waste_Generated",
    "Bin_Capacity", "Collection_Status", "Collection_Date", "Overflow_Status",
]


def make_bins(rng, bins_per_type):
    """One bin for every (location, waste type, bin number)."""
    bins = []
    for loc_no, (location, size) in enumerate(LOCATIONS.items(), start=1):
        for waste_type, base in WASTE_TYPES.items():
            for k in range(1, bins_per_type + 1):
                expected = base * size * rng.uniform(0.85, 1.15)
                # The bin is a bit bigger than the waste it normally receives.
                capacity = int(round(expected * rng.uniform(1.15, 1.7) / 10.0)) * 10
                bins.append({
                    "id": "B%02d-%s-%02d" % (loc_no, waste_type[:3].upper(), k),
                    "location": location,
                    "waste_type": waste_type,
                    "expected": expected,
                    "capacity": max(capacity, 20),
                })
    return bins


def make_clean_rows(rng, bins, start, days):
    """One record per bin per day."""
    rows = []
    for day_no in range(days):
        today = start + timedelta(days=day_no)
        weekend = 1.10 if today.weekday() >= 5 else 1.0   # a bit more waste on Sat/Sun
        trend = 1 + 0.0004 * day_no                       # waste grows slowly over time
        for b in bins:
            waste = b["expected"] * weekend * trend * rng.gauss(1.0, 0.15)
            waste = round(max(waste, 0.5), 1)

            # Overflow: the day's waste is more than the bin can hold.
            overflow = "Yes" if waste > b["capacity"] else "No"

            # Overflowing bins are collected more often.
            chance = 0.97 if overflow == "Yes" else 0.85
            if rng.random() < chance:
                status = "Collected"
                delay = 0 if rng.random() < 0.7 else 1
                collection_date = (today + timedelta(days=delay)).isoformat()
            else:
                status = "Pending"
                collection_date = ""

            rows.append([
                b["id"], today.isoformat(), b["location"], b["waste_type"],
                str(waste), str(b["capacity"]), status, collection_date, overflow,
            ])
    return rows


def make_dirty(rng, rows):
    """Add realistic problems. Returns the dirty rows and a count of each problem."""
    counts = {"duplicates": 0, "missing": 0, "invalid": 0, "messy_text": 0, "other_date_format": 0}
    dirty = []
    for row in rows:
        row = row[:]
        r = rng.random()
        if r < 0.02:                                   # 2% : one value is missing
            column = rng.choice(HEADER)
            row[HEADER.index(column)] = ""
            counts["missing"] += 1
        elif r < 0.03:                                 # 1% : a wrong value
            kind = rng.choice(["negative_waste", "zero_capacity", "bad_date", "collected_before_date"])
            if kind == "negative_waste":
                row[4] = "-" + row[4]
            elif kind == "zero_capacity":
                row[5] = "0"
            elif kind == "bad_date":
                row[1] = "2025-13-45"
            elif row[7]:                               # collected_before_date
                row[7] = (date.fromisoformat(row[1]) - timedelta(days=2)).isoformat()
            else:
                row[4] = "-" + row[4]
            counts["invalid"] += 1
        elif r < 0.05:                                 # 2% : messy text
            row[2] = row[2].upper()
            row[3] = " " + row[3].lower()
            counts["messy_text"] += 1
        elif r < 0.07:                                 # 2% : date written as DD/MM/YYYY
            row[1] = date.fromisoformat(row[1]).strftime("%d/%m/%Y")
            counts["other_date_format"] += 1

        dirty.append(row)
        if rng.random() < 0.02:                        # 2% : the same row is saved twice
            dirty.append(row[:])
            counts["duplicates"] += 1
    return dirty, counts


def main():
    parser = argparse.ArgumentParser(description="Generate a simulated smart-waste dataset.")
    parser.add_argument("--days", type=int, default=30, help="number of days (default 30)")
    parser.add_argument("--bins-per-type", type=int, default=1,
                        help="bins for each location and waste type (default 1)")
    parser.add_argument("--start-date", default="2025-01-01", help="first date, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=42, help="same seed = same data")
    parser.add_argument("--output", default="data/raw/waste_sample.csv", help="output CSV path")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    bins = make_bins(rng, args.bins_per_type)
    clean_rows = make_clean_rows(rng, bins, date.fromisoformat(args.start_date), args.days)
    dirty_rows, counts = make_dirty(rng, clean_rows)

    folder = os.path.dirname(args.output)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(dirty_rows)

    print("Bins: %d | Days: %d" % (len(bins), args.days))
    print("Clean records generated : %d" % len(clean_rows))
    print("Problems added on purpose: %s" % counts)
    print("Rows written to file    : %d" % len(dirty_rows))
    print("Saved to: %s" % args.output)


if __name__ == "__main__":
    main()