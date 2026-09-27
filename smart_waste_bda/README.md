# Smart Waste Management using Big Data Analytics

A beginner Big Data Analytics project that simulates smart waste bins across
10 city locations, processes the data through Hadoop and Spark, clusters
locations by waste-generation behaviour with K-Means, demonstrates two
streaming-data techniques (Bloom Filter, DGIM), stores the results in
MongoDB, and displays them on a Streamlit dashboard.

Pipeline:

```
Python data generator -> Preprocessing -> HDFS -> MapReduce -> PySpark
-> K-Means -> Bloom Filter / DGIM -> MongoDB -> Streamlit Dashboard
```

---

## 1. Project Requirements

| Tool | Version used | Runs on |
|---|---|---|
| Python | 3.13.5 (Windows), 3.12.3 (WSL Ubuntu) | Both |
| Java (JDK) | 17 | Both (installed separately on each side) |
| Hadoop | 3.5.0 | WSL Ubuntu |
| Spark | 4.1.2 | WSL Ubuntu |
| MongoDB | 8.0.6 | Windows |
| Ubuntu (WSL2) | 24.04.3 | Windows host |
| Python packages (WSL) | pyspark, matplotlib, pandas, numpy | WSL Ubuntu |
| Python packages (Windows) | pymongo, streamlit, pandas | Windows |

Hadoop and Spark run inside WSL Ubuntu because Hadoop's native Windows support
needs extra unofficial files and is unreliable. MongoDB and the dashboard run
directly on Windows.

---

## 2. Installation

**WSL side** (one-time):
```
sudo apt update
sudo apt install -y openjdk-17-jdk-headless ssh pdsh
# Hadoop 3.5.0 extracted to ~/hadoop, Spark 4.1.2 extracted to ~/spark
# JAVA_HOME, HADOOP_HOME, SPARK_HOME set in ~/.bashrc
pip install pyspark matplotlib pandas numpy --break-system-packages
```

**Windows side** (one-time):
```
python -m pip install pymongo streamlit pandas
```

MongoDB was already installed and runs as a Windows service (`sc query MongoDB`
should show `RUNNING`).

---

## 3. Dataset Preparation (Checkpoint 1)

```
cd "C:\Users\Priyanka Chavan\Desktop\smart_waste_bda"
python src\generate_dataset.py --days 365 --bins-per-type 5 --output data\raw\waste_full.csv
python src\preprocess.py --input data\raw\waste_full.csv --output data\cleaned\waste_cleaned_full.csv
```

Generates 250 simulated bins (10 locations x 5 waste types x 5 bins) over 365
days, then cleans the data: removes duplicates, fixes formats, validates
values, fills recoverable blanks, and calculates `Bin_Utilization_Pct`.

**Result:** 89,571 clean records in `data\cleaned\waste_cleaned_full.csv`.

---

## 4. Hadoop Setup (Checkpoint 2)

Every time WSL is reopened, start the 3 background services:
```
sudo service ssh start
start-dfs.sh
start-yarn.sh
jps    # should show NameNode, DataNode, SecondaryNameNode, ResourceManager, NodeManager
```

---

## 5. HDFS Commands

```
hdfs dfs -mkdir -p /smart_waste/raw /smart_waste/cleaned
hdfs dfs -put waste_cleaned_full.csv /smart_waste/cleaned/
hdfs dfs -ls /smart_waste/cleaned
hdfs dfs -cat /smart_waste/cleaned/waste_cleaned_full.csv | head -5
```

Also viewable at `http://localhost:9870` (Utilities -> Browse the file system).

---

## 6. MapReduce Execution (Checkpoint 3)

5 jobs, run with Hadoop Streaming (Python mappers/reducers in
`~/smart_waste_mapreduce`):

```
hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-3.5.0.jar \
  -input /smart_waste/cleaned/waste_cleaned_full.csv \
  -output /smart_waste/output/by_location \
  -mapper mapper_location.py -reducer reducer_sum.py \
  -file mapper_location.py -file reducer_sum.py
```
(repeat for `by_type`, `by_date`, `by_collection`, `by_utilization` with their
matching mapper/reducer)

**Expected key result:** Market Area highest total waste (331,700.5 kg),
Central Park lowest (91,733.0 kg).

---

## 7. PySpark Execution (Checkpoint 4)

```
cd ~/smart_waste_pyspark
spark-submit pyspark_analysis.py
```

Runs 7 analyses (by location, by type, daily trend, monthly trend, average
waste, bin utilization, high-waste areas) and saves each as one CSV under
`/smart_waste/spark_output/` in HDFS.

**Expected key result:** 4 locations (Market Area, Railway Station,
Industrial Zone, Mall Complex) flagged as high-waste (more than 10% above
the average of 211,065.03 kg).

---

## 8. K-Means Execution (Checkpoint 5)

```
spark-submit kmeans_clustering.py
```

Clusters the 10 locations into Low/Medium/High waste generation using 4
features (total waste, average waste, average utilization, overflow
frequency), saves the result to HDFS, and saves `cluster_chart.png`.

**Expected key result:** 2 High (Market Area, Railway Station), 6 Medium,
2 Low (School Zone, Central Park).

---

## 9. Streaming Execution (Checkpoint 6)

```
cd ~/smart_waste_stream
python3 stream_analysis.py
```

Simulates a stream of bin events. A **Bloom Filter** flags first-time-seen
bins (250 distinct bins, 0 false positives in the tested run). **DGIM**
estimates overflow events in the last 1000 events without storing them,
with error well within its 50% theoretical guarantee.

---

## 10. MongoDB Setup (Checkpoint 7)

```
mkdir mongo_input
cd mongo_input
hdfs dfs -get /smart_waste/spark_output/by_location .
hdfs dfs -get /smart_waste/spark_output/avg_by_location .
hdfs dfs -get /smart_waste/spark_output/utilization_by_location .
hdfs dfs -get /smart_waste/spark_output/by_type .
hdfs dfs -get /smart_waste/spark_output/daily_trend .
hdfs dfs -get /smart_waste/spark_output/monthly_trend .
hdfs dfs -get /smart_waste/spark_output/cluster_results .
```

Then, from Windows:
```
python mongo_loader.py
```

Loads 4 collections into the `smart_waste` database:

| Collection | Documents | Contents |
|---|---|---|
| `location_statistics` | 10 | Waste totals, averages, utilization per location |
| `waste_statistics` | 382 | Waste by type (5) + daily trend (365) + monthly trend (12) |
| `cluster_results` | 10 | K-Means cluster + Waste_Level + overflow frequency per location |
| `overflow_events` | 4,440 | Individual bin-day records that overflowed |

---

## 11. Dashboard Startup (Checkpoint 8)

```
python -m streamlit run app.py
```

Opens at `http://localhost:8501`. Displays: total waste KPIs, waste by
location, waste by type, waste trend over time, bin utilization, high-waste
areas, K-Means clusters (chart + table), and recent overflow events. The
dashboard only reads from MongoDB — it performs no processing.

---

## 12. Running Everything at Once

Two convenience scripts orchestrate the whole pipeline in the correct order:

**Inside WSL** — runs Hadoop startup, all 5 MapReduce jobs, PySpark, K-Means,
and the stream simulation, then refreshes the MongoDB input files:
```
bash run_pipeline.sh
```

**On Windows**, after `run_pipeline.sh` finishes — loads MongoDB and launches
the dashboard:
```
load_and_dashboard.bat
```

---

## Project Folder Structure

```
smart_waste_bda/                       (Windows: Desktop\smart_waste_bda)
├── src/
│   ├── generate_dataset.py
│   └── preprocess.py
├── data/
│   ├── raw/waste_full.csv
│   └── cleaned/waste_cleaned_full.csv
├── mongo_input/                       (CSV copies pulled from HDFS)
├── mongo_loader.py
├── app.py                             (Streamlit dashboard)
├── cluster_chart.png
├── load_and_dashboard.bat
└── run_pipeline.sh                    (copy or symlink into WSL home)

~/hadoop, ~/spark                      (WSL: Hadoop and Spark installs)
~/smart_waste_mapreduce/               (WSL: mapper/reducer scripts)
~/smart_waste_pyspark/                 (WSL: pyspark_analysis.py, kmeans_clustering.py)
~/smart_waste_stream/                  (WSL: stream_analysis.py)
```

---

## Final Project Checklist

- [x] Checkpoint 0 — Software checked, plan agreed
- [x] Checkpoint 1 — Dataset generated and cleaned (89,571 records)
- [x] Checkpoint 2 — HDFS running, data uploaded
- [x] Checkpoint 3 — 5 MapReduce jobs run successfully
- [x] Checkpoint 4 — 7 PySpark analyses run successfully
- [x] Checkpoint 5 — K-Means clustering (2 High / 6 Medium / 2 Low) + chart
- [x] Checkpoint 6 — Bloom Filter + DGIM demonstrated
- [x] Checkpoint 7 — MongoDB loaded (4 collections)
- [x] Checkpoint 8 — Streamlit dashboard working
- [ ] Checkpoint 9 — Integration + README (this document)
- [ ] Checkpoint 10 — Final testing + viva preparation
