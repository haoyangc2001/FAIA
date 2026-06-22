# FAIA: Fulfillment-oriented Assortment and Inventory Allocation

面向履约效率的前置仓选品与库存分配项目

## 项目简介

本项目研究即时零售配送网络中的履约效率优化问题。在 RDC-FDC 两级仓储网络中，前置仓（FDC）离用户近、配送快，但容量有限；区域仓（RDC）容量大、SKU 全，但离用户较远。核心问题是：**哪些商品应该放入 FDC，以及每天给 FDC 分配多少库存？**

## 业务场景

项目基于小象超市即时零售配送场景，将业务抽象为城市级 RDC + 多个社区 FDC 的两级履约网络：

- **RDC（城市区域配送中心）**：城市级上游大仓，负责集中存储商品、向各 FDC 补货，并在 FDC 缺货时承担兜底履约
- **FDC（社区前置仓）**：靠近消费者，负责服务周边区域的即时订单，但受仓容限制，无法存放全部 SKU

用户下单后，系统优先从 FDC 履约；FDC 缺货时由 RDC 兜底；RDC 也缺货时产生缺货损失。

## 解决方案

采用两阶段方法：

1. **前置仓选品（Assortment Planning）**：决定 FDC 应该存放哪些 SKU
   - ML-Top-K：用机器学习预测 SKU 未来订单频率
   - Reverse-Exclude：从全集开始，逐步删除对订单覆盖影响最小的 SKU
   - Hybrid Selection：融合前两种方法

2. **库存分配（Inventory Allocation）**：决定 RDC 每天给 FDC 调拨多少库存
   - 端到端学习框架：将需求预测、TI/SS 生成和仿真运营损失连接起来

## 参考论文

- [Reference_Paper.md](doc/Reference_Paper.md)
- [Reference_Paper.pdf](doc/Reference_Paper.pdf)

论文标题：*JD.com Improves Fulfillment Efficiency with Data-driven Integrated Assortment Planning and Inventory Allocation*

## 项目文档

详细文档见飞书：[FAIA 项目文档](https://fcnc0sqju1nj.feishu.cn/docx/NOwHdNwV4oJtkpxR2EFcxFbYnUd)

## 目录结构

```
meituan/
├── README.md              # 本文件
├── doc/
│   ├── Reference_Paper.md   # 参考论文（Markdown）
│   └── Reference_Paper.pdf  # 参考论文（PDF）
└── ...
```
