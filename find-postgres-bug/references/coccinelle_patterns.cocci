// coccinelle_patterns.cocci
// 供 find-postgres-bug 阶段3使用的示例语义补丁。
// 运行方式（需要安装 coccinelle / spatch）：
//   spatch --sp-file coccinelle_patterns.cocci --dir <postgres源码>/src --very-quiet
//
// 这些规则只是起点，鼓励根据阶段2挖掘出的具体历史模式现场编写更精确的规则。
// 所有命中都需要人工复核，coccinelle 的语义匹配比正则更准，但仍会有假阳性
// （比如资源在调用者层面被释放、或使用了非标准命名的清理函数）。

// ---------------------------------------------------------------------
// 规则1：palloc 分配后，在函数返回前的某条路径上没有对应的 pfree
// 适用场景：怀疑某个函数在异常/提前返回路径遗漏清理
// ---------------------------------------------------------------------
@possible_leak@
expression E;
identifier func;
position p1, p2;
@@

func(...) {
  ...
  E = palloc@p1(...);
  ... when != pfree(E)
      when != E = NULL
  return@p2 ...;
  ...
}

// 报告命中位置，人工确认 E 是否确实需要在此路径释放
// （很多情况下 E 会在上层 MemoryContext 结束时自动回收，这不是 bug）


// ---------------------------------------------------------------------
// 规则2：LWLockAcquire 之后，某条路径缺少匹配的 LWLockRelease
// ---------------------------------------------------------------------
@possible_unlock_missing@
expression L;
position p1, p2;
@@

LWLockAcquire@p1(L, ...);
... when != LWLockRelease(L)
(
  return@p2 ...;
|
  ereport(ERROR, ...);
)


// ---------------------------------------------------------------------
// 规则3：memcpy/memmove 的长度参数来自两个变量的乘积，且函数上下文中
// 未见任何形式的溢出检查（AllocSizeIsValid / overflow 关键词）
// ---------------------------------------------------------------------
@possible_overflow@
expression A, B, DST, SRC;
position p1;
@@

memcpy@p1(DST, SRC, A * B)


// 使用建议：
// 1. spatch 输出的每个 position (p1/p2) 都要结合完整函数体人工判断
// 2. 针对阶段2挖掘出的具体历史 bug，参照上面的写法现场扩展新规则，
//    重点关注该 bug 所在子系统里的"姊妹函数"（相似签名、相似逻辑的其他函数）
