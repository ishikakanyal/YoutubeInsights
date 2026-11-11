#!/usr/bin/env python3
"""Build a dashboard snapshot from Kaggle regional CSVs using Spark on YARN."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    StringType,
    StructField,
    StructType,
)


CSV_COLUMNS = [
    "video_id",
    "trending_date_raw",
    "title",
    "channel_title",
    "category_id_raw",
    "publish_time_raw",
    "tags",
    "views_raw",
    "likes_raw",
    "dislikes_raw",
    "comment_count_raw",
    "thumbnail_link",
    "comments_disabled_raw",
    "ratings_disabled_raw",
    "video_error_or_removed_raw",
    "description",
]
REGIONS = ("US", "CA", "GB", "DE", "FR", "IN", "JP", "KR", "MX", "RU")
CATEGORY_SCHEMA = StructType(
    [
        StructField(
            "items",
            ArrayType(
                StructType(
                    [
                        StructField("id", StringType(), True),
                        StructField(
                            "snippet",
                            StructType(
                                [
                                    StructField("title", StringType(), True),
                                    StructField("assignable", BooleanType(), True),
                                ]
                            ),
                            True,
                        ),
                    ]
                )
            ),
            True,
        )
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="HDFS glob for regional *videos.csv files")
    parser.add_argument(
        "--categories", required=True, help="HDFS glob for regional *_category_id.json files"
    )
    parser.add_argument("--output", required=True, help="HDFS output directory for dashboard JSON")
    return parser.parse_args()


def load_records(spark: SparkSession, input_path: str) -> DataFrame:
    schema = StructType([StructField(name, StringType(), True) for name in CSV_COLUMNS])
    raw = (
        spark.read.format("csv")
        .schema(schema)
        .option("header", "true")
        .option("multiLine", "true")
        .option("quote", '"')
        .option("escape", '"')
        .option("mode", "PERMISSIVE")
        .load(input_path)
    )
    region = F.regexp_extract(F.input_file_name(), r"/([A-Z]{2})videos\.csv$", 1)
    parsed = (
        raw.withColumn("region", region)
        .withColumn("category_id", F.col("category_id_raw").cast("int"))
        .withColumn("trending_date", F.to_date("trending_date_raw", "yy.dd.MM"))
        .withColumn("views", F.coalesce(F.col("views_raw").cast("long"), F.lit(0)))
        .withColumn("likes", F.coalesce(F.col("likes_raw").cast("long"), F.lit(0)))
        .withColumn("dislikes", F.coalesce(F.col("dislikes_raw").cast("long"), F.lit(0)))
        .withColumn("comments", F.coalesce(F.col("comment_count_raw").cast("long"), F.lit(0)))
        .withColumn("publish_date", F.to_date("publish_time_raw"))
        .withColumn(
            "comments_disabled",
            F.coalesce(F.col("comments_disabled_raw").cast("boolean"), F.lit(False)),
        )
        .withColumn(
            "ratings_disabled",
            F.coalesce(F.col("ratings_disabled_raw").cast("boolean"), F.lit(False)),
        )
        .filter(F.col("region").isin(*REGIONS))
        .filter(F.col("video_id").isNotNull() & (F.length(F.trim("video_id")) > 0))
        .filter(F.col("trending_date").isNotNull())
    )
    return parsed.select(
        "region",
        "video_id",
        "trending_date",
        "publish_date",
        "title",
        "channel_title",
        "category_id",
        "views",
        "likes",
        "dislikes",
        "comments",
        "comments_disabled",
        "ratings_disabled",
    )


def load_categories(spark: SparkSession, categories_path: str) -> DataFrame:
    raw = (
        spark.read.schema(CATEGORY_SCHEMA)
        .option("multiLine", "true")
        .json(categories_path)
    )
    region = F.regexp_extract(F.input_file_name(), r"/([A-Z]{2})_category_id\.json$", 1)
    return (
        raw.select(region.alias("region"), F.explode_outer("items").alias("item"))
        .select(
            "region",
            F.col("item.id").cast("int").alias("category_id"),
            F.col("item.snippet.title").alias("category"),
        )
        .filter(F.col("region").isin(*REGIONS))
        .dropDuplicates(["region", "category_id"])
    )


def with_engagement(frame: DataFrame) -> DataFrame:
    return frame.withColumn(
        "engagement_rate",
        F.when(
            F.col("views") > 0,
            F.round(
                F.lit(100.0) * (F.col("likes") + F.col("comments")) / F.col("views"),
                4,
            ),
        ).otherwise(F.lit(0.0)),
    )


def collect_json_rows(frame: DataFrame) -> list[dict[str, Any]]:
    return [row.asDict(recursive=True) for row in frame.collect()]


def build_payload(
    spark: SparkSession, input_path: str, categories_path: str
) -> dict[str, Any]:
    records = load_records(spark, input_path)
    record_count = records.count()
    if record_count == 0:
        raise ValueError(
            "No valid observations found. Verify the HDFS CSV paths, headers, and trending_date values."
        )

    categories = load_categories(spark, categories_path)
    enriched = (
        records.join(categories, ["region", "category_id"], "left")
        .withColumn("category", F.coalesce("category", F.col("category_id").cast("string")))
        .withColumn("trending_date", F.date_format("trending_date", "yyyy-MM-dd"))
        .withColumn("publish_date", F.date_format("publish_date", "yyyy-MM-dd"))
    )
    latest_window = Window.partitionBy("region", "video_id").orderBy(
        F.col("trending_date").desc()
    )
    latest = with_engagement(
        enriched.withColumn("_row", F.row_number().over(latest_window))
        .filter(F.col("_row") == 1)
        .drop("_row")
    )

    country_metrics = (
        latest.groupBy("region")
        .agg(
            F.countDistinct("video_id").alias("video_count"),
            F.sum("views").alias("views"),
            F.sum("likes").alias("likes"),
            F.sum("comments").alias("comments"),
        )
        .join(
            records.groupBy("region")
            .agg(F.count("*").alias("observation_count")),
            "region",
        )
        .withColumn(
            "engagement_rate",
            F.when(
                F.col("views") > 0,
                F.round(F.lit(100.0) * (F.col("likes") + F.col("comments")) / F.col("views"), 4),
            ).otherwise(F.lit(0.0)),
        )
        .orderBy("region")
    )
    countries = collect_json_rows(country_metrics)
    total_views = sum(row["views"] or 0 for row in countries)
    total_likes = sum(row["likes"] or 0 for row in countries)
    total_comments = sum(row["comments"] or 0 for row in countries)
    total_videos = sum(row["video_count"] or 0 for row in countries)

    category_metrics = (
        latest.groupBy("region", "category_id", "category")
        .agg(
            F.countDistinct("video_id").alias("video_count"),
            F.sum("views").alias("views"),
            F.sum("likes").alias("likes"),
            F.sum("comments").alias("comments"),
        )
    )
    category_metrics = with_engagement(category_metrics).orderBy(
        "region", F.col("views").desc(), "category"
    )

    channel_metrics = (
        latest.groupBy("region", "channel_title")
        .agg(
            F.countDistinct("video_id").alias("video_count"),
            F.sum("views").alias("views"),
            F.sum("likes").alias("likes"),
            F.sum("comments").alias("comments"),
        )
    )
    regional_channel_window = Window.partitionBy("region").orderBy(
        F.col("views").desc(), F.col("channel_title").asc_nulls_last()
    )
    regional_channels = collect_json_rows(
        with_engagement(
            channel_metrics.withColumn("_rank", F.row_number().over(regional_channel_window))
            .filter(F.col("_rank") <= 20)
            .drop("_rank")
        ).orderBy("region", F.col("views").desc())
    )
    global_channel_metrics = (
        latest.groupBy("channel_title")
        .agg(
            F.countDistinct("video_id").alias("video_count"),
            F.sum("views").alias("views"),
            F.sum("likes").alias("likes"),
            F.sum("comments").alias("comments"),
        )
        .withColumn("region", F.lit("ALL"))
    )
    global_channels = collect_json_rows(
        with_engagement(
            global_channel_metrics.orderBy(
                F.col("views").desc(), F.col("channel_title").asc_nulls_last()
            ).limit(20)
        )
    )
    channels = global_channels + regional_channels

    video_window = Window.partitionBy("region").orderBy(
        F.col("views").desc(), F.col("video_id").asc()
    )
    videos = collect_json_rows(
        with_engagement(
            latest.withColumn("_rank", F.row_number().over(video_window))
            .filter(F.col("_rank") <= 20)
            .drop("_rank")
            .select(
                "region",
                "video_id",
                "title",
                "channel_title",
                "category",
                "trending_date",
                "publish_date",
                "views",
                "likes",
                "dislikes",
                "comments",
                "engagement_rate",
            )
        ).orderBy("region", F.col("views").desc())
    )

    trends = collect_json_rows(
        with_engagement(
            enriched.groupBy("region", "trending_date")
            .agg(
                F.countDistinct("video_id").alias("video_count"),
                F.sum("views").alias("views"),
                F.sum("likes").alias("likes"),
                F.sum("comments").alias("comments"),
            )
        ).orderBy("trending_date", "region")
    )

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": input_path,
            "record_count": record_count,
            "latest_video_count": total_videos,
            "regions": [row["region"] for row in countries],
            "metric_basis": "latest observation per region and video; trends use dated observations",
        },
        "overview": {
            "video_count": total_videos,
            "observation_count": record_count,
            "views": total_views,
            "likes": total_likes,
            "comments": total_comments,
            "engagement_rate": round(
                100.0 * (total_likes + total_comments) / total_views, 4
            )
            if total_views
            else 0.0,
        },
        "countries": countries,
        "categories": collect_json_rows(category_metrics),
        "channels": channels,
        "videos": videos,
        "trends": trends,
    }


def write_snapshot(spark: SparkSession, payload: dict[str, Any], output: str) -> None:
    output_uri = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(output).toUri()
    output_location = output_uri.getPath() or ""
    output_segments = output_location.split("/")
    if (
        not output_location.startswith("/youtube/analytics/")
        or ".." in output_segments
        or output_uri.getScheme() not in (None, "hdfs", "viewfs")
    ):
        raise ValueError(
            "Refusing to replace output outside the HDFS /youtube/analytics/ tree. "
            "Choose a dedicated analytics output directory."
        )

    jvm = spark.sparkContext._jvm
    conf = spark.sparkContext._jsc.hadoopConfiguration()
    output_path = jvm.org.apache.hadoop.fs.Path(output)
    filesystem = output_path.getFileSystem(conf)
    token = jvm.java.util.UUID.randomUUID().toString()
    temporary_path = jvm.org.apache.hadoop.fs.Path(output + ".tmp-" + token)
    backup_path = jvm.org.apache.hadoop.fs.Path(output + ".previous-" + token)
    if filesystem.exists(temporary_path):
        filesystem.delete(temporary_path, True)
    json_line = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    try:
        spark.sparkContext.parallelize([json_line], 1).saveAsTextFile(temporary_path.toString())
    except Exception:
        filesystem.delete(temporary_path, True)
        raise

    had_previous = filesystem.exists(output_path)
    if had_previous and not filesystem.rename(output_path, backup_path):
        filesystem.delete(temporary_path, True)
        raise OSError(f"Could not preserve existing Spark output directory: {output}")
    if not filesystem.rename(temporary_path, output_path):
        if had_previous and not filesystem.rename(backup_path, output_path):
            raise OSError(
                f"Could not publish Spark output or restore previous output; "
                f"previous output remains at {backup_path}"
            )
        filesystem.delete(temporary_path, True)
        raise OSError(f"Could not publish Spark dashboard output: {output}")
    if had_previous:
        if not filesystem.delete(backup_path, True):
            raise OSError(f"Dashboard is updated, but old output remains at {backup_path}")


def main() -> int:
    args = parse_args()
    spark = (
        SparkSession.builder.appName("youtube-video-analytics-dashboard")
        .getOrCreate()
    )
    try:
        payload = build_payload(spark, args.input, args.categories)
        write_snapshot(spark, payload, args.output)
        print(
            f"Wrote dashboard snapshot to {args.output}; "
            f"{payload['metadata']['record_count']} valid observations, "
            f"{payload['metadata']['latest_video_count']} latest region/video records."
        )
        return 0
    except Exception as exc:
        print(f"Dashboard analytics failed: {exc}", file=sys.stderr)
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
