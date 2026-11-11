export interface Overview {
  video_count: number;
  observation_count: number;
  views: number;
  likes: number;
  comments: number;
  engagement_rate: number;
}

export interface AggregateMetric {
  region: string;
  video_count: number;
  views: number;
  likes: number;
  comments: number;
  engagement_rate: number;
}

export interface CountryMetric extends AggregateMetric {
  observation_count: number;
}

export interface CategoryMetric extends AggregateMetric {
  category_id: number | null;
  category: string;
}

export interface ChannelMetric extends AggregateMetric {
  channel_title: string;
}

export interface VideoMetric {
  region: string;
  video_id: string;
  title: string;
  channel_title: string;
  category: string;
  trending_date: string;
  publish_date: string | null;
  views: number;
  likes: number;
  dislikes: number;
  comments: number;
  engagement_rate: number;
}

export interface TrendMetric {
  region: string;
  trending_date: string;
  video_count: number;
  views: number;
  likes: number;
  comments: number;
  engagement_rate: number;
}

export interface DashboardData {
  metadata: {
    analytics_mode: "local" | "hdfs";
    generated_at: string;
    source: string;
    record_count: number;
    latest_video_count: number;
    regions: string[];
    metric_basis: string;
    selected_region?: string;
  };
  overview: Overview;
  countries: CountryMetric[];
  categories: CategoryMetric[];
  channels: ChannelMetric[];
  videos: VideoMetric[];
  trends: TrendMetric[];
}
