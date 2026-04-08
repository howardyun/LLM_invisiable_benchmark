
Resume文件来源：\
https://www.kaggle.com/datasets/hadikp/resume-data-pdf?resource=download


# 解析
## 1. 解析单个 PDF

```bash
python Parser/parser_runner.py -i "path/to/your/pdf" -o "output/path/you/specified"
```

作用：

- 对这个单独的 PDF 运行全部 parser

---

## 2. 批量解析某个目录下所有 PDF

```bash
python Parser/parser_runner.py -i "path/to/your/pdfDataset" -o "output/path/you/specified"
```

作用：

- 递归扫描该目录下所有 PDF

---

## 3. 先预览任务，不真正执行

强烈建议大批量跑之前先预览：

```bash
python Parser/parser_runner.py -i "path/to/your/pdfDataset" -o "output/path/you/specified" --dry-run
```

作用：

- 只打印将要执行的 parser、环境、输入、输出、命令
- 不真正运行

---

## 4. 只跑部分 framework

例如只跑 `docling`、`langchain`、`llmsherpa`：

```bash
python Parser/parser_runner.py -i "path/to/your/pdfDataset" -o "output/path/you/specified" -f docling langchain llmsherpa
```

可选 framework 以 `--list-frameworks` 输出为准。

---

## 5. 只跑指定 parser

例如只跑三个指定 parser：

```bash
python Parser/parser_runner.py -i "path/to/your/pdfDataset" -o "output/path/you/specified" -p langchain.pypdf llamaindex.smartpdf llmsherpa.default
```

这个模式适合你做小范围调试。

---

## 6. 不保留 metadata

默认会保留 metadata。如果你只想保留正文内容：

```bash
python Parser/parser_runner.py -i "path/to/your/pdfDataset" -o "output/path/you/specified" --no-include-metadata
```

---


## 汇总文件说明

### `run_summary.json`

记录每个任务的详细运行信息，例如：

- 输入路径
- 输出路径
- parser id
- framework
- conda 环境
- return code
- 运行耗时
- 是否成功

### `benchmark_summary.json`

记录整体 benchmark 汇总，例如：

- 总任务数
- 成功数 / 失败数
- 总耗时
- 每个 framework 的统计
- 每个 parser 的统计

---


# 评估

## 1. 启动方式

评估脚本为：`Evaluation/evaluate_injection_recovery.py`

使用前，你只需要修改这个文件里 **14 到 18 行** 的默认路径配置：

```14:18:Evaluation/evaluate_injection_recovery.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ATTACK_RECORDS = PROJECT_ROOT / "Dataset" / "attack_records.csv"
DEFAULT_PARSE_RESULTS = PROJECT_ROOT / "Parser" / "BatchParseResult"
DEFAULT_RUN_SUMMARY = DEFAULT_PARSE_RESULTS / "run_summary.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Evaluation" / "results"
```

把这些路径改成你当前实验要使用的数据路径、解析结果路径和评估输出路径即可。

修改完成后，直接运行：

```bash
python Evaluation/evaluate_injection_recovery.py
```

---

## 2. 评估输出内容

脚本运行后会在 `Evaluation/results/` 下生成以下文件：

- `sample_level_metrics.csv`
- `parser_level_metrics.csv`
- `parser_attack_category_metrics.csv`
- `parser_attack_subcategory_metrics.csv`
- `evaluation_summary.json`

---

## 3. 本项目的评估层级

本项目从 **四个层级** 对 PDF 解析结果进行评估，用于分析不同 parser 对隐式注入内容的暴露能力与恢复情况。

### （1）样本级评估

对应文件：`sample_level_metrics.csv`

用于评估：

- 某个 parser 对某一个攻击 PDF 是否成功解析出注入内容；
- 该注入内容恢复得有多完整；
- 是否存在完整连续命中；
- 按顺序恢复了多少 token；
- token 内容整体重叠了多少。

这一层级是最细粒度的评估单元。

---

### （2）Parser 级评估

对应文件：`parser_level_metrics.csv`

用于统计每个 parser 在全部攻击样本上的整体表现，包括：

- 解析成功率（`injection_parse_success_rate`）
- 成功样本数量（`successful_sample_count`）
- 成功样本上的平均内容恢复度（`avg_recovery_completeness_on_success`）
- 输出文件可用数量（`available_output_count`）

这一层级用于横向比较不同 parser 的总体暴露能力和恢复能力。

---

### （3）攻击类别级评估

对应文件：`parser_attack_category_metrics.csv`

用于统计每个 parser 在不同 **攻击大类** 下的表现，例如：

- `Visual Hiding`
- `Geometric Escape`
- `Presentation Layer Encoding`
- `Parsing Order/Multi-view Inconsistency`

这一层级用于分析：

- 哪类攻击更容易被不同 parser 暴露；
- 某个 parser 对哪种攻击类型更脆弱；
- 不同 parser 在不同攻击类型下的恢复能力差异。

---

### （4）攻击子类别级评估

对应文件：`parser_attack_subcategory_metrics.csv`

用于统计每个 parser 在更细粒度攻击方式下的表现，例如：

- `white_text`
- `zero_size_font`
- `zero_width`
- `ocg`
- `misaligned`
- `out_of_bound`
- `trm`
- `double_layer_pdf`

这一层级可以帮助你进一步定位：

- parser 对哪一种具体隐式注入手法最敏感；
- 哪些攻击子类型最容易被成功解析出来；
- 哪些子类型即使成功暴露，恢复内容也不完整。

---





