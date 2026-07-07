// Tipos compartidos entre frontend y backend.

export interface StrategyConfig {
  threshold?: number;
  asset_filter?: string[];
  skip_hours_utc?: number[];
  skip_weekdays?: string[];
  only_weekdays?: string[];
  min_volume_usd?: number;
  min_seconds_to_resolution?: number;
  max_seconds_to_resolution?: number;
  dataset?: string;
  half_spread?: number;
  flat_fee?: number;
  fee_rate?: number;
  [key: string]: unknown;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  market_type: string;
  version: string;
  author: string;
  tags: string[];
  initial_bankroll: number;
  stake: number;
  config: StrategyConfig;
}

export interface Trade {
  timestamp: string;
  asset: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  stake_usd: number;
  cost_paid: number;
  pnl: number;
  is_winner: boolean;
  bankroll_after: number;
  extra: Record<string, unknown>;
}

export interface EquityPoint {
  timestamp: string;
  bankroll: number;
  pnl_cumulative: number;
  trades_to_date: number;
}

export interface BacktestMetrics {
  n_trades: number;
  n_wins: number;
  n_losses: number;
  win_rate_pct: number;
  profit_factor: number | null;
  best_trade: number;
  worst_trade: number;
  avg_trade: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
  max_drawdown_pct: number;
  max_drawdown_usd: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  longest_win_streak: number;
  longest_loss_streak: number;
}

export interface BacktestResult {
  strategy_id: string;
  strategy_name: string;
  market_type: string;
  period_start: string;
  period_end: string;
  initial_bankroll: number;
  final_bankroll: number;
  total_pnl: number;
  total_pnl_pct: number;
  trades: Trade[];
  equity_curve: EquityPoint[];
  metrics: BacktestMetrics;
  game_over_at: string | null;
  skipped_markets: number;
  candidate_markets: number;
  config_used: StrategyConfig;
  duration_seconds: number;
}

export interface StrategiesResponse {
  count: number;
  strategies: Strategy[];
}

export interface AssetBreakdown {
  asset: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  pnl_total: number;
  pnl_avg: number;
}

export interface HourBreakdown {
  hour: number;
  trades: number;
  win_rate_pct: number;
  pnl_total: number;
  pnl_avg: number;
}

export interface WeekdayBreakdown {
  weekday: string;
  trades: number;
  win_rate_pct: number;
  pnl_total: number;
  pnl_avg: number;
}

export interface PnlBucket {
  bucket_lo: number;
  bucket_hi: number;
  count: number;
}

export interface DrawdownPoint {
  timestamp: string;
  drawdown_pct: number;
}

export interface BreakdownsResult {
  by_asset: AssetBreakdown[];
  by_hour: HourBreakdown[];
  by_weekday: WeekdayBreakdown[];
  pnl_histogram: PnlBucket[];
  drawdown_curve: DrawdownPoint[];
  duration_seconds: number;
  summary?: { n_trades: number; win_rate_pct: number; total_pnl: number };
}

export interface LiveBotMetrics {
  label: string;
  name: string;
  emoji: string;
  alive: boolean;
  threshold_pp: number;
  description: string;
  bankroll?: number;
  initial_bankroll?: number;
  pct_change_total?: number;
  open_positions?: number;
  closed_total?: number;
  pnl_total?: number;
  pnl_today?: number;
  pnl_week?: number;
  pnl_month?: number;
  win_rate_total?: number;
  win_rate_week?: number;
  trades_today?: number;
  trades_week?: number;
  recent_trades?: Array<{ asset: string; direction: string; pnl: number; result: string; settled_at_utc: string }>;
  error?: string;
}

export interface LiveBotsResponse {
  bots: LiveBotMetrics[];
  summary: {
    total_bankroll: number;
    total_initial: number;
    total_pnl_total: number;
    total_pnl_today: number;
    total_pnl_week: number;
    total_open_positions: number;
    total_closed_positions: number;
    total_trades_today: number;
    n_alive: number;
    n_total: number;
  };
}
