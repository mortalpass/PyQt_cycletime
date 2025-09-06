import re
import shutil
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List
import os
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class LogProcessor:
    """日志处理类，封装所有日志处理逻辑"""

    TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
    FILE_PATTERNS = ["*cycleTime.csv", "*host.log", "*device.log", "*serial.log"]

    def __init__(self, output_base: Path, index_path: Path):
        self.output_base = output_base
        self.index_path = index_path
        self.important_indices = self.load_important_indices()

    def load_important_indices(self) -> Dict[str, Dict[int, List[str]]]:
        """加载重要索引字典 {工作站名称: {索引: [标记列表]}}"""
        index_dict = defaultdict(lambda: defaultdict(list))

        if not self.index_path.exists():
            logger.warning(f"重要索引文件未找到: {self.index_path}")
            return index_dict

        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # 格式: workstation_name:type:index
                    parts = line.split(':', 2)
                    if len(parts) < 3:
                        continue

                    workstation_name = parts[0].strip()
                    mark = parts[1].strip().lower()
                    value = parts[2].strip()

                    try:
                        index_value = int(value)
                        index_dict[workstation_name][index_value].append(mark)
                    except ValueError:
                        logger.warning(f"无效索引值 '{value}'，跳过")

        except Exception as e:
            logger.error(f"读取索引文件失败: {e}")

        return index_dict

    def clean_output_directory(self, output_dir: Path):
        """安全清空输出目录"""
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            return

        try:
            for item in output_dir.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.error(f"删除 {item} 失败: {e}")
        except Exception as e:
            logger.error(f"访问输出目录失败: {e}")

    def find_log_files(self, source_dir: Path) -> List[Path]:
        """查找所有匹配的日志文件"""
        all_files = []
        for pattern in self.FILE_PATTERNS:
            try:
                found_files = list(source_dir.rglob(pattern))
                all_files.extend(found_files)
            except Exception as e:
                logger.error(f"查找 {pattern} 文件失败: {e}")
        return all_files

    def extract_timestamp_identifier(self, path: Path) -> str:
        """从路径中提取时间戳标识符"""
        for part in reversed(path.parts):
            match = self.TIMESTAMP_PATTERN.search(part)
            if match:
                return match.group()
        return "unknown"

    def group_files_by_timestamp(self, files: List[Path]) -> Dict[str, List[Path]]:
        """按时间戳分组文件"""
        timestamp_groups = defaultdict(list)
        for file_path in files:
            timestamp = self.extract_timestamp_identifier(file_path)
            timestamp_groups[timestamp].append(file_path)
        return timestamp_groups

    def format_folder_name(self, index: int, marks: List[str], timestamp: str) -> str:
        """格式化文件夹名称，处理多个标记的情况"""
        # 对标记进行排序，确保一致的命名格式
        sorted_marks = sorted(marks)
        marks_str = "_".join(sorted_marks)
        return f"{index:03d}_{marks_str}_{timestamp}"

    def process_timestamp_group(
            self,
            group: List[Path],
            timestamp: str,
            index: int,
            important_marks: Dict[int, List[str]],
            output_dir: Path
    ):
        """处理单个时间戳组"""
        # 检查是否为重要索引
        if index in important_marks:
            marks = important_marks[index]
            folder_name = self.format_folder_name(index, marks, timestamp)
            timestamp_dir = output_dir / folder_name
            timestamp_dir.mkdir(parents=True, exist_ok=True)

            for src_path in group:
                dest_path = timestamp_dir / src_path.name
                try:
                    shutil.copy2(src_path, dest_path)
                    logger.debug(f"复制重要文件: {src_path.name} -> {folder_name}/")

                    # 额外处理：将cycleTime.csv复制到根目录
                    if src_path.name.endswith('cycleTime.csv'):
                        root_copy_name = f"{index:03d}_{timestamp}-cycleTime.csv"
                        root_copy_path = output_dir / root_copy_name
                        shutil.copy2(src_path, root_copy_path)
                        logger.debug(f"复制重要cycleTime到根目录: {root_copy_name}")

                except Exception as e:
                    logger.error(f"复制 {src_path} 失败: {e}")
        else:
            # 非重要索引 - 只处理CSV文件
            for src_path in group:
                if src_path.suffix.lower() == '.csv':
                    new_name = f"{index:03d}_{timestamp}_{src_path.name}"
                    dest_path = output_dir / new_name
                    try:
                        shutil.copy2(src_path, dest_path)
                        logger.debug(f"复制CSV文件: {src_path.name} -> {new_name}")
                    except Exception as e:
                        logger.error(f"复制 {src_path} 失败: {e}")

    def process_workstation_logs(self, source_dir: Path, workstation_name: str):
        """处理单个工作站的日志文件夹"""
        # 创建工作站输出目录
        output_dir = self.output_base / workstation_name
        self.clean_output_directory(output_dir)

        # 获取当前工作站的重要索引和标记
        important_marks = self.important_indices.get(workstation_name, {})

        # 创建一个更易读的日志输出
        readable_marks = {}
        for idx, marks in important_marks.items():
            marks_str = "_".join(sorted(marks))
            if marks_str not in readable_marks:
                readable_marks[marks_str] = []
            readable_marks[marks_str].append(idx)

        logger.info(f"处理 {workstation_name}，重要索引和标记: {readable_marks}")

        # 查找所有文件
        all_files = self.find_log_files(source_dir)
        if not all_files:
            logger.warning(f"{workstation_name} 中未找到任何文件")
            return

        # 按时间戳分组
        timestamp_groups = self.group_files_by_timestamp(all_files)
        if not timestamp_groups:
            logger.warning(f"{workstation_name} 中未找到有效时间戳")
            return

        # 按时间戳排序
        sorted_timestamps = sorted(timestamp_groups.keys())
        logger.info(f"找到 {len(sorted_timestamps)} 个时间戳组")

        # 处理每个时间戳组
        for idx, timestamp in enumerate(sorted_timestamps, start=1):
            self.process_timestamp_group(
                group=timestamp_groups[timestamp],
                timestamp=timestamp,
                index=idx,
                important_marks=important_marks,
                output_dir=output_dir
            )

        # 结果统计
        processed_count = len(all_files)
        important_folders = len([i for i in range(1, len(sorted_timestamps) + 1) if i in important_marks])
        logger.info(
            f"完成 {workstation_name}! "
            f"处理文件: {processed_count}, "
            f"重要文件夹: {important_folders}, "
            f"输出目录: {output_dir}"
        )

    def process_all_workstations(self):
        """处理所有工作站的日志文件"""
        # 确保输出基础目录存在
        self.output_base.mkdir(parents=True, exist_ok=True)

        # 从环境变量获取工作站信息
        folder_path = os.environ.get('FOLDER_PATH')
        workstation_name = os.environ.get('WORKSTATION_NAME')

        if not folder_path or not workstation_name:
            logger.error("未设置环境变量 FOLDER_PATH 或 WORKSTATION_NAME")
            return

        folder_path = Path(folder_path)

        if not folder_path.exists():
            logger.error(f"工作站文件夹不存在: {folder_path}")
            return

        logger.info(f"开始处理工作站: {workstation_name}")
        logger.info(f"源文件夹: {folder_path}")

        # 处理当前工作站的日志
        self.process_workstation_logs(folder_path, workstation_name)

        logger.info("所有工作站日志处理完成!")


def main():
    """主函数"""
    try:
        # 从配置导入路径
        try:
            from config import index_path, output_log
        except ImportError:
            logger.error("无法导入配置模块，请确保 config.py 存在")
            return

        processor = LogProcessor(
            output_base=Path(output_log),
            index_path=Path(index_path)
        )
        processor.process_all_workstations()
        logger.info("所有日志处理完成!")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == '__main__':
    main()