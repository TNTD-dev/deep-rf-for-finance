// Number formatters shared by chart tooltips + table cells.

export const formatPercent = (v: number, decimals = 1): string =>
  `${v >= 0 ? "+" : ""}${(v * 100).toFixed(decimals)}%`;

export const formatVND = (v: number): string => {
  // Compact form: 1_426_553 → "1.43M ₫"
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B ₫`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)}M ₫`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(0)}K ₫`;
  return `${v.toFixed(0)} ₫`;
};

export const formatUSD = (v: number): string => `$${v.toFixed(2)}`;

export const formatDecimal = (v: number, decimals = 2): string => v.toFixed(decimals);
