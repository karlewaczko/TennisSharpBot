# Edge audit (2026-07-26T22:01:01+00:00)

## 1. Price attainability

A price column implying a negative overround on a large share of matches is a running maximum over the market's lifetime, not a quotable price. Backtesting against it invents money that was never available.

| price_column   |     n |   mean_overround |   negative_overround_rate | attainable   | verdict                                                           |
|:---------------|------:|-----------------:|--------------------------:|:-------------|:------------------------------------------------------------------|
| pinnacle       | 78351 |          0.02541 |                    0.0003 | True         | looks like a real quotable price                                  |
| bet365         | 81711 |          0.06218 |                    0      | True         | looks like a real quotable price                                  |
| market_avg     | 80220 |          0.05759 |                    0.0003 | True         | looks like a real quotable price                                  |
| market_max     | 80222 |         -0.00029 |                    0.4275 | False        | NOT ATTAINABLE -- running max over time, do not bet/backtest this |

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
|     2013 | 4450 |          0.569976 |        0.596518 |            0.571993 | False                |
|     2014 | 4320 |          0.587328 |        0.611573 |            0.592726 | False                |
|     2015 | 4560 |          0.581376 |        0.602451 |            0.582489 | False                |
|     2016 | 4491 |          0.590369 |        0.612687 |            0.590675 | False                |
|     2017 | 4503 |          0.608247 |        0.62782  |            0.608121 | True                 |
|     2018 | 4455 |          0.602766 |        0.626343 |            0.603282 | False                |
|     2019 | 4438 |          0.605942 |        0.627979 |            0.60625  | False                |
|     2020 | 2036 |          0.589064 |        0.616848 |            0.589343 | False                |
|     2021 | 4243 |          0.58832  |        0.615018 |            0.590008 | False                |
|     2022 | 4312 |          0.597221 |        0.621937 |            0.597885 | False                |
|     2023 | 4459 |          0.599292 |        0.632783 |            0.599936 | False                |
|     2024 | 4586 |          0.594918 |        0.618198 |            0.59315  | True                 |
|     2025 | 4271 |          0.605448 |        0.628925 |            0.605784 | False                |

```
seasons_tested: 13
matches_tested: 55124
market_log_loss: 0.59406
ours_log_loss: 0.61842
combined_log_loss: 0.59494
information_gain: -0.00088
market_lifts_our_model_by: 0.02348
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
