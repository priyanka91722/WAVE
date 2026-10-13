#!/usr/bin/env python3
r"""
kmeans_clustering.py
Groups the 10 locations into 3 clusters (Low / Medium / High waste generation)
using K-Means, based on 4 features per location:
    - total waste generated
    - average waste generated per record
    - average bin utilization
    - overflow frequency (% of records that overflowed)

Run with spark-submit, for example:
    spark-submit kmeans_clustering.py
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans

INPUT_PATH = "hdfs://localhost:9000/smart_waste/cleaned/waste_cleaned_full.csv"
OUTPUT_PATH = "/smart_waste/spark_output/cluster_results"
CHART_PATH = "cluster_chart.png"   # saved in the current folder (~/smart_waste_pyspark)
NUM_CLUSTERS = 3


def main():
    spark = SparkSession.builder.appName("SmartWasteKMeans").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    df = spark.read.csv(INPUT_PATH, header=True, inferSchema=True)
    df = df.withColumn("Waste_Generated", F.col("Waste_Generated").cast("double")) \
           .withColumn("Bin_Utilization_Pct", F.col("Bin_Utilization_Pct").cast("double")) \
           .withColumn("Is_Overflow", (F.col("Overflow_Status") == "Yes").cast("int"))

    # ---------- Step 1: build one feature row per location ----------
    features = (
        df.groupBy("Location")
          .agg(
              F.round(F.sum("Waste_Generated"), 2).alias("Total_Waste_Kg"),
              F.round(F.avg("Waste_Generated"), 2).alias("Avg_Waste_Kg"),
              F.round(F.avg("Bin_Utilization_Pct"), 2).alias("Avg_Utilization_Pct"),
              F.round(F.avg("Is_Overflow") * 100, 2).alias("Overflow_Freq_Pct"),
          )
    )
    print("\n===== FEATURES PER LOCATION (input to K-Means) =====")
    features.orderBy(F.desc("Total_Waste_Kg")).show(truncate=False)

    # ---------- Step 2: assemble + scale features ----------
    # K-Means measures distance, so features must be on a similar scale.
    # Without scaling, Total_Waste_Kg (hundreds of thousands) would completely
    # dominate Overflow_Freq_Pct (0-100) even if overflow is just as important.
    feature_cols = ["Total_Waste_Kg", "Avg_Waste_Kg", "Avg_Utilization_Pct", "Overflow_Freq_Pct"]
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="raw_features")
    assembled = assembler.transform(features)

    scaler = StandardScaler(inputCol="raw_features", outputCol="features",
                             withMean=True, withStd=True)
    scaled = scaler.fit(assembled).transform(assembled)

    # ---------- Step 3: run K-Means ----------
    kmeans = KMeans(k=NUM_CLUSTERS, seed=42, featuresCol="features", predictionCol="cluster")
    model = kmeans.fit(scaled)
    clustered = model.transform(scaled)

    # ---------- Step 4: label clusters as Low / Medium / High ----------
    # K-Means only outputs numbers (0, 1, 2) with no inherent order or meaning.
    # We work out which cluster number is "highest waste" by looking at the
    # average Total_Waste_Kg WITHIN each cluster, then map 0/1/2 to labels.
    cluster_avg = (
        clustered.groupBy("cluster")
                  .agg(F.avg("Total_Waste_Kg").alias("cluster_avg_waste"))
                  .orderBy("cluster_avg_waste")
                  .collect()
    )
    label_names = ["Low", "Medium", "High"][:len(cluster_avg)]
    cluster_to_label = {row["cluster"]: label_names[i] for i, row in enumerate(cluster_avg)}

    label_map_expr = F.create_map([F.lit(x) for pair in cluster_to_label.items() for x in pair])
    result = (
        clustered
        .withColumn("Waste_Level", label_map_expr[F.col("cluster")])
        .select("Location", "Total_Waste_Kg", "Avg_Waste_Kg", "Avg_Utilization_Pct",
                "Overflow_Freq_Pct", "cluster", "Waste_Level")
        .orderBy(F.desc("Total_Waste_Kg"))
    )

    print("\n===== K-MEANS CLUSTER RESULTS =====")
    result.show(truncate=False)

    print("\nCluster meaning (based on average total waste within each cluster):")
    for row in cluster_avg:
        print("  Cluster %d -> %-6s (avg total waste in this cluster: %.2f kg)" %
              (row["cluster"], cluster_to_label[row["cluster"]], row["cluster_avg_waste"]))

    # ---------- Step 5: save results ----------
    result.coalesce(1).write.mode("overwrite").option("header", True).csv(OUTPUT_PATH)
    print("\nResults saved to HDFS: %s" % OUTPUT_PATH)

    # ---------- Step 6: simple visualization ----------
    pdf = result.toPandas()
    make_chart(pdf)

    spark.stop()


def make_chart(pdf):
    import matplotlib
    matplotlib.use("Agg")  # no display available inside WSL; just save the file
    import matplotlib.pyplot as plt

    colors = {"Low": "#2ecc71", "Medium": "#f39c12", "High": "#e74c3c"}

    plt.figure(figsize=(9, 6))
    for level, group in pdf.groupby("Waste_Level"):
        plt.scatter(group["Total_Waste_Kg"], group["Avg_Utilization_Pct"],
                    s=160, label=level, color=colors.get(level, "gray"),
                    edgecolors="black")
        for _, row in group.iterrows():
            plt.annotate(row["Location"], (row["Total_Waste_Kg"], row["Avg_Utilization_Pct"]),
                        textcoords="offset points", xytext=(6, 6), fontsize=8)

    plt.xlabel("Total Waste Generated (kg)")
    plt.ylabel("Average Bin Utilization (%)")
    plt.title("Smart Waste Management: Location Clusters (K-Means, k=3)")
    plt.legend(title="Waste Level")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=150)
    print("\nChart saved to: %s" % CHART_PATH)


if __name__ == "__main__":
    main()
