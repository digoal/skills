# Bug 模式目录（历史类别、关键词表、内置扫描模式）

本文件供 `find-postgres-bug` skill 的阶段2、阶段3使用，是判断"这算不算一个值得深挖的模式"的参考基准。

## 六大历史 bug 类别

| 类别 | 判断标准 | 典型历史案例特征 |
|------|----------|------------------|
| 内存管理 | `palloc`/`pfree` 不匹配、use-after-free、double free、跨内存上下文引用 | 函数返回指向已被 pfree 或已切换上下文释放的内存的指针 |
| 并发/锁 | 死锁、加锁顺序不一致、忘记加锁、元组可见性判断错误 | 两处代码以不同顺序获取同一组锁，在高并发下出现死锁 |
| 边界/溢出 | 整数溢出、缓冲区过小、XID 回卷、off-by-one | 用户可控的长度字段参与乘法计算后直接用于 palloc 大小 |
| 逻辑错误 | SQL 标准实现偏差、类型转换错误、优化器生成错误计划 | 特定 JOIN 顺序下的谓词下推破坏了语义等价性 |
| 资源泄漏 | 文件描述符/内存上下文/锁未释放 | 提前 return 路径中缺少和正常路径一致的清理逻辑 |
| 类型转换 | 隐式类型转换导致精度丢失或语义变化 | 大整数转 int4 时静默截断而非报错 |

## 关键词表（用于阶段2历史挖掘的 grep 正则）

| 类别 | 正则片段 |
|------|----------|
| 内存管理 | `pfree|palloc|use-after-free|double.?free|memory leak|dangling` |
| 并发锁 | `deadlock|race condition|lock (order|held)|concurren|lwlock|spinlock` |
| 边界溢出 | `overflow|out.of.bound|buffer.*(small|overrun)|xid wraparound|off.by.one` |
| 逻辑错误 | `incorrect result|wrong (result|answer)|planner.*(bug|error)|semantics` |
| 资源泄漏 | `leak|not (closed|released|freed)|fd leak|resource` |
| 类型转换 | `cast|type coercion|implicit conversion|truncat` |

## 内置扫描模式（阶段3 `03_pattern_scan.py --list-patterns`）

| 模式名 | 说明 | 误报常见来源 |
|--------|------|--------------|
| `missing-pfree-on-error` | 错误路径疑似遗漏资源释放 | 依赖内存上下文自动回收的正常设计 |
| `missing-check-for-interrupts` | 长循环疑似缺少可取消点 | 循环体实际执行很快，无需可取消点 |
| `lock-without-matching-unlock` | 加锁后异常路径疑似遗漏解锁 | PG_TRY/PG_CATCH 或 RAII 式辅助函数已处理 |
| `integer-overflow-in-size-calc` | 大小计算乘法疑似缺少溢出检查 | 上游已对输入做了范围校验 |
| `signal-handler-non-async-safe` | 信号处理函数疑似调用非异步信号安全函数 | 只是设置了一个标志位，函数体扫描误报 |

**使用原则**：所有内置模式都是启发式规则，不是语义分析，扫描结果的价值完全取决于人工复核的质量。宁可少报几个真实候选，也不要把大量误报直接写进正式报告。

## Coccinelle 语义补丁参考（`coccinelle_patterns.cocci`）

如果环境装了 `spatch`（coccinelle），可以用比正则更精确的语义匹配代替阶段3脚本里的启发式规则，见同目录下的 `coccinelle_patterns.cocci`。

## 从历史修复中提炼新模式的方法

1. 挑选一个真实的历史 bug 修复 commit（阶段2产出）
2. 用 `git show <hash> -- src/` 看完整 diff，理解"错误写法"与"正确写法"的差异
3. 问自己："这个子系统/模块里，还有没有姊妹函数可能犯同样的错误？"
4. 如果有，把这个模式描述清楚（触发条件 + 应该存在但可能缺失的配对代码），
   要求 Claude 现场生成一段对应的 semgrep/grep 规则，加入阶段3的扫描
5. 记录到 `find-bug-artifacts/candidates.md`，标注来源 commit 和泛化理由
