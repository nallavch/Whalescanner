import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import type { FC } from "react";
import "./App.css";

// ========== API Configuration ==========
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// ========== API Error Handling ==========
class APIError extends Error {
  statusCode?: number;
  details?: any;
  constructor(message: string, statusCode?: number, details?: any) {
    super(message);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

async function handleResponse(response: Response): Promise<any> {
  if (!response.ok) {
    let errorMessage = `API error: ${response.status} ${response.statusText}`;
    let details = null;
    try {
      const errorData = await response.json();
      errorMessage = errorData.message || errorData.detail || errorMessage;
      details = errorData;
    } catch { }
    throw new APIError(errorMessage, response.status, details);
  }
  try {
    return await response.json();
  } catch (error) {
    throw new APIError("Failed to parse response JSON", response?.status ?? 0, null);
  }
}

// ========== API Functions ==========
const API = {
  fetchDayScan: async (params: any) => {
    const query = new URLSearchParams({
      ticker: params.ticker,
      date: params.date,
      source: params.source,
      block_size: String(params.blockSize),
      trade_pages: String(params.tradePages),
      quote_pages: String(params.tradePages),
      plot: "false",
      ...(params.startTime ? { start_time: params.startTime } : {}),
      ...(params.endTime ? { end_time: params.endTime } : {}),
    });
    const res = await fetch(`${API_BASE}/api/scan/day?${query.toString()}`);
    return await handleResponse(res);
  },

  fetchRangeScan: async (params: any) => {
    const query = new URLSearchParams({
      ticker: params.ticker,
      start_date: params.startDate,
      end_date: params.endDate,
      source: params.source,
      block_size: String(params.blockSize),
    });
    const res = await fetch(`${API_BASE}/api/scan/range?${query.toString()}`);
    return await handleResponse(res);
  },

  fetchScreener: async (payload: any) => {
    const res = await fetch(`${API_BASE}/api/scan/screener`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return await handleResponse(res);
  }
};

// ========== Utility Functions ==========
const formatNumber = (num?: number | null): string => num?.toLocaleString() ?? "-";
const formatPrice = (price?: number | null): string => price != null ? `$${price.toFixed(2)}` : "-";
const formatPercent = (num?: number | null): string => num != null ? `${num.toFixed(1)}%` : "-";

const getConvictionColor = (score: number): string => {
  if (score >= 70) return "#22c55e";
  if (score >= 55) return "#eab308";
  if (score >= 45) return "#6b7280";
  return "#ef4444";
};

const getSetupColor = (label?: string): string => {
  const l = label?.toLowerCase() ?? "";
  if (l.includes("long")) return "#22c55e";
  if (l.includes("short")) return "#ef4444";
  return "#6b7280";
};

// ========== Components ==========

const ConvictionGauge: FC<{ score: number; label: string }> = ({ score, label }) => {
  const radius = 80;
  const stroke = 12;
  const normalizedScore = Math.min(Math.max(score, 0), 100);
  const circumference = radius * Math.PI;
  const strokeDashoffset = circumference - (normalizedScore / 100) * circumference;

  const color = getConvictionColor(score);

  return (
    <div style={{ position: "relative", width: 200, height: 120, display: "flex", flexDirection: "column", alignItems: "center" }}>
      <svg width="200" height="110" viewBox="0 0 200 110">
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#334155" strokeWidth={stroke} strokeLinecap="round" />
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
      </svg>
      <div style={{ position: "absolute", bottom: 10, textAlign: "center" }}>
        <div style={{ fontSize: 32, fontWeight: 700, color: "#fff" }}>{score.toFixed(0)}</div>
        <div style={{ fontSize: 14, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
      </div>
    </div>
  );
};

const Heatmap: FC<{ clusters: any[] }> = ({ clusters }) => {
  if (!clusters || clusters.length === 0) return <div style={{ color: "#64748b", fontSize: 12 }}>No clusters data</div>;

  const times = clusters.map(c => (c.start_ts + c.end_ts) / 2);
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeSpan = maxTime - minTime || 1;

  return (
    <div style={{ height: 60, display: "flex", alignItems: "center", position: "relative", background: "#1e293b", borderRadius: 8, overflow: "hidden" }}>
      {clusters.map((c, i) => {
        const mid = (c.start_ts + c.end_ts) / 2;
        const left = ((mid - minTime) / timeSpan) * 100;
        const color = c.side === "buy" ? "#22c55e" : c.side === "sell" ? "#ef4444" : "#94a3b8";
        const opacity = Math.min(c.total_size / 50000, 1);

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${left}%`,
              width: 4,
              height: "100%",
              background: color,
              opacity: Math.max(0.3, opacity),
            }}
            title={`${c.side.toUpperCase()} ${c.total_size}`}
          />
        );
      })}
    </div>
  );
};

const WhaleTapeTable: FC<{ clusters: any[] }> = ({ clusters }) => {
  if (!clusters || clusters.length === 0) return <div style={{ color: "#64748b", padding: 20 }}>No whale blocks found.</div>;

  // Sort by time descending
  const sorted = [...clusters].reverse();

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h3>Whale Tape (Big Blocks)</h3>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #334155", textAlign: "left", color: "#9ca3af" }}>
              <th style={{ padding: 8 }}>UID</th>
              <th style={{ padding: 8 }}>Time</th>
              <th style={{ padding: 8 }}>Price</th>
              <th style={{ padding: 8 }}>Size</th>
              <th style={{ padding: 8 }}>Value (Est)</th>
              <th style={{ padding: 8 }}>Side</th>
              <th style={{ padding: 8 }}>VWAP</th>
              <th style={{ padding: 8 }}>Dark Pool</th>
              <th style={{ padding: 8 }}>Absorption</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c, i) => {
              const time = new Date(c.end_ts / 1e6).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
              const value = c.total_size * c.vwap;
              return (
                <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                  <td style={{ padding: 8, fontFamily: "monospace", color: "#94a3b8" }}>{c.id}</td>
                  <td style={{ padding: 8 }}>{time}</td>
                  <td style={{ padding: 8, fontWeight: 600 }}>{formatPrice(c.vwap)}</td>
                  <td style={{ padding: 8 }}>{formatNumber(c.total_size)}</td>
                  <td style={{ padding: 8 }}>${formatNumber(Math.round(value))}</td>
                  <td style={{ padding: 8, color: c.side === "buy" ? "#22c55e" : c.side === "sell" ? "#ef4444" : "#9ca3b8", fontWeight: 600 }}>
                    {c.side.toUpperCase()}
                  </td>
                  <td style={{ padding: 8 }}>{formatPrice(c.vwap)}</td>
                  <td style={{ padding: 8, color: c.dark_pool_share > 0.2 ? "#ef4444" : "#9ca3af" }}>
                    {(c.dark_pool_share * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: 8 }}>
                    {c.absorption ? (
                      <span style={{
                        padding: "2px 6px",
                        borderRadius: 4,
                        fontSize: 11,
                        background: c.absorption.includes("bullish") ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                        color: c.absorption.includes("bullish") ? "#22c55e" : "#ef4444"
                      }}>
                        {c.absorption.replace("_", " ")}
                      </span>
                    ) : "-"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const FlowAggregationPanel: FC<{ flowData: any }> = ({ flowData }) => {
  const [activeTf, setActiveTf] = useState("5m");

  if (!flowData) return null;

  const buckets = flowData[activeTf] || [];

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3>Aggregated Flow Analysis</h3>
        <div style={{ display: "flex", gap: 6 }}>
          {["5m", "15m", "1h", "4h"].map(tf => (
            <button
              key={tf}
              onClick={() => setActiveTf(tf)}
              style={{ padding: "4px 12px", background: activeTf === tf ? "#22c55e" : "#374151", border: "none", borderRadius: 4, color: activeTf === tf ? "#0f172a" : "#e5e7eb", fontSize: 12, cursor: "pointer", fontWeight: 600 }}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #334155", textAlign: "left", color: "#9ca3af" }}>
              <th style={{ padding: 8 }}>Time Bucket</th>
              <th style={{ padding: 8 }}>Block Count</th>
              <th style={{ padding: 8 }}>Buy Vol</th>
              <th style={{ padding: 8 }}>Sell Vol</th>
              <th style={{ padding: 8 }}>Net Flow</th>
              <th style={{ padding: 8 }}>Sentiment</th>
            </tr>
          </thead>
          <tbody>
            {buckets.length === 0 ? (
              <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "#64748b" }}>No data for this timeframe</td></tr>
            ) : (
              buckets.slice().reverse().map((b: any, i: number) => {
                const time = new Date(b.ts_ns / 1e6).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false });
                const net = b.net_vol;
                const sentiment = net > 0 ? "BULLISH" : net < 0 ? "BEARISH" : "NEUTRAL";
                const color = net > 0 ? "#22c55e" : net < 0 ? "#ef4444" : "#9ca3af";

                return (
                  <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={{ padding: 8, fontWeight: 600 }}>{time}</td>
                    <td style={{ padding: 8 }}>{b.block_count}</td>
                    <td style={{ padding: 8, color: "#22c55e" }}>{formatNumber(b.buy_vol)}</td>
                    <td style={{ padding: 8, color: "#ef4444" }}>{formatNumber(b.sell_vol)}</td>
                    <td style={{ padding: 8, color: color, fontWeight: 700 }}>{formatNumber(net)}</td>
                    <td style={{ padding: 8 }}>
                      <span style={{ padding: "2px 6px", borderRadius: 4, background: `${color}20`, color: color, fontSize: 11 }}>
                        {sentiment}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ========== TradingView Chart Component ==========

// ========== Lightweight Chart Component ==========

import { createChart, ColorType, CrosshairMode, LineStyle, CandlestickSeries, HistogramSeries, createSeriesMarkers } from 'lightweight-charts';

interface LightweightChartProps {
  ticker: string;
  data: any[];
  clusters?: any[];
  supportResistance?: any;
  divergenceEvents?: any[];
  tradeSetup?: any;
}

const LightweightChart: FC<LightweightChartProps> = ({ ticker, data, supportResistance, divergenceEvents, tradeSetup }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return;

    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1e293b' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      localization: {
        timeFormatter: (time: number) => {
          const date = new Date(time * 1000);
          return date.toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
          });
        },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number) => {
          const date = new Date(time * 1000);
          return date.toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
          });
        },
      },
    });
    chartRef.current = chart;

    // 1. Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    const candleData = data.map((d: any) => ({
      time: d.ts_ns / 1e9 as any, // lightweight-charts uses seconds, cast to any/Time to satisfy TS
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    candleSeries.setData(candleData);

    // 2. Volume Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // set as an overlay by setting a distinct priceScaleId? No, usually overlay
    });

    // Overlay volume at bottom
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8, // highest volume bar takes up bottom 20%
        bottom: 0,
      },
    });

    const volumeData = data.map((d: any) => ({
      time: d.ts_ns / 1e9 as any,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
    }));
    volumeSeries.setData(volumeData);

    // 3. Support & Resistance Lines
    if (supportResistance) {
      supportResistance.supports.forEach((price: number) => {
        candleSeries.createPriceLine({
          price: price,
          color: '#22c55e',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'SUP',
        });
      });
      supportResistance.resistances.forEach((price: number) => {
        candleSeries.createPriceLine({
          price: price,
          color: '#ef4444',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'RES',
        });
      });
    }

    // 4. Divergence Markers
    const markers: any[] = [];

    if (divergenceEvents) {
      divergenceEvents.forEach((evt: any) => {
        if (evt.type === 'bullish_absorption') {
          markers.push({
            time: evt.ts_ns / 1e9 as any,
            position: 'belowBar',
            color: '#22c55e',
            shape: 'arrowUp',
            text: 'ABS',
            size: 2,
          });
        } else if (evt.type === 'bearish_absorption') {
          markers.push({
            time: evt.ts_ns / 1e9 as any,
            position: 'aboveBar',
            color: '#ef4444',
            shape: 'arrowDown',
            text: 'ABS',
            size: 2,
          });
        }
      });
    }

    // 5. Trade Setup Marker (if valid)
    if (tradeSetup && tradeSetup.label !== "NEUTRAL") {
      // Place marker at the last bar
      const lastTime = candleData[candleData.length - 1]?.time;
      if (lastTime) {
        markers.push({
          time: lastTime,
          position: tradeSetup.label.includes("LONG") ? 'belowBar' : 'aboveBar',
          color: tradeSetup.label.includes("LONG") ? '#eab308' : '#eab308',
          shape: tradeSetup.label.includes("LONG") ? 'arrowUp' : 'arrowDown',
          text: `SETUP: ${tradeSetup.label}`,
          size: 3
        });
      }
    }

    createSeriesMarkers(candleSeries, markers);

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, supportResistance, divergenceEvents, tradeSetup]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={chartContainerRef} style={{ width: "100%", height: 500 }} />
      <div style={{
        position: "absolute",
        top: 12,
        left: 12,
        background: "rgba(15, 23, 42, 0.9)",
        padding: "8px 12px",
        borderRadius: 8,
        fontSize: 12,
        color: "#e5e7eb",
        zIndex: 10,
        pointerEvents: "none"
      }}>
        <strong>{ticker}</strong>
        {divergenceEvents && divergenceEvents.length > 0 && (
          <div style={{ marginTop: 4, color: "#eab308" }}>
            {divergenceEvents.length} Divergence Events
          </div>
        )}
      </div>
    </div>
  );
};

// ========== Fallback SVG Chart Component ==========

interface Bar { ts_ns: number; close: number }
interface SimpleSVGChartProps { bars?: Bar[]; clusters?: any[]; trendBias?: string; signals?: any }
const SimpleSVGChart: FC<SimpleSVGChartProps> = ({ bars, trendBias, signals }) => {
  if (!bars?.length) {
    return <div style={{ padding: 16, color: "#9ca3af", fontSize: 14 }}>No data for this timeframe</div>;
  }

  const width = 640;
  const height = 220;
  const pad = 24;

  const times = bars.map((b: Bar) => b.ts_ns / 1e6);
  const closes = bars.map((b: Bar) => b.close);

  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const span = maxClose - minClose || 1;

  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeSpan = maxTime - minTime || 1;

  const xScale = (t: number) => pad + ((t - minTime) / timeSpan) * (width - pad * 2);
  const yScale = (p: number) => pad + (1 - (p - minClose) / span) * (height - pad * 2);

  const pricePoints = closes.map((c: number, i: number) => `${xScale(times[i])},${yScale(c)}`).join(" ");

  const bgTint = trendBias === "up" ? "rgba(34, 197, 94, 0.05)" : trendBias === "down" ? "rgba(239, 68, 68, 0.05)" : "transparent";

  return (
    <div style={{ background: bgTint, borderRadius: 12, padding: 12, border: "1px solid #374151" }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }}>
        <polyline fill="none" stroke="#22c55e" strokeWidth={2} points={pricePoints} />
      </svg>
      <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 8 }}>
        {trendBias && <span style={{ marginRight: 12 }}>Trend: <strong>{trendBias}</strong></span>}
        {signals?.divergence && <span>Divergence: <strong>{signals.divergence}</strong></span>}
      </div>
    </div>
  );
};

// ========== Error Boundary ==========

import React from "react";

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: any }> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("ErrorBoundary caught an error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, color: "#ef4444", background: "#1e293b", minHeight: "100vh" }}>
          <h1>Something went wrong.</h1>
          <pre style={{ background: "#0f172a", padding: 20, borderRadius: 8, overflow: "auto" }}>
            {this.state.error?.toString()}
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: 20, padding: "10px 20px", background: "#3b82f6", color: "white", border: "none", borderRadius: 6, cursor: "pointer" }}
          >
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

// ========== Main App ==========

export default function AppWrapper() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

function App() {
  const [ticker, setTicker] = useState("NVDA");
  const [source, setSource] = useState("alpaca");
  const [blockSize, setBlockSize] = useState(10000);
  const [tradePages, setTradePages] = useState(10);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [activeTab, setActiveTab] = useState("day");
  const [timeframe, setTimeframe] = useState("5m");
  const [useAdvancedChart, setUseAdvancedChart] = useState(true);

  const [dayResult, setDayResult] = useState<any | null>(null);
  const [rangeResult, setRangeResult] = useState<any | null>(null);
  const [screenerResult, setScreenerResult] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [startTime, setStartTime] = useState("09:30");
  const [endTime, setEndTime] = useState("16:00");
  const [autoRefresh, setAutoRefresh] = useState(false);

  const [watchlistInput, setWatchlistInput] = useState("AAPL,MSFT,NVDA,TSLA");
  const [sma50Above200, setSma50Above200] = useState(true);
  const [sma150Above200, setSma150Above200] = useState(true);
  const [minRelativeVolume, setMinRelativeVolume] = useState<number | "">(1.5);
  const [distance50, setDistance50] = useState<number | "">(5);
  const [distance150, setDistance150] = useState<number | "">(8);
  const [distance200, setDistance200] = useState<number | "">(10);
  const [showOnlyPassing, setShowOnlyPassing] = useState(true);

  const runDayScan = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.fetchDayScan({
        ticker,
        date,
        source,
        blockSize,
        tradePages,
        startTime,
        endTime
      });
      setDayResult(res);
    } catch (e: any) {
      setError(e.message);
      setDayResult(null);
    } finally {
      setLoading(false);
    }
  }, [ticker, date, source, blockSize, tradePages, startTime, endTime]);

  const runRangeScan = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.fetchRangeScan({
        ticker,
        startDate,
        endDate,
        source,
        blockSize
      });
      setRangeResult(res);
    } catch (e: any) {
      setError(e.message);
      setRangeResult(null);
    } finally {
      setLoading(false);
    }
  }, [ticker, startDate, endDate, source, blockSize]);

  const runScreener = useCallback(async () => {
    const tickers = watchlistInput
      .split(/[\s,\n]+/)
      .map(t => t.trim().toUpperCase())
      .filter(Boolean);

    if (tickers.length === 0) {
      setError("Please provide at least one ticker for the screener.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await API.fetchScreener({
        tickers,
        source,
        criteria: {
          require_sma50_above_200: sma50Above200,
          require_sma150_above_200: sma150Above200,
          min_relative_volume: minRelativeVolume === "" ? null : Number(minRelativeVolume),
          max_distance_percent: {
            sma50: distance50 === "" ? null : Number(distance50),
            sma150: distance150 === "" ? null : Number(distance150),
            sma200: distance200 === "" ? null : Number(distance200)
          }
        }
      });
      setScreenerResult(res);
    } catch (e: any) {
      setError(e.message);
      setScreenerResult(null);
    } finally {
      setLoading(false);
    }
  }, [watchlistInput, source, sma50Above200, sma150Above200, minRelativeVolume, distance50, distance150, distance200]);

  useEffect(() => {
    let interval: any;
    if (autoRefresh && activeTab === "day") {
      interval = setInterval(runDayScan, 60000);
    }
    return () => clearInterval(interval);
  }, [autoRefresh, activeTab, runDayScan]);

  const currentBars = useMemo(() => {
    return dayResult?.intraday_bars?.[timeframe] ?? [];
  }, [dayResult, timeframe]);

  const currentTrendBias = useMemo(() => {
    if (!dayResult?.timeframe_bias) return null;
    return timeframe === "4h" ? dayResult.timeframe_bias["4h"] :
      timeframe === "1h" ? dayResult.timeframe_bias["1h"] :
        dayResult.timeframe_bias["1h"] ?? dayResult.timeframe_bias["4h"];
  }, [dayResult, timeframe]);

  const screenerRows = useMemo(() => {
    if (!screenerResult) return [];
    return (showOnlyPassing ? screenerResult.passed : screenerResult.matches) ?? [];
  }, [screenerResult, showOnlyPassing]);

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="logo">🐋 WhaleScanner</div>

        <div className="control-group">
          <label>Ticker</label>
          <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} />
        </div>

        <div className="control-group">
          <label>Source</label>
          <select value={source} onChange={e => setSource(e.target.value)}>
            <option value="alpaca">Alpaca</option>
            <option value="polygon">Polygon</option>
          </select>
        </div>

        <div className="control-group">
          <label>Block Size</label>
          <input type="number" value={blockSize} onChange={e => setBlockSize(Number(e.target.value))} />
        </div>

        <div className="control-group">
          <label>Pages</label>
          <input type="number" value={tradePages} onChange={e => setTradePages(Number(e.target.value))} />
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button
            onClick={() => setActiveTab("day")}
            style={{ flex: 1, padding: "8px", background: activeTab === "day" ? "#22c55e" : "#334155", border: "none", borderRadius: 6, color: activeTab === "day" ? "#0f172a" : "#e5e7eb", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
          >
            Day
          </button>
          <button
            onClick={() => setActiveTab("range")}
            style={{ flex: 1, padding: "8px", background: activeTab === "range" ? "#22c55e" : "#334155", border: "none", borderRadius: 6, color: activeTab === "range" ? "#0f172a" : "#e5e7eb", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
          >
            Range
          </button>
          <button
            onClick={() => setActiveTab("screener")}
            style={{ flex: 1, padding: "8px", background: activeTab === "screener" ? "#22c55e" : "#334155", border: "none", borderRadius: 6, color: activeTab === "screener" ? "#0f172a" : "#e5e7eb", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
          >
            Screener
          </button>
        </div>

        {activeTab === "day" && (
          <>
            <div className="control-group" style={{ marginTop: 12 }}>
              <label>Date</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)} />
            </div>
            <div className="control-group">
              <label>Time Range</label>
              <div style={{ display: 'flex', gap: 4 }}>
                <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} />
                <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} />
              </div>
            </div>
            <div className="toggle-group" style={{ marginTop: 12 }}>
              <label style={{ fontSize: 12, color: "#9ca3af", display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
                Auto-Refresh (1m)
              </label>
            </div>
            <button className="run-btn" onClick={runDayScan} disabled={loading}>
              {loading ? "Scanning..." : "Run Day Scan"}
            </button>
          </>
        )}

        {activeTab === "range" && (
          <>
            <div className="control-group" style={{ marginTop: 12 }}>
              <label>Start Date</label>
              <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
            </div>
            <div className="control-group">
              <label>End Date</label>
              <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
            </div>
            <button className="run-btn" onClick={runRangeScan} disabled={loading}>
              {loading ? "Scanning..." : "Run Range Scan"}
            </button>
          </>
        )}

        {activeTab === "screener" && (
          <>
            <div className="control-group" style={{ marginTop: 12 }}>
              <label>Watchlist (comma or newline separated)</label>
              <textarea
                value={watchlistInput}
                onChange={e => setWatchlistInput(e.target.value)}
                rows={4}
                style={{ background: "#0f172a", border: "1px solid #334155", color: "#f1f5f9", padding: 10, borderRadius: 6 }}
              />
            </div>

            <div className="toggle-group" style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <label style={{ fontSize: 12, color: "#9ca3af", display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={sma50Above200} onChange={e => setSma50Above200(e.target.checked)} />
                SMA50 &gt; SMA200
              </label>
              <label style={{ fontSize: 12, color: "#9ca3af", display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={sma150Above200} onChange={e => setSma150Above200(e.target.checked)} />
                SMA150 &gt; SMA200
              </label>
              <label style={{ fontSize: 12, color: "#9ca3af", display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={showOnlyPassing} onChange={e => setShowOnlyPassing(e.target.checked)} />
                Show passing tickers only
              </label>
            </div>

            <div className="control-group" style={{ marginTop: 12 }}>
              <label>Min Relative Volume (vs 20D)</label>
              <input
                type="number"
                step="0.1"
                value={minRelativeVolume}
                onChange={e => setMinRelativeVolume(e.target.value === "" ? "" : Number(e.target.value))}
                placeholder="e.g. 1.5"
              />
            </div>

            <div className="control-group">
              <label>Max Distance from SMAs (%)</label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                <input
                  type="number"
                  value={distance50}
                  onChange={e => setDistance50(e.target.value === "" ? "" : Number(e.target.value))}
                  placeholder="SMA50"
                />
                <input
                  type="number"
                  value={distance150}
                  onChange={e => setDistance150(e.target.value === "" ? "" : Number(e.target.value))}
                  placeholder="SMA150"
                />
                <input
                  type="number"
                  value={distance200}
                  onChange={e => setDistance200(e.target.value === "" ? "" : Number(e.target.value))}
                  placeholder="SMA200"
                />
              </div>
            </div>

            <button className="run-btn" onClick={runScreener} disabled={loading}>
              {loading ? "Scanning..." : "Run Screener"}
            </button>
          </>
        )}
      </aside>

      <main className="main-content">
        {error && <div className="error-banner">{error}</div>}

        {activeTab === "day" && dayResult && (
          <div className="dashboard-grid">
            {/* Conviction */}
            <div className="card conviction-card">
              <h3>Trade Conviction</h3>
              <ConvictionGauge score={dayResult.trade_setup.conviction_score} label={dayResult.trade_setup.label} />
              <p className="explanation">{dayResult.trade_setup.explanation}</p>
            </div>

            {/* Stats */}
            <div className="card stats-card">
              <h3>Market Stats</h3>
              <div className="stat-row">
                <span>Total Vol</span>
                <strong>{formatNumber(dayResult.overall_stats.total_volume)}</strong>
              </div>
              <div className="stat-row">
                <span>Block Vol</span>
                <strong>{formatNumber(dayResult.block_stats.total_volume)}</strong>
              </div>
              <div className="stat-row">
                <span>Net Flow</span>
                <strong style={{ color: dayResult.absorption_summary.net_score > 0 ? "#22c55e" : "#ef4444" }}>
                  {dayResult.absorption_summary.net_score.toFixed(2)}
                </strong>
              </div>
              <div className="stat-row">
                <strong>{dayResult.intraday_info.price_zscore?.toFixed(2) ?? "-"}</strong>
              </div>
              <div className="stat-row">
                <span>Regime</span>
                <strong style={{
                  color: dayResult.market_regime === "BULLISH" || dayResult.market_regime === "ACCUMULATION" ? "#22c55e" :
                    dayResult.market_regime === "BEARISH" || dayResult.market_regime === "DISTRIBUTION" ? "#ef4444" : "#9ca3af"
                }}>
                  {dayResult.market_regime ?? "NEUTRAL"}
                </strong>
              </div>
            </div>

            {/* Chart */}
            <div className="card chart-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <h3>Price & Clusters</h3>
                <div style={{ display: "flex", gap: 6 }}>
                  {["1m", "5m", "15m", "1h", "4h"].map(tf => (
                    <button
                      key={tf}
                      onClick={() => setTimeframe(tf)}
                      style={{ padding: "2px 8px", background: timeframe === tf ? "#22c55e" : "#374151", border: "none", borderRadius: 4, color: timeframe === tf ? "#0f172a" : "#e5e7eb", fontSize: 11, cursor: "pointer" }}
                    >
                      {tf}
                    </button>
                  ))}
                  <button
                    onClick={() => setUseAdvancedChart(!useAdvancedChart)}
                    style={{ padding: "2px 8px", background: "#374151", border: "none", borderRadius: 4, color: "#e5e7eb", fontSize: 11, cursor: "pointer" }}
                  >
                    {useAdvancedChart ? "Simple" : "TV"}
                  </button>
                </div>
              </div>

              {useAdvancedChart ? (
                <LightweightChart
                  ticker={dayResult.ticker}
                  data={currentBars}
                  clusters={dayResult.clusters}
                  supportResistance={dayResult.support_resistance}
                  divergenceEvents={dayResult.chart_signals?.divergence_events}
                  tradeSetup={dayResult.trade_setup}
                />
              ) : (
                <SimpleSVGChart
                  bars={currentBars}
                  clusters={dayResult.clusters}
                  trendBias={currentTrendBias}
                  signals={dayResult.chart_signals}
                />
              )}

              <div style={{ marginTop: 16 }}>
                <Heatmap clusters={dayResult.clusters} />
              </div>
            </div>

            {/* Support/Resistance */}
            <div className="card sr-card">
              <h3>Support & Resistance</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div>
                  <span style={{ color: "#ef4444", fontSize: 12 }}>Resistances</span>
                  <div style={{ fontFamily: "monospace", color: "#fca5a5" }}>
                    {dayResult.support_resistance.resistances.map((r: number) => r.toFixed(2)).join(", ")}
                  </div>
                </div>
                <div style={{ textAlign: "center", fontSize: 18, fontWeight: 700, margin: "8px 0" }}>
                  {formatPrice(dayResult.intraday_info.last_price)}
                </div>
                <div>
                  <span style={{ color: "#22c55e", fontSize: 12 }}>Supports</span>
                  <div style={{ fontFamily: "monospace", color: "#86efac" }}>
                    {dayResult.support_resistance.supports.map((s: number) => s.toFixed(2)).join(", ")}
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 16, borderTop: "1px solid #334155", paddingTop: 12 }}>
                <h4 style={{ fontSize: 12, color: "#9ca3af", marginBottom: 8 }}>Timeframe Bias</h4>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: "#9ca3af" }}>1H</span>
                  <strong style={{ fontSize: 12, color: dayResult.timeframe_bias["1h"] === "up" ? "#22c55e" : dayResult.timeframe_bias["1h"] === "down" ? "#ef4444" : "#9ca3b8" }}>
                    {dayResult.timeframe_bias["1h"]?.toUpperCase() ?? "FLAT"}
                  </strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 12, color: "#9ca3af" }}>4H</span>
                  <strong style={{ fontSize: 12, color: dayResult.timeframe_bias["4h"] === "up" ? "#22c55e" : dayResult.timeframe_bias["4h"] === "down" ? "#ef4444" : "#9ca3b8" }}>
                    {dayResult.timeframe_bias["4h"]?.toUpperCase() ?? "FLAT"}
                  </strong>
                </div>
              </div>
            </div>

            {/* Flow Aggregation Panel */}
            <div style={{ gridColumn: "1 / -1" }}>
              <FlowAggregationPanel flowData={dayResult.flow_aggregation} />
            </div>

            {/* Whale Tape */}
            <div style={{ gridColumn: "1 / -1" }}>
              <WhaleTapeTable clusters={dayResult.clusters} />
            </div>
          </div>
        )}

        {activeTab === "range" && rangeResult && (
          <div className="card" style={{ overflowX: "auto" }}>
            <h3>Range Summary ({rangeResult.days.length} days)</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Total Vol</th>
                  <th>Block Vol</th>
                  <th>Block %</th>
                  <th>Block Net</th>
                  <th>Setup</th>
                  <th>Z-Score</th>
                </tr>
              </thead>
              <tbody>
                {rangeResult.days.map((d: any, i: number) => (
                  <tr key={i}>
                    <td>{d.date}</td>
                    <td>{formatNumber(d.total_volume)}</td>
                    <td>{formatNumber(d.block_volume)}</td>
                    <td>{formatPercent(d.block_pct)}</td>
                    <td style={{ color: d.block_net_volume > 0 ? "#22c55e" : "#ef4444" }}>
                      {formatNumber(d.block_net_volume)}
                    </td>
                    <td>
                      <span style={{ color: getSetupColor(d.setup_label), fontWeight: 600 }}>
                        {d.setup_label}
                      </span>
                    </td>
                    <td>{d.price_zscore?.toFixed(2) ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === "screener" && screenerResult && (
          <div className="card" style={{ overflowX: "auto" }}>
            <h3>Watchlist Screener ({screenerRows.length} tickers)</h3>
            <p style={{ color: "#9ca3af", marginTop: -8 }}>
              Showing {showOnlyPassing ? "only passing filters" : "all evaluated"} • Source: {screenerResult.source}
            </p>
            {screenerRows.length === 0 ? (
              <div style={{ padding: 12, color: "#94a3af" }}>No tickers matched the filters.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Close</th>
                    <th>SMA50</th>
                    <th>SMA150</th>
                    <th>SMA200</th>
                    <th>Rel Vol</th>
                    <th>Dist 50</th>
                    <th>Dist 150</th>
                    <th>Dist 200</th>
                    <th>Status</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {screenerRows.map((row: any) => (
                    <tr key={row.ticker}>
                      <td style={{ fontWeight: 700 }}>{row.ticker}</td>
                      <td>{formatPrice(row.close)}</td>
                      <td>{formatPrice(row.sma50)}</td>
                      <td>{formatPrice(row.sma150)}</td>
                      <td>{formatPrice(row.sma200)}</td>
                      <td>{row.relative_volume ? row.relative_volume.toFixed(2) : "-"}</td>
                      <td>{row.distance_pct?.sma50 != null ? `${row.distance_pct.sma50.toFixed(1)}%` : "-"}</td>
                      <td>{row.distance_pct?.sma150 != null ? `${row.distance_pct.sma150.toFixed(1)}%` : "-"}</td>
                      <td>{row.distance_pct?.sma200 != null ? `${row.distance_pct.sma200.toFixed(1)}%` : "-"}</td>
                      <td style={{ color: row.passed ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                        {row.passed ? "PASS" : "FILTERED"}
                      </td>
                      <td style={{ color: "#cbd5e1", fontSize: 12 }}>
                        {row.reasons?.length ? row.reasons.join(", ") : "Meets criteria"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && !error && !dayResult && !rangeResult && !screenerResult && (
          <div className="empty-state">
            <div style={{ fontSize: 48, marginBottom: 16 }}>🐋</div>
            <p>Run a scan to analyze whale flows and absorption patterns</p>
          </div>
        )}
      </main>
    </div>
  );
}