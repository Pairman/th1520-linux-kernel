# TH1520 6.6.162 合并复审及修复

审查日期：2026-11-13。基线 `4a0d16a522953d43a0ede266137a454242ba5872`。
修复位于独立 worktree `lpi4a-audit-fixes`、分支 `th1520-audit-fixes`。
原 `lpi4a-linux` 保持 detached `879210d1938a`，没有替换现用内核或启动项。

## 最终问题与选择

| 问题 | 本机触发条件 / 证据 | 最终方案 |
| --- | --- | --- |
| 单向 UART DMA 错误清理解引用 NULL；TX capability 失败泄漏已分配的 RX buffer | 厂商允许缺 RX 或缺 TX，但清理仍假定 RX 存在；本机启用 UART 无 `dmas`，console 禁止 DMA，当前配置下未发现实际触发入口 | 保留厂商单向 DMA，按资源所有权清理 buffer/channel 并清指针，保留上游 rx_running/flush 修复 |
| RX-only 时 TX IRQ 没走 PIO；缺方向时清除回调导致重开后回调丢失 | 保留 dma 对象但 txchan 为 NULL、tx_err 为 0 时错误停发；回调只在 set_defaults 初始化 | TX IRQ 检查 txchan；不因暂时缺通道清除 DMA 回调 |
| TH1520 GPIO 扩展器早期恢复时 DMA 尚未恢复 | 本机 `0-0018`、`1-0018`、`3-0018` 绑定 pca953x；厂商 `0fec15fd1dc3` 将 PCA9557 恢复提前到 resume_early 以先于 LCD；其 regcache_sync 需要 I2C DMA；合并后的 DMA normal force_resume 太晚；实机 sysfs 未见 I2C→DMA link | 保留厂商 late/early 阶段及 GPIO/LCD 顺序，使用上游 force PM 管理；新增 I2C→TX DMA supplier managed link，使 early 恢复顺序为 DMA→I2C→PCA9557。非 TH1520 DMA 仍用上游 normal 阶段 |
| AXI DMA core clock 启用失败时 cfgr clock 引用泄漏 | 厂商及上游均存在，只有第二个时钟启用失败时触发；正常工作快照不证明会发生 | 失败时撤销先前启用的 cfgr clock |
| 已有 Image 但无完整模块产物 | 原 build-162 有 Image/vmlinux；没有找到对应 `.ko`，I2C、网卡等配置为模块 | 现有目录不作为安装包；本次仅编译受影响对象，不声明完成可部署内核 |

此前“DMA normal force PM 可直接保留、本板无 early I2C 依赖”的暂定意见已撤回。
PCA9557 的实际绑定和厂商 late/early 补丁是必须组合两边实现的依据。
这是静态确认的阶段不匹配，不是已经执行系统休眠后的故障复现。

## 无需再次修改的合并

- 151/157/162 正式合并均以对应上游 stable 提交为第二父节点。
- OP-TEE 保留上游请求生命周期及 INVALID_REQ_PTR 防护，同时保留解锁后冻结；本机 TEE 关闭。
- RCU 保留上游 READ_ONCE/WRITE_ONCE；stop_machine 保留中断关闭后的 RCU 调用。
- AXI DMA 保留硬件访问前 resume_and_get、失败路径 put、厂商同步 free put；不能恢复旧的第二次 get。
- 初始 TH1520 到 162 的 thead 设备树没有被替换；MMC/ext4/initrd/pinctrl/errata 等启动配置保持启用。

## 实施范围和复审

三名独立 agent 分别复审 UART、DMA/PM、合并/启动路径。PM 初审遗漏
PCA9557 late 回调后，经进一步核查更正；最终实际 diff 再次独立复审通过。
I2C helper 使用真实 `dma-names` 的 `tx` 索引解析 phandle 参数，不假定首项；
供应者未创建或未绑定时 defer，引用/锁配对释放，链接由 core 自动管理。
不添加 RPM link flag，通道引用仍控制 DMA runtime PM。

## 已执行验证

1. 标准 Kbuild `olddefconfig`：沿用原 build-162 配置，输出 `No change to .config`。
2. 标准 Kbuild 编译四个对象通过：8250_dma、8250_port、dw-axi-dmac-platform、i2c-designware-platdrv（模块对象）。输出目录 `../lpi4a-audit-kbuild`。
3. `test_uart_dma_c.py` 从真实 request/release 函数提取 C 代码运行 mock：144 种通道、capability 失败/不支持、RX 分配、TX 映射组合；成功及失败路径检查 buffer、映射和 channel 释放。固定原提交捕获 NULL 清理错误，修复版本通过。
4. `test_uart_port_c.py` 提取真实 TX IRQ/startup 代码块，检查 PIO/DMA 分发、console/失败回退及回调保留。
5. `test_dma_pm_c.py` 提取真实 PM/clock/link 函数，检查 TH1520/通用阶段分流、force 调用次数及错误传播、时钟回滚、TX 索引非零、供应者缺失/未绑定及资源/锁平衡。
6. `git diff --check` 通过。补丁未改配置或设备树。

重跑用户态测试：

```sh
python3 validation/test_uart_dma_c.py
python3 validation/test_uart_port_c.py
python3 validation/test_dma_pm_c.py
```

本机对象编译复现命令见 `validation/build_objects.sh`。
依赖解包于 `../lpi4a-audit-validation/deps`，未安装系统软件包；libelf/bc
使用现有 `/tmp/lpi4a-package-deps/root`。构建日志在 `../lpi4a-audit-validation/`。
该脚本依赖本次已准备的配置和工具目录，不是通用构建安装脚本。

## 仍需的部署前验证

本次没有构建最终修改后的完整 Image、全部模块和发行版包，没有生成新 initramfs，
没有安装、重启、强制休眠、访问 I2C 外设地址或更改运行设备树。
用户态 mocks 不模拟 PM core 并发、真实时钟域、DMA IRQ 或硬件寄存器丢失。

部署前必须用同一提交/配置构建 Image、dtbs、modules，使用匹配的新模块和
initramfs，保留旧启动项与串口恢复方式。板上验证冷启动、根盘、网络、GPIO、
I2C/音频 runtime PM；系统休眠恢复重点检查 PCA9557 regcache 恢复及
DMA→I2C→PCA9557 的 trace 顺序。UART DMA 测试需专门的非控制台配置，
当前设备树不覆盖这一硬件路径。
