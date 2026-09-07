-- Independent reconstruction; calendar contains only frozen 2022-2024 sessions.
CREATE TABLE eligible AS
WITH a AS (
 SELECT *,close*adjustment_factor AS ac,
 close*adjustment_factor/nullif(lag(close*adjustment_factor,20) OVER w,0)-1 AS ret_20,
 ln(CASE WHEN close*adjustment_factor>0 AND lag(close*adjustment_factor) OVER w>0
 THEN close*adjustment_factor/lag(close*adjustment_factor) OVER w END) AS lr,
 avg(amount*1000) OVER w60 AS liquidity,count(amount) OVER w60 AS history
 FROM daily_source WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
 w60 AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
), b AS (
 SELECT *,stddev_samp(lr) OVER(PARTITION BY instrument ORDER BY trade_date
 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS volatility_20 FROM a
)
SELECT c.idx,b.trade_date AS date,b.instrument,b.ac,b.ret_20,b.volatility_20,b.liquidity,
 CASE WHEN f.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 AND isfinite(f.net_inflow_amount/nullif(b.amount*1000,0))
 THEN f.net_inflow_amount/nullif(b.amount*1000,0) END AS flow1
FROM b JOIN calendar c ON c.date=b.trade_date
LEFT JOIN flow_source f ON f.instrument=b.instrument AND f.trade_date=b.trade_date
WHERE b.open>0 AND b.close>0 AND b.adjustment_factor>0
 AND isfinite(b.open) AND isfinite(b.close) AND isfinite(b.adjustment_factor)
 AND b.liquidity>=10000000 AND b.history>=20 AND b.name IS NOT NULL AND b.name!=''
 AND NOT contains(upper(b.name),'ST')
 AND b.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 AND isfinite(b.ret_20) AND isfinite(b.volatility_20) AND isfinite(b.liquidity);

CREATE TABLE reconstructed AS
WITH adjacent AS (
 SELECT a.*,a.ac/p.ac-1 AS return1 FROM eligible a JOIN eligible p
 ON p.instrument=a.instrument AND p.idx=a.idx-1
), windows AS (
 SELECT *,count(*) OVER w n,count(flow1) OVER w fn,min(idx) OVER w first_idx,
 product(1+return1) OVER w-1 AS price5,avg(flow1) OVER w flow5
 FROM adjacent WINDOW w AS(PARTITION BY instrument ORDER BY idx ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
)
SELECT *,CASE WHEN n=5 AND fn=5 AND first_idx=idx-4 THEN price5 END AS price,
 CASE WHEN n=5 AND fn=5 AND first_idx=idx-4 THEN flow5 END AS flow FROM windows;

CREATE TABLE demeaned AS
SELECT *,return1-avg(return1) OVER(PARTITION BY date) AS residual FROM reconstructed;
