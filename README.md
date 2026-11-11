# YouTube Video Analytics Platform

An interactive React dashboard backed by FastAPI, Hadoop HDFS/YARN, a Java Hadoop MapReduce job, and PySpark. The dashboard reads persisted analytics produced by Spark; it does not display generated or mock metrics.

> **Current project status:** The frontend and FastAPI backend run on the Windows development laptop. The Kaggle data is present under `data/`. The distributed jobs are implemented, but the Hadoop/Spark cluster still needs to be configured and run. Until a Spark job writes its output to HDFS and FastAPI can read it, the dashboard intentionally reports that analytics are unavailable.

## What the platform analyzes

The Kaggle **Trending YouTube Video Statistics** dataset has ten regional CSVs (US, CA, GB, DE, FR, IN, JP, KR, MX, RU) and region-specific category JSONs. The archive is from 2017–2018 and contains daily observations of videos that appeared in trending feeds. It is not a census of all YouTube videos, not current live data, and does not say where viewers are located. A region means the feed where the observation appeared.

The archive is already downloaded and extracted:

```text
data/youtube-new.zip
data/youtube-new/{US,CA,GB,DE,FR,IN,JP,KR,MX,RU}videos.csv
data/youtube-new/*_category_id.json
```

The ZIP is 210,575,746 bytes; its integrity check passed. The ten CSVs contain 375,942 observations total. Dataset files are excluded from Git by `.gitignore`.

### Metric logic

- Each CSV row is a video observation for a region and trending date. The same video may appear on many dates and in multiple regions.
- Overview, region, category, channel, and video ranking metrics use the **latest valid observation per `(region, video_id)`**. Repeated cumulative view counts are not added as if they were new daily views.
- Trend charts use dated observations and therefore show the counters recorded for trending-feed videos on each date. They are snapshots, not daily increments or unique viewers.
- Engagement rate is `100 * (likes + comments) / views`; it is zero when views are zero. Likes and comments are also reported individually.
- Category names are looked up using `(region, category_id)` because category ID mappings are regional. Unmapped IDs are labeled with their ID.

## Architecture and data flow

```text
Kaggle CSV + regional category JSON
             |
             v
       HDFS /youtube/raw
          /          \
         v            v
 Hadoop MapReduce   PySpark submitted to YARN
 category counts    clean, enrich, rank, summarize
         |            |
         v            v
 HDFS MapReduce     HDFS /youtube/analytics/dashboard/part-*
 output                         |
                                v
                        FastAPI reads WebHDFS
                                |
                                v
                    React dashboard calls REST API
```

**HDFS** stores raw input and job results. **YARN** schedules MapReduce and Spark containers. The Java MapReduce program reads the Kaggle CSVs and uses map, shuffle, combiner, and reduce stages to aggregate observation count, views, likes, and comments by region and category ID. The PySpark job parses and filters rows, joins regional category labels, selects latest observations, calculates aggregates/rankings/trends, and writes dashboard-ready JSON. It processes the source data in Spark; only grouped summaries are collected to the driver.

**FastAPI** serves persisted Spark output through WebHDFS. It does not launch a Spark job for each request. **React** provides filters, KPI cards, trends, regional/category comparisons, channel/video leaderboards, and an explicit historical-data context. Missing Spark results produce an error state rather than a sample dashboard.

## Repository layout

```text
analytics/jobs/build_dashboard.py        PySpark dashboard analytics job
backend/app/                             FastAPI app and WebHDFS snapshot reader
backend/tests/                           API and snapshot unit tests
backend/requirements.txt                 API runtime dependencies
backend/requirements-dev.txt             API test dependencies
frontend/                                React + TypeScript + Vite dashboard
hadoop/mapreduce/                        Java Hadoop MapReduce job and Maven build
scripts/ingest_kaggle.sh                 Validate/copy dataset files into HDFS
scripts/verify_cluster.sh                Show HDFS DataNodes and YARN nodes
data/                                    Local dataset (ignored by Git)
overview.md                              Expanded operations/deployment guide
```

## Run the application on Windows

Python 3.12 and Node.js 22 are already available on the current development laptop. Hadoop/Spark are not required just to open the UI or run the API. Open two PowerShell terminals from the project directory.

### Terminal 1: FastAPI

First-time setup:

```powershell
Set-Location D:\YoutubeInsights
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Start the API:

```powershell
Set-Location D:\YoutubeInsights\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### Terminal 2: React dashboard

First-time setup and start:

```powershell
Set-Location D:\YoutubeInsights\frontend
npm ci
npm run dev
```

Open the localhost URL printed by Vite (normally `http://localhost:5173`). FastAPI's interactive docs are at `http://localhost:8000/docs`; its liveness endpoint is `http://localhost:8000/api/health`.

The dashboard may say analytics are unavailable even though the website works. That message means the Spark output is not available yet; it is expected until the distributed jobs have run and FastAPI is connected to their output. Running just the API and React does not calculate the dataset.

## Required applications and where they go

Ubuntu Server is **not a requirement**. For the academic three-PC cluster, all three physical laptops may keep Windows, but run Hadoop's Linux daemons inside reachable Linux environments. Use bridged-network VMs as a straightforward option. WSL2 is possible, but default NAT networking can block node-to-node connections; verify that all Linux environments can reach each other before choosing it. Three VMs on one laptop do not satisfy the three-separate-PC requirement.

| Software | Install where | Role |
|---|---|---|
| Windows 10/11 | Existing laptops | Host OS can remain Windows. |
| Ubuntu 22.04 LTS (Server or Desktop) | Linux VM/WSL environment on each of the 3 separate laptops | Recommended Linux runtime for cluster services; the Linux nodes must communicate over the LAN. |
| OpenJDK 11 | All three Linux environments | JVM for Hadoop, YARN, MapReduce, and Spark. Match the chosen Hadoop/Spark support matrix. |
| Apache Hadoop 3.3.6 | All three Linux environments | HDFS, YARN, command-line client, and MapReduce framework. |
| Python 3.10 | All three Linux environments | Same PySpark Python runtime/version on driver and worker nodes. |
| Apache Spark 3.5.3 built for Hadoop 3 | Master; make compatible Spark runtime/JARs available to YARN executors | Submits/runs the PySpark dashboard job on YARN. |
| Maven 3.9.x | Master or build PC only | Builds the Java MapReduce JAR; not needed on workers after build. |
| OpenSSH | All Linux environments | Lets the master start/manage Hadoop daemons on the worker environments. |
| Node.js 22 LTS (includes npm) | Development/UI host | React dependency installation, local development server, and production build. Already present on this laptop. |
| Python 3.12 | Windows API/development host | FastAPI virtual environment and local tests. Already present on this laptop. |
| Browser, VS Code, Git | User/development machine | Browser opens the app; editor and Git are recommended, not cluster requirements. |

Use the official sources:

- [Ubuntu Server](https://ubuntu.com/download/server) or [Ubuntu Desktop](https://ubuntu.com/download/desktop)
- [Apache Hadoop 3.3.6 archives](https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/)
- [Apache Spark 3.5.3 archives](https://archive.apache.org/dist/spark/spark-3.5.3/)
- [Apache Maven downloads](https://maven.apache.org/download.cgi)
- [Node.js downloads](https://nodejs.org/)
- On Ubuntu, install OpenJDK/Python/OpenSSH/Maven with the OS package manager.

Do not install Hadoop as a Windows daemon for this deployment. Do not mix arbitrary Hadoop and Spark versions. Docker is not required.

### Optional: Ubuntu on Windows with WSL2

WSL2 is useful for learning Linux or single-laptop practice, but it is one computer, not a three-PC cluster. In Administrator PowerShell:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart if Windows requests it. Launch Ubuntu from Start, create its Linux user, then install baseline packages in the Ubuntu terminal:

```bash
sudo apt update
sudo apt install -y openjdk-11-jdk maven python3 python3-venv openssh-server
java -version
mvn -version
```

Hadoop and Spark still require downloading, configuring, and testing. For a multi-PC cluster, first confirm the Linux environments can connect to each other on the required Hadoop ports; WSL2's default NAT may require extra networking configuration.

## Three-PC cluster topology

Run the Linux environment on each of three separate laptops on the same trusted LAN, with stable IP addresses or DNS names:

| Node | Services | Responsibilities |
|---|---|---|
| `master` | NameNode, ResourceManager, JobHistoryServer | Submit jobs; optional FastAPI/UI hosting; store HDFS namespace metadata. |
| `worker1` | DataNode, NodeManager | Store HDFS blocks; execute YARN containers/tasks. |
| `worker2` | DataNode, NodeManager | Store HDFS blocks; execute YARN containers/tasks. |

With two DataNodes set HDFS replication to **2**; replication factor 3 cannot be satisfied. The single NameNode and ResourceManager are single points of failure in this minimum academic setup.

Install the same Hadoop distribution and supported Java version on all nodes. Configure `core-site.xml`, `hdfs-site.xml`, `mapred-site.xml`, and `yarn-site.xml` consistently:

- `core-site.xml`: set `fs.defaultFS` to the master NameNode URI, for example `hdfs://master:9000`.
- `hdfs-site.xml`: set `dfs.replication=2`; configure a unique NameNode data directory on master and DataNode data directories on each worker.
- `mapred-site.xml`: set `mapreduce.framework.name=yarn`.
- `yarn-site.xml`: set `yarn.resourcemanager.hostname=master`; configure the MapReduce shuffle auxiliary service appropriate for the Hadoop version.
- List `worker1` and `worker2` in the Hadoop `workers` file and make host resolution consistent on all nodes.

Set `JAVA_HOME`, `HADOOP_HOME`, `HADOOP_CONF_DIR`, and `PATH` consistently. Configure OpenSSH access from master to both workers for daemon startup. Permit required Hadoop RPC, DataNode transfer, NameNode, ResourceManager, NodeManager, and WebHDFS traffic only on the trusted cluster network; synchronize clocks and reserve sufficient CPU, memory, and disk.

**Format only a new, empty NameNode directory.** Running `hdfs namenode -format` on an initialized NameNode can destroy its namespace. Start HDFS and YARN from master using the distribution scripts (commonly `start-dfs.sh` and `start-yarn.sh`); start JobHistoryServer if required. Check node status:

```bash
hdfs dfsadmin -report
yarn node -list
```

Typical UIs are NameNode `http://master:9870`, ResourceManager `http://master:8088`, and WebHDFS under `http://master:9870/webhdfs/v1`; verify actual configured ports. FastAPI's WebHDFS client also needs to reach the DataNode address returned by the NameNode redirect.

## Process the dataset on the cluster

The archive is already present in `data/youtube-new/`. Copy that directory to the master (or download/extract it there). Hadoop commands below run in the Linux environment with the cluster configuration loaded. From the project root:

### 1. Upload source files to HDFS

```bash
chmod +x scripts/*.sh
HDFS_RAW_DIR=/youtube/raw scripts/ingest_kaggle.sh /path/to/youtube-new
hdfs dfs -ls /youtube/raw
hdfs fsck /youtube/raw -files -blocks
```

The ingestion script checks that regional CSVs have matching category JSONs, then copies the inputs. It does not modify the source. Keep `data/` out of Git.

### 2. Build and run the actual Hadoop MapReduce job

From the project root:

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

Output records are tab-separated: `region<TAB>category_id<TAB>observation_count,views,likes,comments`. The MapReduce output directory must not already exist. For reruns, choose a new output directory or carefully remove only the intended old output after checking its exact HDFS path.

### 3. Run PySpark on YARN

From the project root on master, with Spark/YARN configured and the same Python interpreter available on workers:

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

Check `yarn application -list`, the ResourceManager UI, and application logs. Confirm task/executor containers ran on **both worker machines**. A local-mode Spark run does not demonstrate distributed execution. The Spark job replaces only its dashboard output directory; never point `--output` at raw input.

### 4. Connect FastAPI to the persisted Spark output

FastAPI may run on master or another host with LAN access to the NameNode and redirected DataNode WebHDFS endpoint. On Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HDFS_WEBHDFS_URL=http://master:9870/webhdfs/v1
export HDFS_USER=hadoop
export HDFS_DASHBOARD_PATH=/youtube/analytics/dashboard
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local development, set `ANALYTICS_SNAPSHOT_FILE` to an actual Spark-produced `part-*` JSON file copied from HDFS. If neither a valid local Spark snapshot nor reachable HDFS output exists, `/api/dashboard` returns HTTP 503 rather than fabricated data.

### 5. Start React and view the dashboard

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Vite proxies `/api` to `http://localhost:8000` by default. Set `VITE_API_PROXY_TARGET` if FastAPI is hosted elsewhere. For a production frontend, set `VITE_API_BASE_URL` to the API URL and set FastAPI's `CORS_ORIGINS` to the UI origin before building/running.

## API and dashboard endpoints

- `GET /api/health` — API process liveness.
- `GET /api/dashboard` — full dashboard snapshot.
- `GET /api/dashboard?region=US` — filter analytics to a dataset region.
- `GET /docs` — interactive FastAPI documentation.

The dashboard presents overview counts/metrics, views-over-time observations, regional comparisons, category engagement, channel ranking, and top video ranking. It labels the data as historical trending observations to avoid implying live or viewer-geographic analytics.

## Compatibility and interpretation notes

- Hadoop is most straightforward to operate on Linux. Windows can remain the laptop host OS; use reachable Linux VMs or a carefully networked WSL2 environment for Hadoop nodes. Native Windows Hadoop is not the recommended cluster route.
- Pin compatible Hadoop, Spark, Java, and Python versions. Spark's YARN executors need Spark's runtime/JARs; Python must be available at a consistent path/version on master and workers.
- WebHDFS reads redirect from NameNode to DataNode, so API connectivity to the NameNode alone is insufficient. Secure WebHDFS should replace simple authentication on an untrusted network.
- The Kaggle archive is relatively small: the project demonstrates distributed processing and cluster operation, not a serious throughput benchmark.
- Regional category ID mappings differ; joins use both region and category ID.

## Development checks

On Windows PowerShell, from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
python -m compileall -q analytics\jobs backend\app
Set-Location frontend
npm ci
npm run build
```

End-to-end acceptance requires a configured three-PC cluster: ingest the original dataset, run Hadoop MapReduce and PySpark through YARN, verify both workers execute tasks, inspect HDFS outputs, and load the dashboard from the FastAPI host. A local frontend build or API unit test alone does not establish distributed execution.
