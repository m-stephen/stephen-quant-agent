-- Independent raw-source support and rolling-normalization reconstruction.
-- daily_source, flow_source, evidence and calendar are bounded caller views.
CREATE TABLE raw_features AS
WITH a AS (
 SELECT *, close*adjustment_factor AS ac,
 close*adjustment_factor/nullif(lag(close*adjustment_factor,20) OVER w,0)-1 AS ret_20,
 ln(CASE WHEN close*adjustment_factor>0 AND lag(close*adjustment_factor) OVER w>0
    THEN close*adjustment_factor/lag(close*adjustment_factor) OVER w END) AS lr,
 avg(amount*1000) OVER w60 AS liquidity,count(amount) OVER w60 AS history
 FROM daily_source
 WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
 w60 AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
), b AS (
 SELECT *,stddev_samp(lr) OVER(PARTITION BY instrument ORDER BY trade_date
 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS volatility_20 FROM a
), valid_prices AS (
 SELECT trade_date,instrument,ac FROM b
 WHERE open>0 AND close>0 AND adjustment_factor>0
 AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor)
)
SELECT c.idx AS index,b.trade_date AS date,b.instrument,b.ac AS close,
 p.ac AS previous_close,b.ac/p.ac-1 AS price_return,
 f.net_inflow_amount/nullif(b.amount*1000,0) AS flow,b.ret_20,b.volatility_20,b.liquidity
FROM b JOIN calendar c ON c.date=b.trade_date
JOIN valid_prices v ON v.instrument=b.instrument AND v.trade_date=b.trade_date
JOIN calendar pc ON pc.idx=c.idx-1
JOIN valid_prices p ON p.instrument=b.instrument AND p.trade_date=pc.date
JOIN flow_source f ON f.instrument=b.instrument AND f.trade_date=b.trade_date
WHERE b.trade_date>=DATE '2022-01-01' AND b.trade_date<DATE '2025-01-01'
 AND b.liquidity>=10000000 AND b.history>=20 AND b.name IS NOT NULL AND b.name!=''
 AND NOT contains(upper(b.name),'ST')
 AND b.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 AND f.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 AND isfinite(b.ret_20) AND isfinite(b.volatility_20) AND isfinite(b.liquidity)
 AND isfinite(f.net_inflow_amount/nullif(b.amount*1000,0)) AND isfinite(b.ac/p.ac-1);

CREATE TABLE reconstructed AS
WITH a AS (
 SELECT *,count(*) OVER w AS n,min(index) OVER w AS first_i,max(index) OVER w AS last_i,
 avg(flow) OVER w AS mf,stddev_samp(flow) OVER w AS sf,stddev_samp(price_return) OVER w AS sr
 FROM raw_features WINDOW w AS(PARTITION BY instrument ORDER BY index ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)
)
SELECT *,CASE WHEN n=20 AND first_i=index-20 AND last_i=index-1 AND sf>0 AND sr>0
 THEN (flow-mf)/sf END AS flow_z,
 CASE WHEN n=20 AND first_i=index-20 AND last_i=index-1 AND sf>0 AND sr>0
 THEN price_return/sr END AS price_z FROM a;

CREATE TABLE support AS
WITH a AS (
 SELECT *,row_number() OVER(PARTITION BY date ORDER BY volatility_20,instrument)-1 AS vi,
 count(*) OVER(PARTITION BY date) AS ns FROM reconstructed
 WHERE flow_z IS NOT NULL AND price_z IS NOT NULL AND isfinite(flow_z) AND isfinite(price_z)
), b AS (SELECT *,floor(3.0*vi/ns)::INTEGER AS gi FROM a),
c AS (SELECT *,row_number() OVER(PARTITION BY date,gi ORDER BY volatility_20,instrument)-1 AS j,
 count(*) OVER(PARTITION BY date,gi) AS gn FROM b),
d AS (SELECT *,CASE WHEN j<ceil(gn/2.0) THEN 0 ELSE 1 END AS vh FROM c),
f AS (SELECT *,row_number() OVER(PARTITION BY date,gi,vh ORDER BY liquidity,instrument)-1 AS ai,
 count(*) OVER(PARTITION BY date,gi,vh) AS hn FROM d)
SELECT index,date,instrument,flow,flow_z,price_z,
 gi||':'||vh||':'||floor(2.0*ai/hn)::INTEGER AS cell FROM f;
