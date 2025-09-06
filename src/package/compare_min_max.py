import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import re
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 导入配置
try:
    from config import output_form, output_log, index_path
except ImportError:
    logger.error("无法导入配置模块，请确保 config.py 存在")
    raise


class CSVComparator:
    """CSV文件比较器类"""

    def __init__(self, base_path: Path, output_dir: Path):
        self.base_path = base_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_ordinal_suffix(self, number):
        """
        将整数转换为序数形式（1st, 2nd, 3rd, 4th等）

        参数:
            number: 整数或可以转换为整数的字符串

        返回:
            str: 序数字符串
        """
        try:
            num = int(number)
            # 处理特殊情况：11, 12, 13
            if 10 <= num % 100 <= 20:
                suffix = 'th'
            else:
                # 根据最后一位数字确定后缀
                last_digit = num % 10
                if last_digit == 1:
                    suffix = 'st'
                elif last_digit == 2:
                    suffix = 'nd'
                elif last_digit == 3:
                    suffix = 'rd'
                else:
                    suffix = 'th'

            return f"{num}{suffix}"
        except (ValueError, TypeError):
            # 如果无法转换为整数，返回原始值
            return str(number)

    def parse_file(self, file_path: Path) -> pd.Series:
        """解析CSV文件，返回包含阶段名称和时间数据的Series"""
        if not file_path.exists():
            logger.error(f"文件不存在: {file_path}")
            return pd.Series(dtype=object)

        try:
            # 读取CSV文件
            df = pd.read_csv(
                file_path,
                sep=';',
                header=None,
                names=['Stage', 'Time'],
                usecols=[0, 1],
                encoding='utf-8',
                on_bad_lines='warn'
            )

            # 清理数据
            df = df.dropna(subset=['Time'])
            df = df[df['Time'] != '']

            # 转换时间列为数值
            df['Time'] = pd.to_numeric(df['Time'], errors='coerce')

            # 保留每个阶段的最后一条记录
            df = df.drop_duplicates(subset=['Stage'], keep='last')

            return df.set_index('Stage')['Time']

        except Exception as e:
            logger.error(f"解析文件 {file_path} 时出错: {e}")
            return pd.Series(dtype=object)

    def parse_index_file(self, txt_path: Path) -> Dict[str, Dict[str, List[str]]]:
        """从txt文件中解析min、max和abnormal索引，按工作站名称分组"""
        index_dict = {}

        if not txt_path.exists():
            logger.error(f"索引文件不存在: {txt_path}")
            return index_dict

        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # 分割成三部分：工作站名称、键、值
                    parts = line.split(':', 2)
                    if len(parts) < 3:
                        continue

                    workstation_name = parts[0].strip()
                    key = parts[1].strip().lower()
                    value = parts[2].strip()

                    if workstation_name not in index_dict:
                        index_dict[workstation_name] = {'min': [], 'max': [], 'abnormal': []}

                    if key in ['min', 'max', 'abnormal']:
                        index_dict[workstation_name][key].append(value)

        except Exception as e:
            logger.error(f"读取索引文件失败: {e}")

        return index_dict

    def find_cycle_file(self, workstation_name: str, index: str) -> Path:
        """根据工作站名称和索引找到对应的cycleTime.csv文件"""
        # 构建文件路径模式
        workstation_dir = self.base_path / workstation_name

        # 查找文件 - 优先查找文件夹中的文件
        pattern = f"{int(index):03d}_*_*cycleTime.csv"
        found_files = list(workstation_dir.glob(pattern))

        # 如果没有找到，尝试查找根目录下的文件
        if not found_files:
            pattern = f"{int(index):03d}_*cycleTime.csv"
            found_files = list(workstation_dir.glob(pattern))

        if found_files:
            return found_files[0]

        logger.warning(f"未找到索引 {index} 在 {workstation_name} 对应的文件")
        return None

    def process_comparison(
            self,
            min_files: List[Tuple[str, Path]],
            max_files: List[Tuple[str, Path]],
            abnormal_files: List[Tuple[str, Path]],
            workstation_name: str
    ) -> Path:
        """处理文件并生成结果CSV"""
        # 合并所有数据
        all_data = {}

        # 提取abnormal索引用于检查min和max索引是否与其相同
        abnormal_indices = {index for index, _ in abnormal_files}

        # 添加max数据 - 如果索引与abnormal相同，则修改列名
        for index, file_path in max_files:
            data = self.parse_file(file_path)
            if not data.empty:
                ordinal_index = self.get_ordinal_suffix(index)
                if index in abnormal_indices:
                    # 如果max索引与abnormal相同，添加_abnormal后缀
                    all_data[f"Max_abnormal({ordinal_index} loop)"] = data
                else:
                    all_data[f"Max({ordinal_index} loop)"] = data

        # 添加min数据 - 如果索引与abnormal相同，则修改列名
        for index, file_path in min_files:
            data = self.parse_file(file_path)
            if not data.empty:
                ordinal_index = self.get_ordinal_suffix(index)
                if index in abnormal_indices:
                    # 如果min索引与abnormal相同，添加_abnormal后缀
                    all_data[f"Min_abnormal({ordinal_index} loop)"] = data
                else:
                    all_data[f"Min({ordinal_index} loop)"] = data

        # 添加abnormal数据 - 只添加不在min和max中的abnormal索引
        min_max_indices = {index for index, _ in min_files} | {index for index, _ in max_files}
        for index, file_path in abnormal_files:
            if index not in min_max_indices:  # 只添加独有的abnormal索引
                data = self.parse_file(file_path)
                if not data.empty:
                    ordinal_index = self.get_ordinal_suffix(index)
                    all_data[f"Abnormal({ordinal_index} loop)"] = data

        # 创建DataFrame
        result = pd.DataFrame(all_data)
        result.index.name = 'Stage'
        result = result.reset_index()

        # 计算时间差（max - min）
        # 找到第一个min列和第一个max列（无论是否有_abnormal后缀）
        min_cols = [col for col in result.columns if col.startswith('Min')]
        max_cols = [col for col in result.columns if col.startswith('Max')]

        if min_cols and max_cols:
            # 使用第一个min和max列计算差异
            min_col = min_cols[0]
            max_col = max_cols[0]

            # 确保列是数值类型
            result[min_col] = pd.to_numeric(result[min_col], errors='coerce')
            result[max_col] = pd.to_numeric(result[max_col], errors='coerce')

            # 计算时间差并保留四位小数
            result['Time_Difference(Max-Min)'] = (result[max_col] - result[min_col]).round(4)

        # 删除第一行（如果有"Log Folder Path"）
        if not result.empty and result.iloc[0]['Stage'] == 'Log Folder Path':
            result = result.iloc[1:].reset_index(drop=True)

        # 创建工作站子文件夹
        workstation_dir = self.output_dir / workstation_name
        workstation_dir.mkdir(parents=True, exist_ok=True)

        # 保存结果到工作站子文件夹
        output_path = workstation_dir / f"{workstation_name}_comparison.csv"
        result.to_csv(output_path, sep=';', index=False, encoding='utf-8')
        logger.info(f"处理完成！结果已保存到 {output_path}")

        return output_path

    def process_all_workstations(self):
        """处理所有工作站的比较"""
        # 获取所有索引值（按工作站名称分组）
        all_indices = self.parse_index_file(Path(index_path))

        if not all_indices:
            logger.error("无法获取索引值，请检查important_index.txt文件格式")
            return

        # 处理每个工作站
        for workstation_name, indices in all_indices.items():
            logger.info(f"\n{'=' * 50}")
            logger.info(f"处理工作站: {workstation_name}")

            # 获取索引值
            min_indices = indices.get('min', [])
            max_indices = indices.get('max', [])
            abnormal_indices = indices.get('abnormal', [])

            logger.info(f"Min 索引: {min_indices}")
            logger.info(f"Max 索引: {max_indices}")
            logger.info(f"Abnormal 索引: {abnormal_indices}")

            # 查找对应的文件
            min_files = []
            for index in min_indices:
                file_path = self.find_cycle_file(workstation_name, index)
                if file_path:
                    min_files.append((index, file_path))

            max_files = []
            for index in max_indices:
                file_path = self.find_cycle_file(workstation_name, index)
                if file_path:
                    max_files.append((index, file_path))

            abnormal_files = []
            for index in abnormal_indices:
                file_path = self.find_cycle_file(workstation_name, index)
                if file_path:
                    abnormal_files.append((index, file_path))

            if not min_files and not max_files and not abnormal_files:
                logger.warning(f"未找到任何文件，跳过 {workstation_name}")
                continue

            # 处理文件比较
            self.process_comparison(min_files, max_files, abnormal_files, workstation_name)


def main():
    """主函数"""
    try:
        # 创建比较器实例
        comparator = CSVComparator(
            base_path=Path(output_log),
            output_dir=Path(output_form)
        )

        # 处理所有工作站
        comparator.process_all_workstations()

        logger.info("所有比较处理完成!")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == "__main__":
    main()