# PolyMETL

ETL for Polymarket — both **on-chain trade events** (Polygon RPC) and
**off-chain market metadata** (Gamma API), unified in ClickHouse.

> 📚 **Thesis project** — see [`docs/REPRODUCE.md`](docs/REPRODUCE.md)
> for a complete reproduction guide and
> [`docs/EXPERIMENT_LOG.md`](docs/EXPERIMENT_LOG.md) for the dataset
> snapshot used in the thesis. Analysis SQL lives under
> [`scripts/sql/`](scripts/sql/) and is catalogued in
> [`docs/ANALYSES.md`](docs/ANALYSES.md).

## 模块概览

| 模块 | 数据源 | 输出表 |
|---|---|---|
| `src/etl.py` (`python -m src`) | Polygon RPC (链上事件) | `order_filled`, `orders_matched`, `etl_progress` |
| `src/gamma.py` (`python -m src.gamma`) | Polymarket Gamma API (链下元数据) | `markets` |

链下 `markets.clob_token_ids` 与链上 `order_filled.maker_asset_id` /
`taker_asset_id` 是 ERC1155 outcome token id,可直接 JOIN。

## 原理

0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e 部署于 33605403

通过polygon的RPC节点，查找所有匹配的 OrderFilled、OrdersMatched

OrderFilled (index_topic_1 bytes32 orderHash, index_topic_2 address maker, index_topic_3 address taker, uint256 makerAssetId, uint256 takerAssetId, uint256 makerAmountFilled, uint256 takerAmountFilled, uint256 fee)
hash: 0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6


OrdersMatched (index_topic_1 bytes32 takerOrderHash, index_topic_2 address takerOrderMaker, uint256 makerAssetId, uint256 takerAssetId, uint256 makerAmountFilled, uint256 takerAmountFilled)

hash: 0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c

## 使用说明

- 解析 OrdersMatched、OrderFilled，并写入 ClickHouse。
- 具备断点续跑能力：每个区间处理完成后更新 `etl_progress`，中断后会从上次 `last_block + 1` 继续。

### 1) 准备环境

推荐使用 uv（更快的 Python 包与运行管理器）。如未安装：`curl -LsSf https://astral.sh/uv/install.sh | sh`。

1. 安装依赖（uv）

```bash
uv sync
```

2. 配置环境变量

复制 `.env.example` 为 `.env`，并设置 Polygon RPC 与 ClickHouse 连接信息：

```bash
cp .env.example .env
```

必要项：
- POLYMETL_RPC_URL

可选项：
- POLYMETL_EXCHANGE_ADDRESS 仅抓取某个合约（推荐）
- POLYMETL_START_BLOCK / POLYMETL_END_BLOCK 限定范围
- POLYMETL_LOG_BATCH_SIZE / POLYMETL_INSERT_BATCH_SIZE 调整批大小

3. ClickHouse

确保 ClickHouse 可用（默认 localhost:9000）。脚本会自动创建数据库与表：
- order_filled
- orders_matched
- etl_progress （保存链、合约与 last_block）

### 2) 运行

运行 ETL（uv）：

```bash
uv run -m src --address 0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e --start 33605403 --end 33700000
```

不指定 start/end 时，将从进度表继续；若无进度，将从最新区块往前 10000 个开始。

建议：
- 指定 `--address`（或设置 `POLYMETL_EXCHANGE_ADDRESS`）以仅抓取目标合约事件。
- `--start` 设置为合约部署高度（例如 33605403），避免长时间扫描无事件的历史区块。

### 3) 数据表结构（ClickHouse）

- order_filled(chain_id, block_number, block_time, tx_hash, log_index, contract_address, order_hash, maker, taker, maker_asset_id, taker_asset_id, maker_amount_filled, taker_amount_filled, fee)
- orders_matched(chain_id, block_number, block_time, tx_hash, log_index, contract_address, taker_order_hash, taker_order_maker, maker_asset_id, taker_asset_id, maker_amount_filled, taker_amount_filled)
- etl_progress(chain_id, exchange_address, last_block, updated_at)

### 4) 断点续跑原理

每处理完一个区块区间 [from, to]，即写入进度 (chain_id, exchange_address, to_block, updated_at)。
下次启动时按以下优先级确定起点：CLI --start > 环境变量 START_BLOCK > 进度表 last_block+1 > latest-10000。

## Gamma puller (off-chain metadata)

`src/gamma.py` 从 `gamma-api.polymarket.com/markets` 抓市场元数据
(slug、问题文本、outcomes、clobTokenIds、当前赔率、累计成交量、结算时
间等)写入 ClickHouse `markets` 表。

```bash
# 当前活跃市场 (~45k)
uv run python -m src.gamma --closed false

# 历史已结算市场 (~100k,Gamma offset 上限 ~100k 后会优雅退出)
uv run python -m src.gamma --closed true
```

`markets` 表字段:`market_id, slug, question, description, category,
outcomes, clob_token_ids, outcome_prices, volume, end_date, active,
closed, fetched_at`。引擎为 `ReplacingMergeTree(fetched_at)
ORDER BY market_id`,查询时建议加 `FINAL` 去重。

完整字段调研:`uv run python scripts/inspect_market_fields.py`。

## Tests

```bash
uv run python -m unittest tests.test_gamma -v
```
