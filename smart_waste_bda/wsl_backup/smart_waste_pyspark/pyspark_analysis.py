#!/usr/bin/env python3
r"""
pyspark_analysis.py
Runs 7 analyses on the cleaned waste dataset using PySpark, and saves
each result as a single CSV file so Checkpoint 7 (MongoDB) can load them.

Run with spark-submit, for example:
    spark-submit pyspark_analysis.py
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

INPUT_PATH = "hdfs://localhost:9000/smart_waste/cleaned/waste_cleaned_full.csv"
OUTPUT_BASE = "/smart_waste/spark_output"

HIGH_WASTE_THRESHOLD_MULTIPLIER = 1.10  # a location counts as "high waste" if it's
                                         # more than 10% above the average location total


def save_one_csv(df, folder):
    """Spark normally writes many part files. This saves exactly ONE CSV,
    which is much easier for Checkpoint 7 (MongoDB) to read back later."""
    df.coalesce(1).write.mode("overwrite").option("header", True).csv(OUTPUT_BASE + "/" + folder)


def main():
    spark = SparkSession.builder.appName("SmartWasteAnalysis").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")  # hide noisy INFO logs, keep our own prints clean

    df = spark.read.csv(INPUT_PATH, header=True, inferSchema=True)

    df = df.withColumn("Waste_Generated", F.col("Waste_Generated").cast("double")) \
           .withColumn("Bin_Utilization_Pct", F.col("Bin_Utilization_Pct").cast("double"))

    df.cache()
    total_records = df.count()
    print("\nTotal cleaned records loaded into Spark: %d" % total_records)

    # ---------- 1. Total waste by location ----------
    by_location = (
        df.groupBy("Location")
          .agg(F.round(F.sum("Waste_Generated"), 2).alias("Total_Waste_Kg"),
               F.count("*").alias("Records"))
          .orderBy(F.desc("Total_Waste_Kg"))
    )
    print("\n===== 1. TOTAL WASTE BY LOCATION =====")
    by_location.show(truncate=False)
    save_one_csv(by_location, "by_location")

    # ---------- 2. Total waste by waste type ----------
    by_type = (
        df.groupBy("Waste_Type")
          .agg(F.round(F.sum("Waste_Generated"), 2).alias("Total_Waste_Kg"),
               F.count("*").alias("Records"))
          .orderBy(F.desc("Total_Waste_Kg"))
    )
    print("\n===== 2. TOTAL WASTE BY WASTE TYPE =====")
    by_type.show(truncate=False)
    save_one_csv(by_type, "by_type")

    # ---------- 3. Daily waste trend ----------
    daily_trend = (
        df.groupBy("Date")
          .agg(F.round(F.sum("Waste_Generated"), 2).alias("Total_Waste_Kg"))
          .orderBy("Date")
    )
    print("\n===== 3. DAILY WASTE TREND (first 5 days) =====")
    daily_trend.show(5, truncate=False)
    save_one_csv(daily_trend, "daily_trend")

    # ---------- 4. Monthly waste trend ----------
    monthly_trend = (
        df.withColumn("Month", F.date_format("Date", "yyyy-MM"))
          .groupBy("Month")
          .agg(F.round(F.sum("Waste_Generated"), 2).alias("Total_Waste_Kg"))
          .orderBy("Month")
    )
    print("\n===== 4. MONTHLY WASTE TREND =====")
    monthly_trend.show(20, truncate=False)
    save_one_csv(monthly_trend, "monthly_trend")

    # ---------- 5. Average waste generation ----------
    avg_by_location = (
        df.groupBy("Location")
          .agg(F.round(F.avg("Waste_Generated"), 2).alias("Avg_Waste_Kg_Per_Record"))
          .orderBy(F.desc("Avg_Waste_Kg_Per_Record"))
    )
    overall_avg = df.agg(F.round(F.avg("Waste_Generated"), 2).alias("x")).collect()[0][0]
    print("\n===== 5. AVERAGE WASTE GENERATION =====")
    print("Overall average waste per record: %.2f kg" % overall_avg)
    avg_by_location.show(truncate=False)
    save_one_csv(avg_by_location, "avg_by_location")

    # ---------- 6. Bin utilization ----------
    utilization_by_location = (
        df.groupBy("Location")
          .agg(F.round(F.avg("Bin_Utilization_Pct"), 2).alias("Avg_Utilization_Pct"),
               F.round(F.max("Bin_Utilization_Pct"), 2).alias("Max_Utilization_Pct"))
          .orderBy(F.desc("Avg_Utilization_Pct"))
    )
    print("\n===== 6. BIN UTILIZATION BY LOCATION =====")
    utilization_by_location.show(truncate=False)
    save_one_csv(utilization_by_location, "utilization_by_location")

    # ---------- 7. High-waste areas ----------
    location_totals = by_location.select("Location", "Total_Waste_Kg")
    avg_location_total = location_totals.agg(F.avg("Total_Waste_Kg")).collect()[0][0]
    threshold = avg_location_total * HIGH_WASTE_THRESHOLD_MULTIPLIER

    high_waste_areas = (
        location_totals
        .withColumn("Avg_Across_Locations", F.lit(round(avg_location_total, 2)))
        .withColumn("Threshold_Used", F.lit(round(threshold, 2)))
        .filter(F.col("Total_Waste_Kg") > threshold)
        .orderBy(F.desc("Total_Waste_Kg"))
    )
    print("\n===== 7. HIGH-WASTE AREAS =====")
    print("Average total waste across all locations: %.2f kg" % avg_location_total)
    print("A location counts as 'high waste' above  : %.2f kg (avg + 10%%)" % threshold)
    high_waste_areas.show(truncate=False)
    save_one_csv(high_waste_areas, "high_waste_areas")

    print("\nAll 7 analyses complete. Results saved under: %s" % OUTPUT_BASE)

    spark.stop()


if __name__ == "__main__":
    main()
