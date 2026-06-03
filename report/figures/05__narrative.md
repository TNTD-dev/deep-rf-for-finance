# Kết quả thực nghiệm — Tóm tắt

## Big Picture: Top 3 xếp hạng

Trong 248 phiên test (2025-05 → 2026-04) trên VN30, chiến lược **buy_and_hold đạt +103.2% (Sharpe 2.75)**, vượt trội toàn bộ active agents. Equal_weight về nhì với +53.1%. Multi_agent xếp thứ 3 với +50.2% (Sharpe 2.19).

Kết quả này phản ánh **giai đoạn bull market mạnh** (VN30 +103.2%) — trong điều kiện đó, passive index rất khó bị đánh bại bởi bất kỳ active strategy nào.

## RL Bracket: PPO vs DDPG

PPO đạt +40.3% (Sharpe 1.26), gấp nhiều lần so với DDPG chỉ +1.1% (Sharpe 0.05). Nguyên nhân: DDPG bị "saturated tanh" — action bão hoà overweight HPG, portfolio gần như không rebalance. PPO với clipped objective + entropy bonus giữ được portfolio đa dạng.

## LLM Bracket: multi_agent > single > zero_shot

Multi_agent với kiến trúc 8-node LangGraph đạt +50.2% — cao nhất trong nhóm LLM. Zero_shot và single_agentic chỉ chạy smoke run (N=10 sessions) nên Sharpe overfit; kết quả không representative cho full backtest.

## Surprises & Insights

1. **Buy_and_hold thắng tuyệt đối**: không phải lỗi model mà là đặc thù bull market. Thesis vẫn có giá trị: so sánh RL vs LLM trong cùng điều kiện.
2. **Multi_agent Sharpe 2.19 ≈ buy_and_hold Sharpe 2.75**: risk-adjusted, LLM agent có cùng chất lượng với passive index.
3. **Max DD multi_agent +16.4% < random +26.7%**: LLM debate giúp kiểm soát rủi ro tốt hơn random allocation đáng kể.