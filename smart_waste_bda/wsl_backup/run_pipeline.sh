#!/bin/bash
# run_pipeline.sh
# Runs the entire Hadoop-side pipeline in the correct order:
#   start services -> MapReduce (5 jobs) -> PySpark (7 analyses) ->
#   K-Means clustering -> Bloom Filter/DGIM stream simulation
#
# Safe to re-run any time: it deletes old HDFS output folders first,
# so nothing needs to be cleaned up by hand.
#
# Run from anywhere inside WSL:
#   bash run_pipeline.sh

set -e   # stop immediately if any step fails, instead of continuing on a broken state

echo "===================================================="
echo " STEP 0: Starting Hadoop services"
echo "===================================================="
sudo service ssh start
start-dfs.sh
start-yarn.sh
jps

echo
echo "===================================================="
echo " STEP 1: Running MapReduce jobs (Checkpoint 3)"
echo "===================================================="
cd ~/smart_waste_mapreduce
STREAM_JAR="$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-3.5.0.jar"

run_job () {
    NAME=$1; MAPPER=$2; REDUCER=$3
    echo "--- MapReduce job: $NAME ---"
    hdfs dfs -rm -r -f /smart_waste/output/$NAME
    hadoop jar "$STREAM_JAR" \
      -input /smart_waste/cleaned/waste_cleaned_full.csv \
      -output /smart_waste/output/$NAME \
      -mapper $MAPPER -reducer $REDUCER \
      -file $MAPPER -file $REDUCER
}

run_job by_location    mapper_location.py     reducer_sum.py
run_job by_type        mapper_wastetype.py    reducer_sum.py
run_job by_date        mapper_date.py         reducer_sum.py
run_job by_collection  mapper_collection.py   reducer_collection.py
run_job by_utilization mapper_utilization.py  reducer_sum.py

echo
echo "===================================================="
echo " STEP 2: Running PySpark analysis (Checkpoint 4)"
echo "===================================================="
cd ~/smart_waste_pyspark
spark-submit pyspark_analysis.py

echo
echo "===================================================="
echo " STEP 3: Running K-Means clustering (Checkpoint 5)"
echo "===================================================="
spark-submit kmeans_clustering.py
PROJ="/mnt/c/Users/Priyanka Chavan/Desktop/smart_waste_bda"
cp cluster_chart.png "$PROJ/cluster_chart.png"

echo
echo "===================================================="
echo " STEP 4: Running Bloom Filter / DGIM stream (Checkpoint 6)"
echo "===================================================="
cd ~/smart_waste_stream
python3 stream_analysis.py

echo
echo "===================================================="
echo " STEP 5: Refreshing MongoDB input files (Checkpoint 7)"
echo "===================================================="
mkdir -p "$PROJ/mongo_input"
cd "$PROJ/mongo_input"
for folder in by_location avg_by_location utilization_by_location by_type daily_trend monthly_trend cluster_results; do
    rm -rf "$folder"
    hdfs dfs -get /smart_waste/spark_output/$folder .
done

echo
echo "===================================================="
echo " ALL STEPS COMPLETE"
echo "===================================================="
echo "Next: on Windows, run mongo_loader.py, then 'python -m streamlit run app.py'"
echo "(or just run load_and_dashboard.bat)"
