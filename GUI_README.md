# Tkinter Desktop GUI

这个仓库现在额外提供了一个基于 `Tkinter` 的桌面入口：

```bash
python tkinter_app.py
```

## 当前能力

- `年报抓取` 页签：映射 `main.py` / `spider.py` 的常用参数
- `文本提取` 页签：映射 `extract_text.py`
- `指标计算` 页签：映射 `digital_transformation.py`
- `一键全流程` 页签：依次执行抓取、文本提取、指标计算
- 后台线程运行任务，避免 GUI 卡死
- 日志实时回显
- 显示步骤进度、当前阶段、结果统计与产物位置
- 支持停止当前任务
- 自动保存表单配置到 `gui_config.json`
- 抓取页、提取页和全流程页支持通过 GUI 重置旧 checkpoint / 成功后删除 checkpoint

## 设计说明

第一版 GUI 采用“外壳包装”方式，没有改写现有业务逻辑，而是通过子进程调用现有脚本。这种方案的优点是：

- 对现有代码侵入小
- CLI 和 GUI 共用同一套参数语义
- 后续便于继续重构成内部服务层

## 推荐后续演进

如果准备把它继续做成更完整的桌面应用，建议下一步优先做这些事情：

1. 把 `spider.py`、`extract_text.py`、`digital_transformation.py` 各自抽出可直接调用的服务函数
2. 增加更细粒度的进度反馈，而不是仅显示日志
3. 增加结果预览区，例如统计已下载 PDF 数、已提取文本数、生成的 CSV 路径
4. 增加打包脚本，例如使用 `PyInstaller`

## 打包示例

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name report_spider_gui tkinter_app.py
```
