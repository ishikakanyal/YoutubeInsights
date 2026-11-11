import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  ChevronDown,
  CircleHelp,
  Eye,
  Globe2,
  Heart,
  MessageCircle,
  Play,
  RefreshCw,
  Server,
  Sparkles,
  Video,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CategoryMetric, ChannelMetric, DashboardData, TrendMetric, VideoMetric } from "./types";

const regionNames: Record<string, string> = {
  US: "United States",
  CA: "Canada",
  GB: "United Kingdom",
  DE: "Germany",
  FR: "France",
  IN: "India",
  JP: "Japan",
  KR: "South Korea",
  MX: "Mexico",
  RU: "Russia",
};

const colors = ["#c9f36a", "#66d9c0", "#78a9ff", "#ff9f70", "#c79cff"];
const numberFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function compact(value: number) {
  return numberFormat.format(value);
}

function dateLabel(date: string) {
  const parsed = new Date(`${date}T00:00:00`);
  return parsed.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
}

function App() {
  const [region, setRegion] = useState("all");
  const [activeNav, setActiveNav] = useState("overview");
  const [analyticsMode, setAnalyticsMode] = useState<"local" | "hdfs">("local");
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [aboutOpen, setAboutOpen] = useState(false);

  useEffect(() => {
    if (!aboutOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAboutOpen(false);
        setActiveNav("overview");
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [aboutOpen]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/health`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Analytics API returned ${response.status}`);
        return (await response.json()) as { analytics_mode: "local" | "hdfs" };
      })
      .then((health) => setAnalyticsMode(health.analytics_mode))
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name !== "AbortError") {
          console.error("Could not read analytics mode from FastAPI health endpoint.", reason);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const query = region === "all" ? "" : `?region=${encodeURIComponent(region)}`;
    setLoading(true);
    setError(null);
    fetch(`${apiBaseUrl}/api/dashboard${query}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail || `Analytics API returned ${response.status}`);
        }
        return (await response.json()) as DashboardData;
      })
      .then((payload: DashboardData) => {
        setAnalyticsMode(payload.metadata.analytics_mode);
        setData(payload);
      })
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name !== "AbortError") {
          setData(null);
          setError(reason.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [region, refreshKey]);

  const trends = useMemo(() => {
    if (!data) return [];
    const byDate = new Map<string, TrendMetric>();
    for (const row of data.trends) {
      const current = byDate.get(row.trending_date) ?? {
        ...row,
        region: "ALL",
        video_count: 0,
        views: 0,
        likes: 0,
        comments: 0,
      };
      current.video_count += row.video_count;
      current.views += row.views;
      current.likes += row.likes;
      current.comments += row.comments;
      byDate.set(row.trending_date, current);
    }
    return [...byDate.values()].sort((a, b) => a.trending_date.localeCompare(b.trending_date)).map((row) => ({
      ...row,
      engagement_rate: row.views > 0 ? (100 * (row.likes + row.comments)) / row.views : 0,
      dateLabel: dateLabel(row.trending_date),
    }));
  }, [data]);

  const categories = useMemo(() => {
    if (!data) return [];
    if (region !== "all") {
      return [...data.categories]
        .sort((a: CategoryMetric, b: CategoryMetric) => b.views - a.views)
        .slice(0, 7);
    }
    const grouped = new Map<string, CategoryMetric>();
    for (const row of data.categories) {
      const current = grouped.get(row.category) ?? {
        ...row,
        region: "ALL",
        category_id: null,
        video_count: 0,
        views: 0,
        likes: 0,
        comments: 0,
      };
      current.video_count += row.video_count;
      current.views += row.views;
      current.likes += row.likes;
      current.comments += row.comments;
      grouped.set(row.category, current);
    }
    return [...grouped.values()]
      .map((row) => ({
        ...row,
        engagement_rate: row.views > 0 ? (100 * (row.likes + row.comments)) / row.views : 0,
      }))
      .sort((a: CategoryMetric, b: CategoryMetric) => b.views - a.views)
      .slice(0, 7);
  }, [data, region]);

  const channels = useMemo(() => {
    if (!data) return [];
    const channelRegion = region === "all" ? "ALL" : region;
    return data.channels
      .filter((channel) => channel.region === channelRegion)
      .sort((a: ChannelMetric, b: ChannelMetric) => b.views - a.views)
      .slice(0, 12);
  }, [data, region]);

  const videos = useMemo(() => {
    if (!data) return [];
    return [...data.videos].sort((a: VideoMetric, b: VideoMetric) => b.views - a.views).slice(0, 10);
  }, [data]);

  const selectedCountry = data?.countries[0];
  const missingDataset = error?.toLowerCase().includes("local kaggle dataset is missing") ?? false;
  const changeRegion = (value: string) => setRegion(value);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="YouTube Insights home">
          <span className="brand-mark"><Play size={16} fill="white"/></span>
          <span className="brand-name">youtube<span>insights</span></span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          <a className={`nav-item ${activeNav === "overview" ? "active" : ""}`} href="#overview" aria-current={activeNav === "overview" ? "page" : undefined} onClick={() => setActiveNav("overview")}><BarChart3 size={18} /> Overview</a>
          <a className={`nav-item ${activeNav === "trends" ? "active" : ""}`} href="#trends" aria-current={activeNav === "trends" ? "page" : undefined} onClick={() => setActiveNav("trends")}><Activity size={18} /> Trends</a>
          <a className={`nav-item ${activeNav === "categories" ? "active" : ""}`} href="#categories" aria-current={activeNav === "categories" ? "page" : undefined} onClick={() => setActiveNav("categories")}><Sparkles size={18} /> Categories</a>
          <a className={`nav-item ${activeNav === "channels" ? "active" : ""}`} href="#channels" aria-current={activeNav === "channels" ? "page" : undefined} onClick={() => setActiveNav("channels")}><Video size={18} /> Videos & channels</a>
        </nav>
        <div className="sidebar-spacer" />
        <div className="cluster-card">
          <div className="cluster-heading"><span className="status-dot neutral-dot" /> ANALYTICS MODE</div>
          <strong>{analyticsMode === "local" ? "Local Analytics" : "HDFS snapshot"}</strong>
          <span>{analyticsMode === "local" ? "Pandas · local CSVs" : "HDFS · WebHDFS"}</span>
          <div className="cluster-detail"><Server size={13} /> {analyticsMode === "local" ? "No Hadoop/Spark execution" : "Reading persisted results"}</div>
        </div>
        <button className={`nav-item help-link ${activeNav === "about" ? "active" : ""}`} type="button" aria-current={activeNav === "about" ? "page" : undefined} onClick={() => { setActiveNav("about"); setAboutOpen(true); }}><CircleHelp size={17} /> About the data</button>
        <div className="sidebar-footer">YOUTUBE INSIGHTS <span>·</span> v1.0</div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs"><span>Analytics</span><span className="crumb-slash">/</span><strong>{activeNav === "channels" ? "Videos & channels" : activeNav === "about" ? "About the data" : activeNav[0].toUpperCase() + activeNav.slice(1)}</strong></div>
          <div className="topbar-actions">
            <div className="data-status"><span className="status-dot neutral-dot" /> {analyticsMode === "local" ? "Local Analytics" : "HDFS snapshot"}</div>
            <button className="icon-button" aria-label="Refresh dashboard" onClick={() => setRefreshKey((key) => key + 1)}>
              <RefreshCw size={16} />
            </button>
            <div className="avatar">YI</div>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading" id="overview">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> VIDEO PERFORMANCE</div>
              <h1>Trending, in perspective<span>.</span></h1>
              <p>Explore what captured attention across YouTube’s regional trending feeds.</p>
            </div>
            <label className="region-select">
              <Globe2 size={16} />
              <select value={region} onChange={(event) => changeRegion(event.target.value)} aria-label="Filter by region">
                <option value="all">All regions</option>
                {(data?.metadata.regions ?? Object.keys(regionNames)).map((code) => (
                  <option value={code} key={code}>{regionNames[code] ?? code}</option>
                ))}
              </select>
              <ChevronDown size={14} className="select-chevron" />
            </label>
          </section>

          {loading && <div className="notice loading-notice"><RefreshCw size={17} className="spin" /> {analyticsMode === "local" ? "Reading and analyzing the local Kaggle dataset…" : "Loading persisted HDFS analytics…"}</div>}
          {!loading && error && (
            <div className="notice error-notice">
              <div className="notice-icon"><Server size={18} /></div>
              <div>
                <strong>{analyticsMode === "local" && missingDataset ? "Local dataset is missing" : analyticsMode === "local" ? "Local analytics are unavailable" : "HDFS analytics are unavailable"}</strong>
                <p>{error}</p>
                <span>{analyticsMode === "local" ? "Check ANALYTICS_DATASET_DIR and the ten regional CSV/category JSON files." : "Check HDFS WebHDFS connectivity and the persisted Spark output."}</span>
              </div>
              <button onClick={() => setRefreshKey((key) => key + 1)}>Retry</button>
            </div>
          )}

          {data && !loading && (
            <>
              <section className="metric-grid" aria-label="Summary metrics">
                <MetricCard title="Video views" value={compact(data.overview.views)} change="Latest observation" icon={<Eye size={17} />} tone="lime" />
                <MetricCard title="Videos tracked" value={compact(data.overview.video_count)} change="Unique per region" icon={<Play size={16} />} tone="violet" />
                <MetricCard title="Likes" value={compact(data.overview.likes)} change="Latest observation" icon={<Heart size={16} />} tone="coral" />
                <MetricCard title="Engagement rate" value={`${data.overview.engagement_rate.toFixed(2)}%`} change="(Likes + comments) / views" icon={<Activity size={17} />} tone="mint" />
              </section>

              <section className="chart-grid">
                <article className="panel trend-panel" id="trends">
                  <PanelHeading eyebrow="AUDIENCE MOMENTUM" title="Views over time" subtitle="Trending-feed observations · daily snapshots">
                    <span className="legend-chip"><i className="legend-dot lime-dot" /> Views</span>
                  </PanelHeading>
                  {trends.length > 0 ? (
                    <div className="chart-area trend-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={trends} margin={{ top: 16, right: 12, left: -12, bottom: 0 }}>
                          <defs><linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c9f36a" stopOpacity={0.25} /><stop offset="100%" stopColor="#c9f36a" stopOpacity={0} /></linearGradient></defs>
                          <CartesianGrid stroke="#292d2a" vertical={false} />
                          <XAxis dataKey="dateLabel" tick={{ fill: "#777e78", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={44} />
                          <YAxis tickFormatter={compact} tick={{ fill: "#777e78", fontSize: 11 }} axisLine={false} tickLine={false} />
                          <Tooltip content={<ChartTooltip />} />
                          <Area type="monotone" dataKey="views" name="Views observed" stroke="#c9f36a" strokeWidth={2} fill="url(#viewsFill)" activeDot={{ r: 4, fill: "#c9f36a", stroke: "#121512", strokeWidth: 2 }} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : <EmptyChart />}
                  <div className="chart-footnote"><span><i className="status-dot" /> {region === "all" ? "All regional feeds" : regionNames[region]}</span><span>2017–2018 dataset</span></div>
                </article>

                <article className="panel country-panel">
                  <PanelHeading eyebrow="REGIONAL COMPARISON" title="Where attention trends" subtitle={region === "all" ? "Latest observations by trending region" : "Selected trending region"}>
                    <Globe2 size={16} className="heading-icon" />
                  </PanelHeading>
                  {data.countries.length > 0 ? (
                    <div className="chart-area country-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={[...data.countries].sort((a, b) => b.views - a.views)} layout="vertical" margin={{ top: 2, right: 20, left: 4, bottom: 0 }}>
                          <CartesianGrid stroke="#292d2a" horizontal={false} />
                          <XAxis type="number" tickFormatter={compact} tick={{ fill: "#777e78", fontSize: 10 }} axisLine={false} tickLine={false} />
                          <YAxis type="category" dataKey="region" width={34} tick={{ fill: "#aeb5af", fontSize: 11 }} axisLine={false} tickLine={false} />
                          <Tooltip content={<ChartTooltip />} />
                          <Bar dataKey="views" name="Views" radius={[0, 5, 5, 0]} barSize={13}>
                            {data.countries.map((entry, index) => <Cell key={entry.region} fill={colors[index % colors.length]} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : <EmptyChart />}
                  <div className="chart-footnote"><span><i className="legend-dot violet-dot" /> Views</span><span>{region === "all" ? `${data.countries.length} regions` : selectedCountry ? regionNames[selectedCountry.region] : region}</span></div>
                </article>
              </section>

              <section className="lower-grid">
                <article className="panel category-panel" id="categories">
                  <PanelHeading eyebrow="CONTENT MIX" title="Top categories" subtitle="Ranked by latest observed views">
                    <a className="text-link" href="#videos" onClick={() => setActiveNav("channels")}>Explore videos <ArrowUpRight size={13} /></a>
                  </PanelHeading>
                  <div className="category-list">
                    {categories.map((category, index) => {
                      const max = categories[0]?.views || 1;
                      return <div className="category-row" key={`${category.region}-${category.category_id}`}>
                        <span className="category-rank">{String(index + 1).padStart(2, "0")}</span>
                        <span className="category-name" title={category.category}>{category.category}</span>
                        <div className="category-bar"><i style={{ width: `${Math.max(3, (category.views / max) * 100)}%`, background: colors[index % colors.length] }} /></div>
                        <span className="category-value">{compact(category.views)}</span>
                      </div>;
                    })}
                    {categories.length === 0 && <EmptyChart />}
                  </div>
                  <div className="chart-footnote"><span>Category IDs mapped per region</span><span>{region === "all" ? "All regions" : region}</span></div>
                </article>

                <article className="panel engagement-panel">
                  <PanelHeading eyebrow="INTERACTION SIGNAL" title="Engagement by category" subtitle="Likes + comments per view">
                    <MessageCircle size={16} className="heading-icon" />
                  </PanelHeading>
                  <div className="chart-area engagement-chart">
                    {categories.length > 0 ? <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={categories.slice(0, 6)} margin={{ top: 12, right: 8, left: -18, bottom: 0 }}>
                        <CartesianGrid stroke="#292d2a" vertical={false} />
                        <XAxis dataKey="category" tick={{ fill: "#858c86", fontSize: 9 }} axisLine={false} tickLine={false} interval={0} angle={-15} textAnchor="end" height={46} />
                        <YAxis tickFormatter={(value: number) => `${value}%`} tick={{ fill: "#777e78", fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip />} />
                        <Bar dataKey="engagement_rate" name="Engagement rate" radius={[4, 4, 0, 0]} barSize={23}>
                          {categories.slice(0, 6).map((entry, index) => <Cell key={`${entry.region}-${entry.category_id}`} fill={colors[index % colors.length]} />)}
                        </Bar>
                      </ComposedChart>
                    </ResponsiveContainer> : <EmptyChart />}
                  </div>
                  <div className="chart-footnote"><span><i className="legend-dot mint-dot" /> Engagement rate</span><span>Weighted by views</span></div>
                </article>
              </section>

              <section className="panel table-panel" id="channels">
                <PanelHeading eyebrow="CHANNEL LEADERBOARD" title="Channels driving the feed" subtitle="Ranked by latest observed views">
                  <span className="table-count"><BarChart3 size={14} /> {channels.length} channels</span>
                </PanelHeading>
                <div className="table-scroll">
                  <table>
                    <thead><tr><th>CHANNEL</th><th>REGION</th><th>VIDEOS</th><th>VIEWS</th><th>LIKES</th><th>ENGAGEMENT</th></tr></thead>
                    <tbody>
                      {channels.map((channel, index) => (
                        <tr key={`${channel.region}-${channel.channel_title}`}>
                          <td><div className="video-cell"><span className="video-index">{String(index + 1).padStart(2, "0")}</span><div><strong title={channel.channel_title}>{channel.channel_title || "Unknown channel"}</strong></div></div></td>
                          <td><span className="region-pill">{channel.region}</span></td>
                          <td className="numeric-cell">{compact(channel.video_count)}</td>
                          <td className="numeric-cell">{compact(channel.views)}</td>
                          <td className="numeric-cell">{compact(channel.likes)}</td>
                          <td><span className="rate-pill"><ArrowUpRight size={12} /> {channel.engagement_rate.toFixed(2)}%</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {channels.length === 0 && <EmptyChart />}
                </div>
                <div className="chart-footnote table-footnote"><span>Latest observation per video and region</span><span>Top 20 per selected region</span></div>
              </section>

              <section className="panel table-panel" id="videos">
                <PanelHeading eyebrow="TOP PERFORMERS" title="Most viewed videos" subtitle="Latest observation per video and region">
                  <span className="table-count"><Video size={14} /> {data.videos.length} videos</span>
                </PanelHeading>
                <div className="table-scroll">
                  <table>
                    <thead><tr><th>VIDEO</th><th>REGION</th><th>CATEGORY</th><th>VIEWS</th><th>LIKES</th><th>ENGAGEMENT</th><th>LAST TRENDING</th></tr></thead>
                    <tbody>
                      {videos.map((video, index) => (
                        <tr key={`${video.region}-${video.video_id}`}>
                          <td><div className="video-cell"><span className="video-index">{String(index + 1).padStart(2, "0")}</span><div><strong title={video.title}>{video.title || "Untitled video"}</strong><span>{video.channel_title || "Unknown channel"}</span></div></div></td>
                          <td><span className="region-pill">{video.region}</span></td>
                          <td className="muted-cell">{video.category}</td>
                          <td className="numeric-cell">{compact(video.views)}</td>
                          <td className="numeric-cell">{compact(video.likes)}</td>
                          <td><span className="rate-pill"><ArrowUpRight size={12} /> {video.engagement_rate.toFixed(2)}%</span></td>
                          <td className="muted-cell">{video.trending_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {data.videos.length === 0 && <EmptyChart />}
                </div>
                <div className="chart-footnote table-footnote"><span>Ranked by view count</span><span>Top 20 per selected region</span></div>
              </section>

              <footer className="page-footer">
                <div><span className="footer-mark"><Sparkles size={13} /></span><span><strong>Research note</strong> · Trending snapshots, not total YouTube viewership.</span></div>
                <span>Snapshot {new Date(data.metadata.generated_at).toLocaleString()} · {compact(data.metadata.record_count)} valid observations</span>
              </footer>
            </>
          )}
        </div>
      </main>
      {aboutOpen && (
        <div className="about-overlay" onMouseDown={(event) => {
          if (event.target === event.currentTarget) {
            setAboutOpen(false);
            setActiveNav("overview");
          }
        }}>
          <section className="about-dialog" role="dialog" aria-modal="true" aria-labelledby="about-title">
            <header className="about-dialog-header">
              <div>
                <div className="panel-eyebrow">DATASET & METHODOLOGY</div>
                <h2 id="about-title">About the data</h2>
              </div>
              <button className="about-close" type="button" aria-label="Close About the data" onClick={() => { setAboutOpen(false); setActiveNav("overview"); }}><X size={18} /></button>
            </header>
            <div className="about-dialog-content">
              <p>This dashboard uses the <a href="https://www.kaggle.com/datasets/datasnaek/youtube-new" target="_blank" rel="noreferrer">YouTube Trending Video Dataset on Kaggle</a>. It contains daily trending-video observations from ten regional feeds, with video statistics, categories, and channel information.</p>
              <div className="about-facts">
                <article><strong>What views mean</strong><span>Views and engagement come from the dataset’s trending snapshots. They are not total YouTube viewership or viewer location data.</span></article>
                <article><strong>How engagement is calculated</strong><span>(Likes + comments) ÷ views × 100. A zero-view observation has a 0% engagement rate.</span></article>
                <article><strong>Latest-observation metrics</strong><span>Overview, category, channel, and video totals use the latest valid observation for each video in each region. Trends use dated observations.</span></article>
                <article><strong>Current analytics mode</strong><span>{analyticsMode === "local" ? "Local Analytics uses Pandas to process the local CSV and category JSON files; Hadoop and Spark are not running in this mode." : "HDFS snapshot reads persisted analytics from HDFS; it does not start a live Hadoop or Spark job."}</span></article>
              </div>
              {data && <div className="about-data-stats">Current snapshot: {compact(data.metadata.record_count)} valid observations · generated {new Date(data.metadata.generated_at).toLocaleString()}</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function MetricCard({ title, value, change, icon, tone }: { title: string; value: string; change: string; icon: React.ReactNode; tone: string }) {
  return <article className="metric-card">
    <div className="metric-top"><span>{title}</span><i className={`metric-icon ${tone}`}>{icon}</i></div>
    <strong className="metric-value">{value}</strong>
    <div className="metric-foot"><span className="metric-change"><Activity size={12} /> {change}</span><span className="metric-period">DATASET</span></div>
  </article>;
}

function PanelHeading({ eyebrow, title, subtitle, children }: { eyebrow: string; title: string; subtitle: string; children?: React.ReactNode }) {
  return <div className="panel-heading">
    <div><div className="panel-eyebrow">{eyebrow}</div><h2>{title}</h2><p>{subtitle}</p></div>
    {children && <div className="panel-action">{children}</div>}
  </div>;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color?: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><strong>{label}</strong>{payload.map((item) => <span key={item.name}><i style={{ background: item.color }} />{item.name}<b>{item.name.toLowerCase().includes("rate") ? `${Number(item.value).toFixed(2)}%` : compact(item.value)}</b></span>)}</div>;
}

function EmptyChart() {
  return <div className="empty-chart">No results for this selection.</div>;
}

export default App;
