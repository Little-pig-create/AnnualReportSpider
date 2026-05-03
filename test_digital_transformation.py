import math
import tempfile
import unittest
from pathlib import Path

from digital_transformation import (
    CATEGORY_VALUE,
    DEFAULT_END_YEAR,
    DEFAULT_START_YEAR,
    append_checkpoint_entry,
    build_panel,
    calculate_digital_transformation,
    count_group_frequencies,
    file_in_year_range,
    load_checkpoint,
    parse_report_metadata,
    process_report,
)


class DigitalTransformationTests(unittest.TestCase):
    def test_count_group_frequencies_handles_negation_and_case(self) -> None:
        text = (
            "公司推进人工智能、FinTech、NFC支付和云计算平台建设。"
            "报告期内未开展区块链业务，也没有数字货币相关应用。"
        )

        counts = count_group_frequencies(text)

        self.assertEqual(counts["人工智能技术"], 1)
        self.assertEqual(counts["数字技术应用"], 2)
        self.assertEqual(counts["云计算技术"], 1)
        self.assertEqual(counts["区块链技术"], 0)

    def test_calculate_digital_transformation_uses_log1p(self) -> None:
        text = "人工智能 大数据 云计算"
        self.assertTrue(math.isclose(calculate_digital_transformation(text), math.log1p(3)))

    def test_process_report_uses_unified_category_value(self) -> None:
        file_path = Path("txt_extract/2024/689009_九号公司_九号有限公司2024年年度报告_1223072410.txt")
        row = process_report(file_path, {})
        five_group_total = (
            row["人工智能技术"]
            + row["区块链技术"]
            + row["云计算技术"]
            + row["大数据技术"]
            + row["数字技术应用"]
        )
        self.assertEqual(row["类别"], CATEGORY_VALUE)
        self.assertEqual(row["数字化转型"], five_group_total)

    def test_parse_report_metadata_and_year_filter(self) -> None:
        file_path = Path("txt_extract/2019/000001_平安银行_2019年年度报告_1207305488.txt")
        metadata = parse_report_metadata(file_path)

        self.assertEqual(metadata["stkcd"], "000001")
        self.assertEqual(metadata["year"], "2019")
        self.assertEqual(metadata["公司简称"], "平安银行")
        self.assertTrue(file_in_year_range(file_path, 2014, 2024))
        self.assertFalse(file_in_year_range(file_path, 2020, 2024))

    def test_year_filter_falls_back_to_parent_folder_when_title_pattern_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "2024" / "custom_report.txt"
            sample.parent.mkdir(parents=True, exist_ok=True)
            sample.write_text("示例文本", encoding="utf-8")

            metadata = parse_report_metadata(sample)
            self.assertEqual(metadata["year"], "2024")
            self.assertTrue(file_in_year_range(sample, 2024, 2024))

    def test_checkpoint_can_resume_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_file = Path(tmp_dir) / "checkpoint.jsonl"
            row = {"stkcd": "000001", "year": "2019", "类别": CATEGORY_VALUE}

            with checkpoint_file.open("a", encoding="utf-8") as checkpoint:
                append_checkpoint_entry(checkpoint, "file-a", row)
                checkpoint.write("{broken json\n")

            loaded = load_checkpoint(checkpoint_file)
            self.assertEqual(loaded["file-a"], row)

    def test_default_year_range_constants(self) -> None:
        self.assertEqual(DEFAULT_START_YEAR, 2014)
        self.assertEqual(DEFAULT_END_YEAR, 2024)

    def test_build_panel_keeps_checkpoint_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            input_dir = tmp_dir_path / "txt_extract" / "2024"
            input_dir.mkdir(parents=True, exist_ok=True)
            sample_file = input_dir / "000001_测试公司_2024年年度报告_1.txt"
            sample_file.write_text("人工智能 云计算", encoding="utf-8")

            output_file = tmp_dir_path / "panel.csv"
            checkpoint_file = tmp_dir_path / "checkpoint.jsonl"

            build_panel(
                input_dir=tmp_dir_path / "txt_extract",
                output_file=output_file,
                label_file=None,
                checkpoint_file=checkpoint_file,
                start_year=2024,
                end_year=2024,
                workers=1,
                executor_type="thread",
                log_every=1,
                reset_checkpoint=False,
            )

            self.assertTrue(output_file.exists())
            self.assertTrue(checkpoint_file.exists())

    def test_build_panel_deletes_checkpoint_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            input_dir = tmp_dir_path / "txt_extract" / "2024"
            input_dir.mkdir(parents=True, exist_ok=True)
            sample_file = input_dir / "000001_测试公司_2024年年度报告_1.txt"
            sample_file.write_text("人工智能 云计算", encoding="utf-8")

            output_file = tmp_dir_path / "panel.csv"
            checkpoint_file = tmp_dir_path / "checkpoint.jsonl"

            build_panel(
                input_dir=tmp_dir_path / "txt_extract",
                output_file=output_file,
                label_file=None,
                checkpoint_file=checkpoint_file,
                start_year=2024,
                end_year=2024,
                workers=1,
                executor_type="thread",
                log_every=1,
                reset_checkpoint=False,
                delete_checkpoint_on_success=True,
            )

            self.assertTrue(output_file.exists())
            self.assertFalse(checkpoint_file.exists())


if __name__ == "__main__":
    unittest.main()
