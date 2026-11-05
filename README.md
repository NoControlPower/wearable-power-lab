# wearable-power-lab

**把"我们以为的功耗"变成"可复现的功耗账"。**

面向 10–30 mAh 级电池的可穿戴设备：给定各状态的实测电流与占空比，
算出每日电荷预算、预测续航，并回答"续航差多少、该砍哪一项"。

> 一个 21 mAh 的戒指要撑 5 天，整机平均电流必须 ≤ 175 µA。
> 而很多产品的待机规格就已经是 100–200 µA。
> 这类矛盾不是靠"再优化一下"解决的，是靠**先把账算清楚**再谈取舍。

---

## 这个仓库能回答什么

- 我的续航还差多少？（目标天数 → 允许的平均电流）
- 差的那部分电流，是哪几个状态贡献的？（按 mAh/天 排序）
- 砍掉/降档某一项，能换回几天？（敏感度分析）
- 为什么"把功能关掉"不省电？（共享采样档位问题）

## 方法：测量 → 切分 → 记账

```
PPK2 波形 ──┐
            ├─> 按固件状态切分 ─> 每状态平均电流 × 占空比 ─> mAh/天 ─> 续航 + 敏感度
固件日志 ───┘        (状态时间线)
```

1. **测量**：PPK2 抓电流波形。注意量程切换、平均 vs 峰值、内阻压降，详见
   [docs/methodology.md](docs/methodology.md)。
2. **切分**：用固件日志/GPIO 打点把波形对齐到状态（睡眠窗口、自动测量、BLE 连接……）。
3. **记账**：`mAh/天 = 电流(mA) × 秒/3600`。所有状态必须**互斥**，不要重复计数。

## 快速开始

```bash
python tools/power_budget.py examples/duty_table.example.json
```

输出示例：

```
battery 21.0 mAh  ->  2.4 days
battery 17.0 mAh  ->  1.9 days
battery 13.0 mAh  ->  1.5 days

top phases (mAh/day):
  sleep_window_ppg     5.60
  awake_connected      2.50
  awake_idle           0.60
  ...
```

敏感度分析（把某一项减半能多活多久）：

```bash
python tools/power_budget.py examples/duty_table.example.json --sensitivity
```

## 目录

```
tools/power_budget.py      占空比 → 每日电荷 → 续航 + 敏感度
examples/                  示例占空比表（illustrative，非实测）
docs/methodology.md        测量方法、误差来源、预算模型
docs/case-template.md      案例模板：每篇必须带数据、方法和局限
tests/                     预算模型的回归测试
```

## 路线图

- [x] 平均电流预算模型 + 敏感度分析
- [ ] PPK2 实时数据接入（可选依赖 [ppk2-api-python](https://github.com/IRNAS/ppk2-api-python)，GPL v2，仅作运行依赖、不并入本仓）
- [ ] 固件日志 → 状态时间线（RTT / 串口）
- [ ] 案例 01：马达单次振动与 50 mA 限值
- [ ] 案例 02：为什么"关掉呼吸率"不省电（PPG 共享档位）
- [ ] 案例 03：BLE 连接间隔的功耗代价
- [ ] 案例 04：1 Hz 连续体温采样的账

## 与现有工具的关系

- [ppk2-api-python](https://github.com/IRNAS/ppk2-api-python)：PPK2 的串口读取/多进程采样库（GPL v2）。
  本项目**不重复实现采样**，准备把它作为可选依赖接入；核心预算逻辑独立实现，保持 MIT。
- nRF Connect Power Profiler：官方 GUI，适合看波形，不适合做批量记录、对比和预算报表。
- 本项目的定位是**归因与预算层**：把波形切成状态、算每日电荷、给出取舍建议。

## 局限

- 这是**平均电流**模型，不含峰值电流、内阻压降、DC-DC 效率曲线；
- 电池容量是额定值，实际受温度、老化、放电倍率影响；
- 不能替代实测：它的价值是**在实测之前**告诉你哪里值得测。

## License

MIT
