# YouTube Video Analytics Platform

This project analyzes the Kaggle **Trending YouTube Video Statistics** dataset with a real Hadoop MapReduce job and PySpark on YARN, then serves the persisted analytics through FastAPI to a React dashboard. It does not generate or substitute mock analytics. Until the input files have been uploaded and the Spark job has completed, the dashboard/API report that results are unavailable.

## What this dataset can tell us

The ten regional CSVs (US, CA, GB, DE, FR, IN, JP, KR, MX, RU) contain snapshots of videos that were trending in each region during 2017–2018. They are not a census of all YouTube videos, do not contain viewer geography, and are not current YouTube statistics. A region in this application means the trending feed that produced the record.

Each row is one observation of a video in a region on a trending date. A video can occur on many dates and in multiple regions. To avoid summing repeated cumulative view counters as though they were distinct views:

- Overview, country, category, channel, and video ranking metrics use the **latest valid observation per (region, video ID)**.
- Trend series use each dated observation. They chart the view/like/comment counters seen for the trending feed on that date; they are not daily increments or unique viewers.
- Engagement rate is `100 * (likes + comments) / views` for the relevant aggregate. It is zero where views are zero. Likes and comments remain independently available in the results.
- Category names come from the corresponding regional `*_category_id.json`. Unmapped IDs are labeled with their ID.

## Components and data flow

```text
Kaggle ZIP
  -> scripts/ingest_kaggle.sh
  -> HDFS /youtube/raw/{region}videos.csv and *_category_id.json
       -> Java Hadoop MapReduce -> /youtube/analytics/mapreduce-category-summary
       -> PySpark DataFrame job on YARN -> /youtube/analytics/dashboard/part-*.json
                                                  |
                              FastAPI reads small persisted JSON via WebHDFS
                                                  |
                              React dashboard (filters and charts)
```

HDFS holds the source data and job outputs. YARN launches and schedules both distributed jobs. The MapReduce job demonstrates map, shuffle, combiner, and reduce by aggregating observation count, views, likes, and comments by region and category ID. The PySpark job performs parsing, data-quality filtering, category enrichment, latest-observation selection, group-by calculations, and dashboard summarization. It only collects the small grouped summaries needed for the dashboard; it does not collect the raw dataset to the driver.

FastAPI reads Spark's `part-*.json` files through WebHDFS. This keeps the request path independent of Spark and avoids doing a full scan for every dashboard interaction. No local or in-memory sample dataset is used as a fallback.

## Repository layout

```text
analytics/jobs/build_dashboard.py    PySpark analytics submitted to YARN
backend/app/                         FastAPI app, WebHDFS reader, API models/routes
backend/tests/                       Unit tests for snapshot reading/filtering
frontend/                            React + Vite dashboard
hadoop/mapreduce/                    Java MapReduce job and Maven build
scripts/                             Ingest, submit, and cluster verification scripts
overview.md                          This workflow and deployment guide
```

## Applications and downloads

The project is developed in this Windows workspace, but the Hadoop cluster should use Linux. Install the applications on the machines listed below; the React UI, API, and cluster do not all need to run on every PC.

| Application | Install on | Purpose |
|---|---|---|
| Ubuntu Server 22.04 LTS | Each of the 3 cluster PCs | Recommended OS baseline; keeps the Hadoop/Java/Python runtime consistent. Back up or preserve existing data before installing an OS. |
| OpenJDK 11 (JDK) | All 3 cluster PCs | Hadoop, YARN, MapReduce and Spark JVM runtime. Use the same supported Java version on all nodes. |
| Apache Hadoop 3.3.6 | All 3 cluster PCs | HDFS, YARN, Hadoop command-line tools and MapReduce. Configure it for the same cluster on every PC. |
| Apache Spark 3.5.3 (Hadoop 3 build) | Master; workers need compatible runtime/JAR access as described below | PySpark analytics submitted to YARN. Use a distribution compatible with the installed Hadoop 3.3.x cluster. |
| Python 3.10 | Master and both workers | PySpark driver and worker Python runtime. Install the same Python minor version on all nodes. |
| Maven 3.9.x | Master/build machine | Builds the Java MapReduce JAR. Not needed on worker PCs after the JAR is built. |
| OpenSSH server/client | All 3 cluster PCs | Lets the master start/manage Hadoop daemons on the worker PCs. |
| Node.js 22 LTS (includes npm) | Development/UI host only | Installs dependencies, builds, and serves the React/Vite dashboard. Not needed on Hadoop workers. |
| Python 3.12 (current Windows development machine) | Windows development/API host | Runs FastAPI and its virtual environment. The Spark worker Python version is installed separately on cluster machines. |
| Git and Visual Studio Code | Development machine (recommended) | Source control and editing; optional if already installed. |
| Modern web browser | Your viewing machine | Opens the React dashboard and FastAPI docs. |

Use the official Apache downloads for Hadoop and Spark and the OS vendor's trusted package manager for Ubuntu, OpenJDK, Python, OpenSSH and Maven. Node.js downloads are at [nodejs.org](https://nodejs.org/); VS Code at [code.visualstudio.com](https://code.visualstudio.com/). Avoid installing a random Hadoop bundle or mixing Spark builds. Do not install Docker as a requirement for this three-PC deployment.

For YARN deployment, the master needs Spark/PySpark, Hadoop client configuration, and Python. Spark's JARs must be available to executors (for example via Spark's YARN archive mechanism or a consistent cluster installation). The two workers need Hadoop/YARN services, Java, and the same Python interpreter path/version used by PySpark. The MapReduce JAR is built on master and runs inside YARN containers; Maven is not required on each worker.

On the existing Windows development PC, install/use **Node.js 22 LTS** and **Python 3.12** for the UI and API. Do not attempt to make this Windows PC a Hadoop daemon host for the required cluster. Run the three Hadoop nodes on separate Linux PCs.

### Windows laptop: start the app now

Python 3.12 and Node.js 22 are already installed on the current development laptop, so do not download them again. From PowerShell in the project root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
```

In the first terminal, start FastAPI:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

In a second terminal, install the React packages and start Vite:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open the localhost URL printed by Vite. Until the PySpark job has generated a real dashboard snapshot, the page will display an output-unavailable message; this is intentional, not an app-installation failure. Starting FastAPI alone does not install Hadoop or create analytics.

### Optional: add Ubuntu inside Windows (WSL2)

WSL2 lets you practice Linux commands on this laptop without replacing Windows. It is optional and is still only **one computer**, not the required three-PC cluster. In an Administrator PowerShell terminal:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart if Windows requests it, launch **Ubuntu 22.04** from the Start menu, and create its Linux username/password. In the Ubuntu terminal, install baseline tools:

```bash
sudo apt update
sudo apt install -y openjdk-11-jdk maven python3 python3-venv openssh-server
java -version
mvn -version
```

Install Hadoop and Spark only when ready to configure a Linux single-node practice environment. Use the versions in the table above and the matching Apache archives, follow their official installation/configuration guides, and keep the archives/extracted programs within WSL's Linux filesystem. Installing them does not configure HDFS/YARN by itself. WSL's Ubuntu instance cannot count as three separate physical PCs.

## Dataset setup

The Kaggle archive has been downloaded to `data/youtube-new.zip` (210,575,746 bytes) and extracted into `data/youtube-new/`. Its ZIP CRC check passed. The extracted archive contains ten regional CSVs, ten category JSONs, and 375,942 CSV observations total. The data directory is ignored by Git and should remain local; it is not copied into source control. If you need to download it again, use the [Kaggle dataset page](https://www.kaggle.com/datasets/datasnaek/youtube-new).

The original CSV headers and regional category files were checked. A few rows contain invalid UTF-8 bytes in text fields; the inspection reader used replacement decoding to complete the row-count check. The distributed CSV readers use Java/Spark UTF-8 decoding. If malformed text causes parser errors in a cluster run, inspect Spark/Hadoop task logs rather than silently dropping the input.

On Windows PowerShell, extract the archive with:

```powershell
Expand-Archive -LiteralPath data\youtube-new.zip -DestinationPath data\youtube-new -Force
Get-ChildItem data\youtube-new
```

Copy the extracted data directory to the master PC (or download it there), then install the `hdfs` client command on the master, configure it to use the cluster's Hadoop configuration, and set `HADOOP_CONF_DIR`.

From the project root on the master, run:

   ```bash
   chmod +x scripts/*.sh
   HDFS_RAW_DIR=/youtube/raw scripts/ingest_kaggle.sh /path/to/extracted/dataset
   hdfs dfs -ls /youtube/raw
   ```

The ingest script requires regional CSVs and matching category JSON files, validates their names/nonzero sizes, and copies them to HDFS. It does not download the dataset or alter the source files. Keep the ZIP and extracted copy out of Git; `.gitignore` excludes `data/`.

## Three-PC cluster

Use three separate, preferably Linux (e.g. Ubuntu Server) PCs on the same trusted LAN with static DHCP reservations or stable DNS names:

| Machine | Hadoop daemons | Responsibilities |
|---|---|---|
| `master` | NameNode, ResourceManager, JobHistoryServer | Submit jobs; optional FastAPI and React hosting |
| `worker1` | DataNode, NodeManager | HDFS blocks; MapReduce/Spark containers |
| `worker2` | DataNode, NodeManager | HDFS blocks; MapReduce/Spark containers |

The NameNode and ResourceManager are single points of failure in this minimum topology. With only two DataNodes, use HDFS replication factor **2** (not the usual 3). Replication cannot protect against loss of both workers.

### Configure and start Hadoop

Install the same Hadoop 3.x distribution on all three PCs. Use a Java version supported by that exact Hadoop distribution (Java 11 is a practical choice for Hadoop 3.3.x; check the chosen vendor's support matrix). Create the same `core-site.xml`, `hdfs-site.xml`, `mapred-site.xml`, and `yarn-site.xml` under `HADOOP_CONF_DIR` on all hosts:

- `core-site.xml`: `fs.defaultFS = hdfs://master:9000` (or the configured NameNode RPC address).
- `hdfs-site.xml`: `dfs.replication = 2`, plus unique `dfs.namenode.name.dir` on master and `dfs.datanode.data.dir` on each worker.
- `mapred-site.xml`: `mapreduce.framework.name = yarn`.
- `yarn-site.xml`: `yarn.resourcemanager.hostname = master`; configure NodeManager auxiliary services for the Hadoop version's MapReduce shuffle service.
- Configure each machine's `workers` file with `worker1` and `worker2`; configure host resolution consistently on all PCs.

Set `JAVA_HOME`, `HADOOP_HOME`, `HADOOP_CONF_DIR`, and `PATH` consistently. Ensure the Hadoop service account can SSH from master to both workers without an interactive password for daemon startup. Configure the OS firewall to permit the Hadoop RPC, DataNode transfer, NameNode UI, ResourceManager UI, NodeManager, and WebHDFS ports required by the chosen version; restrict these to the cluster LAN. Synchronize clocks and permit enough disk, RAM, and CPU for OS services plus YARN containers.

**First-time format only:** on a new, empty NameNode storage directory, run `hdfs namenode -format` once on master. Never reformat an initialized NameNode; that destroys its namespace metadata. Then start HDFS and YARN from master using the distribution's scripts (commonly `start-dfs.sh` and `start-yarn.sh`). Start the JobHistoryServer if desired (`mapred --daemon start historyserver`).

Verify both workers actually joined and HDFS has live DataNodes:

```bash
hdfs dfsadmin -report
yarn node -list
scripts/verify_cluster.sh
```

The ResourceManager web UI is commonly `http://master:8088`, NameNode UI commonly `http://master:9870`, and WebHDFS commonly `http://master:9870/webhdfs/v1`; ports can vary by version/configuration. Check the actual configuration rather than opening these services beyond the trusted LAN.

## Build and run the jobs

Prerequisites on master: Maven, Hadoop client/config, and Spark with PySpark matching the cluster Hadoop version. Use the same supported Python interpreter on the Spark submission host and workers; set `PYSPARK_PYTHON` to an interpreter path available on each worker.

### 1. Ingest

Follow [Dataset setup](#dataset-setup), then verify the HDFS listing and replication:

```bash
hdfs dfs -ls /youtube/raw
hdfs fsck /youtube/raw -files -blocks
```

### 2. Run Hadoop MapReduce

Build the Java job and submit it to YARN:

```bash
cd hadoop/mapreduce
mvn -DskipTests package
cd ../..
hadoop jar hadoop/mapreduce/target/youtube-mapreduce-1.0.0.jar \
  mr.YouTubeCategorySummary \
  hdfs:///youtube/raw \
  hdfs:///youtube/analytics/mapreduce-category-summary
hdfs dfs -cat /youtube/analytics/mapreduce-category-summary/part-*
```

The output is tab-separated: `region<TAB>category_id<TAB>observation_count,views,likes,comments`. The MapReduce job is independent from the Spark dashboard and exists as an actual Hadoop job requirement; it does not feed fake values into the UI.
Hadoop requires the output path not to exist. For a repeat run, use a new dedicated output directory or remove only the previous result directory after verifying the exact path.

### 3. Run PySpark on YARN

From the project root:

```bash
spark-submit \
  --master yarn \
  --deploy-mode client \
  analytics/jobs/build_dashboard.py \
  --input 'hdfs:///youtube/raw/*videos.csv' \
  --categories 'hdfs:///youtube/raw/*_category_id.json' \
  --output hdfs:///youtube/analytics/dashboard
hdfs dfs -ls /youtube/analytics/dashboard
```

Check `yarn application -list`, the ResourceManager UI, and application logs. Confirm executor/container logs show tasks on **both worker PCs**. A successful local-mode Spark run is not evidence of distributed processing.

To re-run, Spark replaces only its configured output directory. Review the `--output` argument before submitting; do not point it at `/youtube/raw` or another input directory.

### 4. Start FastAPI

On the master (or a host with LAN access to NameNode and DataNode WebHDFS endpoints):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HDFS_WEBHDFS_URL=http://master:9870/webhdfs/v1
export HDFS_USER=hadoop
export HDFS_DASHBOARD_PATH=/youtube/analytics/dashboard
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`HDFS_WEBHDFS_URL` must be reachable by the API host, and the WebHDFS redirect target (the DataNode) must also be reachable. For local development, set `ANALYTICS_SNAPSHOT_FILE` to an actual Spark-produced `part-*.json` file copied from HDFS; without it or a reachable HDFS output, dashboard requests return HTTP 503 rather than sample results.

### 5. Start React

In another terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

By default Vite proxies `/api` requests to `http://localhost:8000`. Set `VITE_API_PROXY_TARGET` before starting Vite if FastAPI is on another host. For a production frontend, configure `VITE_API_BASE_URL` to the API's LAN URL and set `CORS_ORIGINS` on FastAPI to the UI origin before starting the API. Then build with `npm run build`.

## Dashboard/API

The dashboard's region selector filters the persisted result snapshot. It shows latest-observation totals, date-indexed trending-feed snapshots, regional/category comparisons, channel and video rankings, and engagement rate. Data/source date context is shown to avoid confusing historical observations with live YouTube data.

- `GET /api/health`: process liveness.
- `GET /api/dashboard?region=US`: dashboard data; `region` is optional and accepts a two-letter region present in the dataset.
- `GET /docs`: FastAPI's interactive API documentation.

FastAPI returns HTTP 503 with an actionable message if the Spark output is missing/unreadable. It does not return a success-shaped empty dashboard. The source path, generated timestamp, valid/latest record counts, and region list are included in the Spark-produced snapshot metadata.

## Compatibility, network, and scale notes

- This repository can be edited on Windows, but the three-PC Hadoop deployment should use Linux workers/master for the most straightforward Hadoop daemon, SSH, path, and permissions behavior. Native Windows Hadoop requires extra native binaries and is not the recommended cluster route.
- Pin Hadoop, Spark, Java, and Python versions together. Spark's Hadoop client must be compatible with the cluster; PySpark must be available to YARN containers. Do not mix arbitrary `HADOOP_HOME` client jars into a different Spark distribution.
- WebHDFS follows a NameNode redirect to a DataNode for file reads; opening only the NameNode port is insufficient. Secure WebHDFS should replace simple auth on any network that is not trusted.
- Kaggle's archive is modest in size. The cluster demonstrates genuine HDFS/YARN execution, not a meaningful throughput benchmark. Use YARN's application/task logs and per-worker evidence for the academic demo.
- The source category IDs are region-specific. The Spark job joins by `(region, category_id)` rather than assuming a global category mapping.

## Local checks

```bash
python -m venv backend/.venv
# Linux/macOS: source backend/.venv/bin/activate
# Windows PowerShell: .\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
python -m pytest
python -m compileall -q analytics/jobs backend/app
cd frontend && npm ci && npm run build
```

End-to-end distributed acceptance requires the three configured PCs: upload the original dataset, run both jobs with YARN, inspect HDFS outputs, and load the dashboard from the FastAPI host. A local build or unit test alone does not establish distributed execution.
