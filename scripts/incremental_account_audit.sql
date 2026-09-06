WITH daily AS (
 SELECT *,
   regexp_extract(filename, '(202[34])-(.*)-([012])[.]jsonl$', 1) AS year,
   regexp_extract(filename, '(202[34])-(.*)-([012])[.]jsonl$', 2) AS account,
   regexp_extract(filename, '(202[34])-(.*)-([012])[.]jsonl$', 3)::INTEGER AS cost_variant,
   greatest(3000000, max(nav) OVER (PARTITION BY filename ORDER BY date)) AS peak
 FROM read_json_auto('artifacts/incremental-alpha/epoch-001/batch-01/accounts/*.jsonl', filename=true)
), annual AS (
 SELECT account,year,cost_variant AS cost, arg_max(nav,date)/3000000-1 AS net,
   arg_max(nav,date)-3000000 AS profit_cny, sum(cost) AS fees_cny,
   min(nav/peak-1) AS drawdown
 FROM daily
 GROUP BY account,year,cost_variant
)
SELECT * FROM annual ORDER BY account,year,cost;
