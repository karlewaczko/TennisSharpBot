# Edge audit (2026-08-20T13:44:58+00:00)

## 1. Price attainability

A price column implying a negative overround on a large share of matches is a running maximum over the market's lifetime, not a quotable price. Backtesting against it invents money that was never available.

| price_column   |     n |   mean_overround |   negative_overround_rate | attainable   | verdict                                                           |
|:---------------|------:|-----------------:|--------------------------:|:-------------|:------------------------------------------------------------------|
| pinnacle       | 78351 |          0.02541 |                    0.0003 | True         | looks like a real quotable price                                  |
| bet365         | 82132 |          0.06212 |                    0      | True         | looks like a real quotable price                                  |
| market_avg     | 80642 |          0.05762 |                    0.0003 | True         | looks like a real quotable price                                  |
| market_max     | 80644 |         -0.00016 |                    0.4256 | False        | NOT ATTAINABLE -- running max over time, do not bet/backtest this |

## 2. Market calibration

Largest gap between de-vigged implied probability and realised win rate: **0.0076**.

| bucket     |     n |   market_implied |   actual_win_rate |   error |
|:-----------|------:|-----------------:|------------------:|--------:|
| (0.0, 0.1] |  4933 |           0.063  |            0.0555 | -0.0075 |
| (0.1, 0.2] | 11251 |           0.1545 |            0.1584 |  0.0039 |
| (0.2, 0.3] | 17694 |           0.2524 |            0.2521 | -0.0003 |
| (0.3, 0.4] | 22379 |           0.3514 |            0.3579 |  0.0065 |
| (0.4, 0.5] | 21793 |           0.4463 |            0.4518 |  0.0055 |
| (0.5, 0.6] | 22403 |           0.5522 |            0.5469 | -0.0053 |
| (0.6, 0.7] | 22374 |           0.6486 |            0.6421 | -0.0065 |
| (0.7, 0.8] | 17693 |           0.7476 |            0.7479 |  0.0003 |
| (0.8, 0.9] | 11251 |           0.8455 |            0.8416 | -0.0039 |
| (0.9, 1.0] |  4931 |           0.937  |            0.9446 |  0.0076 |

## 3. Incremental information over the market

The decisive test. If a model trained on [market price + our features] cannot beat one trained on [market price] alone, out of sample, then we hold no information the market lacks -- and no amount of tuning creates an edge.

|   season |    n |   market_log_loss |   ours_log_loss |   combined_log_loss | we_add_information   |
|---------:|-----:|------------------:|----------------:|--------------------:|:---------------------|
|     2013 | 4450 |          0.569976 |        0.597388 |            0.57297  | False                |
|     2014 | 4320 |          0.587328 |        0.611391 |            0.589754 | False                |
|     2015 | 4560 |          0.581376 |        0.60093  |            0.580904 | True                 |
|     2016 | 4491 |          0.590369 |        0.612931 |            0.591924 | False                |
|     2017 | 4503 |          0.608247 |        0.629983 |            0.608182 | False                |
|     2018 | 4455 |          0.602766 |        0.624451 |            0.603543 | False                |
|     2019 | 4438 |          0.605938 |        0.629289 |            0.607116 | False                |
|     2020 | 2036 |          0.589024 |        0.617983 |            0.588442 | True                 |
|     2021 | 4243 |          0.58832  |        0.614934 |            0.589043 | False                |
|     2022 | 4312 |          0.597221 |        0.622916 |            0.597722 | False                |
|     2023 | 4459 |          0.599292 |        0.631333 |            0.600069 | False                |
|     2024 | 4586 |          0.594918 |        0.61864  |            0.59438  | True                 |
|     2025 | 4271 |          0.605448 |        0.628375 |            0.605641 | False                |

```
seasons_tested: 13
matches_tested: 55124
market_log_loss: 0.59405
ours_log_loss: 0.61849
combined_log_loss: 0.59483
information_gain: -0.00078
market_lifts_our_model_by: 0.02365
verdict: NO information beyond the market: the market already prices in everything we know, so this model cannot systematically beat it
```

## 4. Strategy ROI, attainable prices only

### Betting `bet365` vs Pinnacle fair

| EV threshold | n bets | ROI | t-stat | verdict |
|---|---|---|---|---|
| >0.00 | 9143 | +1.93% | +1.27 | consistent with zero edge -- do not bet this |
| >0.02 | 3795 | +3.84% | +1.32 | consistent with zero edge -- do not bet this |
| >0.05 | 1336 | +9.26% | +1.39 | consistent with zero edge -- do not bet this |

### Betting `market_avg` vs Pinnacle fair

| EV threshold | n bets | ROI | t-stat | verdict |
|---|---|---|---|---|
| >0.00 | 2942 | +4.38% | +0.76 | consistent with zero edge -- do not bet this |
| >0.02 | 885 | +19.59% | +1.05 | consistent with zero edge -- do not bet this |
| >0.05 | 265 | +69.32% | +1.13 | consistent with zero edge -- do not bet this |
