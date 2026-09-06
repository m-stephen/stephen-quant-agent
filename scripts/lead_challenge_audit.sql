WITH evidence AS (
 SELECT *, regexp_extract(filename, '([^/\\]+)[.]jsonl$', 1) AS account_key,
   greatest(3000000, max(nav) OVER (PARTITION BY filename ORDER BY date)) AS peak
 FROM read_json_auto('__ACCOUNT_GLOB__', filename=true)
)
SELECT account_key, count(*) AS sessions,
       arg_max(nav,date) AS final_nav, arg_max(nav,date)/3000000-1 AS net_return,
       arg_max(nav,date)-3000000 AS profit_cny, sum(cost) AS cost_cny,
       min(nav/peak-1) AS max_drawdown
FROM evidence GROUP BY account_key ORDER BY account_key;
