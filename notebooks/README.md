# Notebooks — defense-grade walkthroughs

Bốn notebook, mỗi notebook một vai trò. **Đây là figure factory + Q&A reference cho buổi defense 31/05** — không phải exploratory. Mọi figure / số liệu trong slide sẽ trỏ về một notebook để defend khi thầy hỏi.

```
notebooks/
  _shared.py                  utilities (frozen-data loaders, color palette, figure savers)
  01_data.ipynb               Person 1     — VN30 dataset + news coverage + lookahead-safe alignment
  02_strategies.ipynb         Duc          — 8 agents architecture + sample decisions
  03_results.ipynb            Person 1     — comparison analysis, slide chapter 5
  04_invariants.ipynb         Person 2     — no-lookahead, reproducibility, VN rules sign-off
```

## Workflow (agent-driven)

1. **Đọc** TODO ở đầu mỗi cell. Format chuẩn:
   ```
   # TODO-NN: <kebab-id> — <one-line description>
   # OWNER: <name>          DEPENDS: <prior TODO ids or none>
   # READ: <files / columns>
   # WRITE: <figure path / variable / markdown>
   # CONSTRAINTS:
   #   - <hard rule 1>
   #   - <hard rule 2>
   # VALIDATE:
   #   - <assertion or expected output>
   # PATTERN: <file:line of similar code to mirror>
   # DEFENSE Q&A: "<câu thầy có thể hỏi>"
   ```
2. **Mở notebook trong VS Code + chạy Claude Code / Cursor**. Highlight cell → "Fill this TODO" → agent đọc context tự fill.
3. **Restart & Run All** sau mỗi nhóm TODO → kernel phải xanh đến cuối, output deterministic.
4. **Commit** notebook đã chạy với cell outputs đã render (cho người review đọc mà không cần re-run).

## Frozen snapshot policy (BẮT BUỘC)

Kể từ **2026-05-19** (sau PKG-S merge), các artifact sau là **canonical, không re-run**:

| File | Status | Lý do |
|---|---|---|
| `results/metrics_table.csv` | FROZEN | Slide chapter 5 trỏ về row của file này |
| `results/multi_agent/transcripts/*.json` (51 file) | FROZEN | Demo `/debate` UI dùng cached |
| `results/<agent>/portfolio_curve.parquet` | FROZEN | Notebooks chỉ read |
| `results/<agent>/holdings.parquet` | FROZEN | — |
| `results/<agent>/metrics.json` | FROZEN | — |

**Quy tắc**:
- **KHÔNG** chạy `python scripts/run_all.py` (kể cả với `--skip-existing`)
- **KHÔNG** chạy `python scripts/run_multi_agent.py`
- **KHÔNG** train lại DDPG/PPO
- Nếu phát hiện bug → 3 người align Slack/Zalo TRƯỚC, sửa, regen tất cả artifacts cùng lúc, update slide. Không silent re-run.

## Figure export contract

Mọi figure sinh ra phải lưu vào `report/figures/` với prefix là notebook id để Person 1 trỏ đúng:

```
report/figures/
  01__vn30_overview.png       ← notebook 01
  01__news_coverage_heatmap.png
  02__multi_agent_topology.png ← notebook 02
  03__cumret_bar.png          ← notebook 03 (slide chapter 5)
  03__sharpe_vs_return.png
  04__lookahead_proof.png     ← notebook 04
  ...
```

**Mọi figure**:
- `dpi=150` (slide-ready)
- `bbox_inches="tight"` (no whitespace)
- Title + axis labels tiếng Việt (defense bằng tiếng Việt)
- Color palette từ `notebooks/_shared.py:AGENT_COLORS` (consistent với landing UI)

## Single-source-of-truth rule

Mọi con số trong notebook + slide phải đọc từ artifact, **KHÔNG hardcode**:

| ❌ Don't | ✅ Do |
|---|---|
| `print("Multi-agent: +50.18%")` | `print(f"Multi-agent: {metrics.loc['multi_agent', 'cumulative_return']:.2%}")` |
| `sharpe = 2.19` | `sharpe = metrics.loc['multi_agent', 'sharpe']` |

Nếu thầy hỏi "+50.18% ra từ đâu?", mở notebook → run cell → ra số same. Drift = lost credibility.

## Defense Q&A sections

Cell cuối mỗi notebook **bắt buộc** có Q&A section:

```python
# %% Defense Q&A
# Q1: <câu thầy có thể hỏi>
#   A: <câu trả lời ngắn>
#   Evidence: <ô notebook trỏ về cell nào / file path>
# Q2: ...
```

3-5 câu cho mỗi notebook. Khi defense, mở notebook → tìm Q tương ứng → có evidence sẵn.

## Owner contract

| Person | Notebook | Effort | Hạn |
|---|---|---|---|
| **Duc** | 02_strategies | 2 day | 22/05 |
| **Person 1** | 01_data + 03_results | 2.5 day | 25/05 |
| **Person 2** | 04_invariants | 1 day | 23/05 |

Sau 25/05: cả 4 notebook lock + Person 1 dùng các figure đã export để build slide.

## Validation trước khi commit

Cuối mỗi notebook chạy:
```bash
# trong notebooks/ dir
jupyter nbconvert --to notebook --execute 01_data.ipynb --output 01_data.executed.ipynb
diff 01_data.ipynb 01_data.executed.ipynb  # outputs identical → safe to commit
```

Hoặc trong notebook UI: Kernel → Restart & Run All → save → commit.

## Vấn đề thường gặp

- **`metrics_table.csv` thiếu cột `n_decisions` cho buy_and_hold**: đúng, các baseline không có decision count. Filter `dropna()` khi cần.
- **Multi-agent `cumulative_return` lệch giữa `metrics.json` và `metrics_table.csv`**: 2nd là canonical (rebuilt từ parquet sau backtest).
- **Figure font không phải Inter trên slide**: mặc định matplotlib dùng DejaVu Sans. Để match landing UI, set `plt.rcParams["font.family"] = "Inter"` ở đầu notebook (nếu Inter installed system-wide; fallback `sans-serif` cũng OK).
