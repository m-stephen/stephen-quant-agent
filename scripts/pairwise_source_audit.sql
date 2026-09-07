-- Independent raw fields; no future target, survivorship subset or fitted transform.
CREATE TABLE eligible AS WITH a AS (
 SELECT *,close*adjustment_factor/nullif(lag(close*adjustment_factor,20) OVER w,0)-1 ret20,
 ln(CASE WHEN close*adjustment_factor>0 AND lag(close*adjustment_factor) OVER w>0
 THEN close*adjustment_factor/lag(close*adjustment_factor) OVER w END) lr,
 avg(amount*1000) OVER w60 adv,count(amount) OVER w60 history
 FROM daily_source WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
 w60 AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
), b AS (
 SELECT *,stddev_samp(lr) OVER(PARTITION BY instrument ORDER BY trade_date
 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) vol20 FROM a
)
SELECT z.idx,b.trade_date AS date,b.instrument,b.vol20,b.ret20,b.adv,
 CASE WHEN f.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 THEN f.net_inflow_amount/nullif(b.amount*1000,0) END flow,
 CASE WHEN a.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 THEN a.auction_return END auction,
 CASE WHEN c.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 THEN (c.chip_cost_85-c.chip_cost_15)/nullif(c.chip_weighted_cost,0) END width
FROM b JOIN calendar z ON b.trade_date=z.date
LEFT JOIN fund_flow_source f USING(trade_date,instrument)
LEFT JOIN auction_source a USING(trade_date,instrument)
LEFT JOIN chip_source c USING(trade_date,instrument)
WHERE b.adv>=10000000 AND b.history>=20 AND b.name IS NOT NULL AND b.name!=''
 AND NOT contains(upper(b.name),'ST')
 AND b.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND;

CREATE TABLE valid_bars AS SELECT trade_date AS date,instrument,
 open*adjustment_factor AS op,close*adjustment_factor AS cp FROM daily_source
WHERE open>0 AND close>0 AND adjustment_factor>0
 AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor);
