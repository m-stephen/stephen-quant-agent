-- Independent source prices and lagged liquidity reference; adjusted fractional units.
CREATE TABLE valid_bars AS
SELECT trade_date AS date,instrument,open*adjustment_factor AS op,
       close*adjustment_factor AS cp
FROM daily_source
WHERE open>0 AND close>0 AND adjustment_factor>0
  AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor);
