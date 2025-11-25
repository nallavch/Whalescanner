// frontend/src/api/flowScanner.ts
// Optimized with better types, error handling, and caching

// ========== Type Definitions ==========

export interface IntradayBar {
    ts_ns: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    buy_vol?: number;
    sell_vol?: number;
}

export interface TradeStats {
    count: number;
    total_volume: number;
    avg_size: number;
    median_size: number;
    buy_volume?: number;
    sell_volume?: number;
}

export interface SupportResistance {
    supports: number[];
    resistances: number[];
    last_close: number | null;
}

export interface IntradayInfo {
    has_volume_spike: boolean;
    volume_spike_ratio: number | null;
    price_zscore: number | null;
    divergence: string | null;
    last_price: number | null;
    last_buy_vol?: number;
    last_vol?: number;
}

export interface ChartSignals {
    divergence?: string | null;
    divergence_ts?: number | null;
    absorption_bias?: "bullish" | "bearish" | "neutral";
    absorption_ts?: string | null;
}

export interface Cluster {
    id: string;
    side: "buy" | "sell" | "mixed" | "neutral";
    vwap: number;
    total_size: number;
    start_ts: number;
    end_ts: number;
    dark_pool_volume?: number;
    dark_pool_share?: number;
    absorption?: string | null;
    trades?: any[];
}

export interface TradeSetup {
    label: "long" | "short" | "neutral" | "long_bias" | "short_bias";
    explanation: string;
    conviction_score: number;
    bias_direction: "up" | "down" | "none";
}

export interface TimeframeBias {
    "1h"?: "up" | "down" | "flat" | null;
    "4h"?: "up" | "down" | "flat" | null;
}

export interface AbsorptionSummary {
    bullish_volume: number;
    bearish_volume: number;
    net_volume: number;
    net_score: number;
}

export interface DayScanResult {
    ticker: string;
    date: string;
    source: string;
    overall_stats: TradeStats;
    block_stats: TradeStats;
    hourly_block_volume?: Record<string, number>;
    clusters: Cluster[];
    support_resistance: SupportResistance;
    intraday_info: IntradayInfo;
    intraday_bars?: Record<string, IntradayBar[]>;
    timeframe_bias?: TimeframeBias;
    chart_signals?: ChartSignals;
    absorption_summary?: AbsorptionSummary;
    trade_setup: TradeSetup;
}

export interface RangeDaySummary {
    date: string;
    total_volume: number;
    block_volume: number;
    block_pct: number;
    // NEW: buy/sell breakdown of block volume
    block_buy_volume?: number;
    block_sell_volume?: number;
    block_buy_pct?: number;   // % of block_volume that is buy
    block_sell_pct?: number;  // % of block_volume that is sell
    block_net_volume?: number; // buy - sell

    setup_label: string;
    has_volume_spike: boolean;
    price_zscore: number | null;
    last_close: number | null;
    supports: number[];
    resistances: number[];
}

export interface RangeScanResult {
    ticker: string;
    source: string;
    start_date: string;
    end_date: string;
    days: RangeDaySummary[];
}

// ========== API Configuration ==========

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// ========== Simple Cache ==========

interface CacheEntry<T> {
    data: T;
    timestamp: number;
}

class SimpleCache {
    private cache = new Map<string, CacheEntry<any>>();

    get<T>(key: string): T | null {
        const entry = this.cache.get(key);
        if (!entry) return null;

        if (Date.now() - entry.timestamp > CACHE_TTL) {
            this.cache.delete(key);
            return null;
        }

        return entry.data as T;
    }

    set<T>(key: string, data: T): void {
        this.cache.set(key, { data, timestamp: Date.now() });
    }

    clear(): void {
        this.cache.clear();
    }
}

const cache = new SimpleCache();

// ========== Error Handling ==========

export class FlowScannerError extends Error {
    public statusCode?: number;
    public details?: any;

    constructor(message: string, statusCode?: number, details?: any) {
        super(message);
        this.name = "FlowScannerError";
        this.statusCode = statusCode;
        this.details = details;
    }
}

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        let errorMessage = `API error: ${response.status} ${response.statusText}`;
        let details: any = null;

        try {
            const errorData = await response.json();
            errorMessage = errorData.message || errorData.detail || errorMessage;
            details = errorData;
        } catch {
            // Response body not JSON
        }

        throw new FlowScannerError(errorMessage, response.status, details);
    }

    try {
        return await response.json();
    } catch (error) {
        throw new FlowScannerError("Failed to parse response JSON");
    }
}

// ========== API Functions ==========

export interface DayScanParams {
    ticker: string;
    date: string;
    source: "alpaca" | "polygon";
    blockSize: number;
    plot?: boolean;
    useCache?: boolean;
    startTime?: string,   // "09:30"
    endTime?: string      // "16:00"
}

export async function fetchDayScan(params: DayScanParams): Promise<DayScanResult> {
    const { ticker, date, source, blockSize, plot = false, useCache = true } = params;

    // Check cache
    const cacheKey = `day:${ticker}:${date}:${source}:${blockSize}`;
    if (useCache) {
        const cached = cache.get<DayScanResult>(cacheKey);
        if (cached) {
            console.log("[Cache] Day scan hit:", cacheKey);
            return cached;
        }
    }

    // Build URL
    const searchParams = new URLSearchParams({
        ticker,
        date,
        source,
        block_size: String(blockSize),
        plot: String(plot),
    });
    if (params.startTime) {
        searchParams.set("start_time", params.startTime);
    }
    if (params.endTime) {
        searchParams.set("end_time", params.endTime);
    }
    const url = `${API_BASE}/api/scan/day?${searchParams.toString()}`;

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
            },
        });

        const data = await handleResponse<DayScanResult>(response);

        // Cache result
        if (useCache) {
            cache.set(cacheKey, data);
        }

        return data;
    } catch (error) {
        if (error instanceof FlowScannerError) {
            throw error;
        }
        throw new FlowScannerError(
            `Network error: ${error instanceof Error ? error.message : "Unknown error"}`
        );
    }
}

export interface RangeScanParams {
    ticker: string;
    startDate: string;
    endDate: string;
    source: "alpaca" | "polygon";
    blockSize: number;
    useCache?: boolean;
    block_buy_volume?: number;
    block_sell_volume?: number;
    block_buy_pct?: number;
    block_sell_pct?: number;
    block_net_volume?: number;    
}

export async function fetchRangeScan(params: RangeScanParams): Promise<RangeScanResult> {
    const { ticker, startDate, endDate, source, blockSize, useCache = true, block_buy_volume, block_sell_volume, block_buy_pct, block_sell_pct, block_net_volume } = params;

    // Check cache
    const cacheKey = `range:${ticker}:${startDate}:${endDate}:${source}:${blockSize}:${block_buy_volume}:${block_sell_volume}:${block_buy_pct}:${block_sell_pct}:${block_net_volume}`;
    if (useCache) {
        const cached = cache.get<RangeScanResult>(cacheKey);
        if (cached) {
            console.log("[Cache] Range scan hit:", cacheKey);
            return cached;
        }
    }

    // Build URL
    const searchParams = new URLSearchParams({
        ticker,
        start_date: startDate,
        end_date: endDate,
        source,
        block_size: String(blockSize),
        block_buy_volume: String(block_buy_volume || ""),
        block_sell_volume: String(block_sell_volume || ""),
        block_buy_pct: String(block_buy_pct || ""),
        block_sell_pct: String(block_sell_pct || ""),
        block_net_volume: String(block_net_volume || ""),
    });

    const url = `${API_BASE}/api/scan/range?${searchParams.toString()}`;

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
            },
        });

        const data = await handleResponse<RangeScanResult>(response);

        // Cache result
        if (useCache) {
            cache.set(cacheKey, data);
        }

        return data;
    } catch (error) {
        if (error instanceof FlowScannerError) {
            throw error;
        }
        throw new FlowScannerError(
            `Network error: ${error instanceof Error ? error.message : "Unknown error"}`
        );
    }
}

// ========== Utility Functions ==========

export function clearCache(): void {
    cache.clear();
    console.log("[Cache] Cleared all entries");
}

export function formatTimestamp(ts_ns: number): string {
    return new Date(ts_ns / 1_000_000).toLocaleString();
}

export function formatVolume(volume: number): string {
    if (volume >= 1_000_000) {
        return `${(volume / 1_000_000).toFixed(2)}M`;
    }
    if (volume >= 1_000) {
        return `${(volume / 1_000).toFixed(2)}K`;
    }
    return volume.toString();
}

export function formatPrice(price: number): string {
    return price.toFixed(2);
}

export function getConvictionColor(conviction: number): string {
    if (conviction >= 70) return "#22c55e";
    if (conviction >= 55) return "#eab308";
    if (conviction >= 45) return "#6b7280";
    if (conviction >= 30) return "#f59e0b";
    return "#ef4444";
}

export function getSetupColor(label: string): string {
    const lower = label.toLowerCase();
    if (lower.includes("long")) return "#22c55e";
    if (lower.includes("short")) return "#ef4444";
    return "#6b7280";
}