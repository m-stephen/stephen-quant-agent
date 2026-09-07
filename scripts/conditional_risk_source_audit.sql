-- Independent daily-only state and gross forecast-basket reconstruction.
CREATE TABLE risk_eligible AS
WITH a AS (
 SELECT *,close*adjustment_factor AS cp,
 close*adjustment_factor/nullif(lag(close*adjustment_factor,20) OVER w,0)-1 AS ret20,
 ln(CASE WHEN close*adjustment_factor>0 AND lag(close*adjustment_factor) OVER w>0
 THEN close*adjustment_factor/lag(close*adjustment_factor) OVER w END) AS lr,
 avg(amount*1000) OVER w60 AS adv,count(amount) OVER w60 AS history
 FROM daily_source WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
 w60 AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
), b AS (
 SELECT *,stddev_samp(lr) OVER(PARTITION BY instrument ORDER BY trade_date
 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vol20 FROM a
)
SELECT c.idx,b.trade_date AS date,b.instrument,b.cp,b.ret20,b.vol20,b.adv
FROM b JOIN calendar c ON c.date=b.trade_date
WHERE b.open>0 AND b.close>0 AND b.adjustment_factor>0
 AND isfinite(b.open) AND isfinite(b.close) AND isfinite(b.adjustment_factor)
 AND b.adv>=10000000 AND b.history>=20 AND b.name IS NOT NULL AND b.name!=''
 AND NOT contains(upper(b.name),'ST')
 AND b.available_at<=(b.trade_date::TIMESTAMP AT TIME ZONE 'Asia/Shanghai')+INTERVAL 1 DAY-INTERVAL 1 SECOND
 AND isfinite(b.ret20) AND isfinite(b.vol20) AND isfinite(b.adv);

CREATE TABLE state_names AS
SELECT a.*,a.cp/p.cp-1 AS return1,
 row_number() OVER(PARTITION BY a.date ORDER BY a.vol20,a.instrument) AS rn
FROM risk_eligible a JOIN risk_eligible p ON p.instrument=a.instrument AND p.idx=a.idx-1;

CREATE TABLE state_values AS
SELECT c.idx,c.date,count(n.instrument) AS eligible,
 avg((n.ret20>0)::INTEGER) AS breadth20,avg(n.ret20) AS mean_return20,
 avg(n.vol20) AS mean_volatility20,stddev_pop(n.return1) AS dispersion1
FROM calendar c LEFT JOIN state_names n USING(idx,date) GROUP BY ALL;

CREATE TABLE valid_bars AS
SELECT trade_date AS date,instrument,open*adjustment_factor AS op,close*adjustment_factor AS cp
FROM daily_source WHERE open>0 AND close>0 AND adjustment_factor>0
AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor);

CREATE TABLE proxy_components AS
WITH components AS (
 SELECT n.date AS signal_date,n.instrument,e.date AS entry_date,f.date AS label_end,
 b.op AS entry_price,CASE WHEN b.op IS NULL THEN NULL ELSE coalesce(z.op,stale.cp,b.op) END AS end_mark,
 CASE WHEN b.op IS NULL THEN NULL WHEN z.op IS NOT NULL THEN f.date ELSE coalesce(stale.date,e.date) END AS mark_date
 FROM state_names n JOIN state_values s USING(idx,date)
 JOIN calendar e ON e.idx=n.idx+1 JOIN calendar f ON f.idx=n.idx+6
 LEFT JOIN valid_bars b ON b.date=e.date AND b.instrument=n.instrument
 LEFT JOIN valid_bars z ON z.date=f.date AND z.instrument=n.instrument
 LEFT JOIN LATERAL (SELECT cp,date FROM valid_bars v WHERE v.instrument=n.instrument
   AND v.date>=e.date AND v.date<f.date ORDER BY date DESC LIMIT 1) stale ON true
 WHERE n.idx%5=0 AND n.rn<=200 AND s.eligible>=200 AND f.date<DATE '2024-01-01'
)
SELECT *,CASE WHEN entry_price IS NULL THEN 0.0 ELSE end_mark/entry_price-1 END AS return
FROM components;

CREATE TABLE label_values AS
SELECT signal_date,entry_date,label_end,sum(return)/200 AS return,
 count(entry_price) AS entries,count(*) FILTER(WHERE entry_price IS NOT NULL AND mark_date=label_end) AS fresh
FROM proxy_components GROUP BY ALL;
