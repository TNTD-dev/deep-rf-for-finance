# Paper - DDPG Stock Trading

## Source

[[Deep Reinforcement Learning Approach for Stock Trading_.pdf]]

## Role in project

Paper gốc làm xương sống cho demo stock trading bằng DDPG.

## Connects to

- [[DRL Finance - Graph Map]]
- [[Foundation -Deep Reinforcement Learning for Finance]]
- [[Deep Understanding - Deep Reinforcement Learning for Finance]]
- [[Pipeline]]
- [[TASK]]
- [[Task_v2]]
- [[Paper - Ensemble Stock Trading]]

## Key ideas

- Stock trading được mô hình hóa thành MDP.
- State gồm cash, holdings, prices, technical indicators.
- Action thường là mua/bán/giữ hoặc tỷ trọng/liều lượng giao dịch.
- Reward thường dựa trên portfolio value sau transaction cost.
- DDPG phù hợp khi action space liên tục.

## Use in report

- Problem formulation.
- Method: DDPG.
- Environment design.
- Experiment baseline.
- Limitation: overfitting, transaction cost, regime shift.
