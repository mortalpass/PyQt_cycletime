import re
from datetime import datetime
from pathlib import Path
import pandas as pd
import logging
from typing import List, Optional, Dict
import os
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M-%S'
)
logger = logging.getLogger(__name__)


class CycleTimeExtractor:
    """循环时间提取器，封装提取逻辑"""

    # 编译一次正则表达式，提高效率
    TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")

    def __init__(self, target_row: int = 7, target_col: int = 1):
        self.target_row = target_row
        self.target_col = target_col

    def find_cycle_files(self, folder_path: Path) -> List[Path]:
        """递归查找所有 cycleTime.csv 文件"""
        cycle_files = []
        try:
            # 使用 rglob 递归查找
            for file_path in folder_path.rglob("*cycleTime.csv"):
                if file_path.is_file():
                    cycle_files.append(file_path)
        except Exception as e:
            logger.error(f"在 {folder_path} 中查找文件时出错: {e}")
        return cycle_files

    def extract_timestamp(self, file_path: Path) -> Optional[datetime]:
        """从文件名中提取时间戳"""
        try:
            match = self.TIMESTAMP_PATTERN.search(file_path.name)
            if match:
                return datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            logger.warning(f"文件名中时间戳格式无效: {file_path.name}")
        return None

    def extract_restore_time(self, file_path: Path) -> Optional[float]:
        """从 CSV 文件中提取恢复时间"""
        try:
            # 使用 pandas 读取 CSV 文件
            df = pd.read_csv(
                file_path,
                sep=';',
                header=None,
                encoding='utf-8',
                engine='python',
                on_bad_lines='warn'  # 处理格式不正确的行
            )

            # 确保有足够的行和列
            if df.shape[0] > self.target_row and df.shape[1] >= self.target_col:
                cell_value = df.iloc[self.target_row, self.target_col]
                try:
                    return float(cell_value)
                except (ValueError, TypeError):
                    logger.warning(f"无法转换为浮点数: {file_path} 中的值 '{cell_value}'")
            else:
                logger.warning(f"文件 {file_path.name} 的行列数不足 ({df.shape[0]}行, {df.shape[1]}列)")
        except pd.errors.EmptyDataError:
            logger.warning(f"文件 {file_path.name} 为空或没有数据")
        except Exception as e:
            logger.error(f"处理文件 {file_path} 时出错: {e}")
        return None

    def process_workstation_folder(self, folder_path: Path, workstation_name: str) -> Dict[str, List[float]]:
        """处理单个工作站的文件夹并返回恢复时间列表"""
        if not folder_path.exists() or not folder_path.is_dir():
            logger.warning(f"工作站文件夹不存在或不是目录: {folder_path}")
            return {}

        logger.info(f"开始处理工作站 {workstation_name} 的文件夹: {folder_path}")
        cycle_files = self.find_cycle_files(folder_path)

        if not cycle_files:
            logger.warning(f"在 {folder_path} 中未找到任何 cycleTime.csv 文件")
            return {}

        # 收集时间戳和恢复时间
        time_data = []
        for file_path in cycle_files:
            timestamp = self.extract_timestamp(file_path)
            restore_time = self.extract_restore_time(file_path)

            if timestamp and restore_time is not None:
                time_data.append((timestamp, restore_time))
            else:
                logger.debug(f"跳过文件: {file_path.name}")

        # 按时间戳排序并返回时间值
        time_data.sort(key=lambda x: x[0])
        times = [val for _, val in time_data]

        logger.info(f"从工作站 {workstation_name} 成功提取 {len(times)} 个恢复时间 (共找到 {len(cycle_files)} 个文件)")

        return {
            workstation_name: times
        }


def main():
    """主函数"""
    try:
        # 从环境变量获取工作站信息
        folder_path = os.environ.get('FOLDER_PATH')
        workstation_name = os.environ.get('WORKSTATION_NAME')

        if not folder_path or not workstation_name:
            logger.error("未设置环境变量 FOLDER_PATH 或 WORKSTATION_NAME")
            return

        folder_path = Path(folder_path)

        # 创建提取器实例
        extractor = CycleTimeExtractor(target_row=7, target_col=1)

        # 处理工作站的文件夹
        results = extractor.process_workstation_folder(folder_path, workstation_name)

        if not results:
            logger.warning(f"工作站 {workstation_name} 没有提取到任何数据")
            return

        # 输出结果
        print(f"\n工作站 {workstation_name} 处理结果:")
        for ws_name, times in results.items():
            print(f"  恢复时间数量: {len(times)}")
            print(f"  恢复时间范围: {min(times):.3f} - {max(times):.3f} 秒")
            print(f"  平均恢复时间: {sum(times) / len(times):.3f} 秒")
            print(f"  示例数据: {times[:3]}{'...' if len(times) > 3 else ''}")

        # 保存结果到JSON文件
        output_dir = Path("extracted_data")
        output_dir.mkdir(exist_ok=True)

        json_output_path = output_dir / f"{workstation_name}_restore_times.json"
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # 保存结果到文本文件
        txt_output_path = output_dir / f"{workstation_name}_restore_times.txt"
        with open(txt_output_path, 'w', encoding='utf-8') as f:
            f.write(f"工作站: {workstation_name}\n")
            f.write(f"文件夹路径: {folder_path}\n")
            f.write(f"恢复时间数量: {len(times)}\n")
            f.write(f"恢复时间列表: {times}\n")

        print(f"\n结果已保存到:")
        print(f"  JSON文件: {json_output_path}")
        print(f"  文本文件: {txt_output_path}")

        # 更新主结果文件
        main_results_path = output_dir / "all_restore_times.json"
        all_results = {}

        if main_results_path.exists():
            with open(main_results_path, 'r', encoding='utf-8') as f:
                all_results = json.load(f)

        all_results.update(results)

        with open(main_results_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        print(f"  主结果文件已更新: {main_results_path}")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == '__main__':
    main()