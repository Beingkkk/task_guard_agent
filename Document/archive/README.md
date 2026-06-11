# 归档目录 (Archive)

本目录存放已合并的变更提案和过期的 plan 版本。

---

## 归档规则

### 1. 变更提案归档

当 `changes/proposal-{NNNN}.md` 完成 `/sdd-archive` 流程后，移动到此目录：

```
archive/proposal-{NNNN}-{YYYY-MM-DD}-merged.md
```

### 2. Plan 版本归档

当 plan 因 Type-A（需求变更）或 Type-B（设计变更）而大幅修订时，旧版本归档：

```
archive/plan-{module}-v{旧版本}-{YYYY-MM-DD}.md
```

### 3. Spec 版本归档

当 spec 升级 Major/Minor 版本时，旧版本归档：

```
archive/spec-v{旧版本}-{YYYY-MM-DD}.md
```

---

## 现有归档

> 暂无归档。基线采纳后首个变更完成时产生。
