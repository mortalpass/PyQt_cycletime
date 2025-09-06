import re
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import ast
import json
import os
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 导入配置
try:
    from config import output_img, index_path, output_form
except ImportError:
    logger.error("无法导入配置模块，请确保 config.py 存在")
    raise


class RestoreTimeChartGenerator:
    """恢复时间图表生成器类"""

    def __init__(self, output_dir: str = output_img):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 存储所有数据集的统计信息
        self.all_stats = defaultdict(list)
        # 存储所有图表的路径
        self.all_chart_paths = []

    def load_workstation_data(self) -> Dict[str, List[float]]:
        """加载工作站数据"""
        try:
            # 从环境变量获取工作站信息
            workstation_name = os.environ.get('WORKSTATION_NAME')
            if not workstation_name:
                logger.error("未设置环境变量 WORKSTATION_NAME")
                return {}

            # 加载提取的数据
            data_dir = Path("extracted_data")
            json_file = data_dir / f"{workstation_name}_restore_times.json"

            if not json_file.exists():
                logger.error(f"找不到数据文件: {json_file}")
                return {}

            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return data

        except Exception as e:
            logger.error(f"加载工作站数据时出错: {e}")
            return {}

    def calculate_statistics(self, restore_times: List[float]) -> Dict[str, float]:
        """计算恢复时间的统计信息"""
        if not restore_times:
            return {}

        return {
            'mean': np.mean(restore_times),
            'median': np.median(restore_times),
            'min': np.min(restore_times),
            'max': np.max(restore_times),
            'std': np.std(restore_times),
            'range': np.max(restore_times) - np.min(restore_times)
        }

    def find_extreme_indices(self, restore_times: List[float]) -> Tuple[List[int], List[int]]:
        """找到最小值和最大值的索引"""
        if not restore_times:
            return [], []

        min_value = np.min(restore_times)
        max_value = np.max(restore_times)

        min_indices = [i + 1 for i, t in enumerate(restore_times) if t == min_value]
        max_indices = [i + 1 for i, t in enumerate(restore_times) if t == max_value]

        return min_indices, max_indices

    def save_important_indices(self, dataset_name: str, min_indices: List[int], max_indices: List[int]):
        """保存重要索引到文件"""
        try:
            with open(index_path, 'a', encoding='utf-8') as f:
                for idx in min_indices:
                    f.write(f"{dataset_name}:min:{idx}\n")
                for idx in max_indices:
                    f.write(f"{dataset_name}:max:{idx}\n")
        except Exception as e:
            logger.error(f"保存重要索引时出错: {e}")

    def collect_statistics(self, stats: Dict[str, float], min_indices: List[int], max_indices: List[int],
                           outlier_count: int = 0, remark: str = ""):
        """收集统计信息，用于后续写入metadata.json"""
        # 收集所有统计信息
        self.all_stats['mean'].append(f"{stats['mean']:.2f}")
        self.all_stats['median'].append(f"{stats['median']:.2f}")
        self.all_stats['min'].append(f"{stats['min']:.2f}")
        self.all_stats['max'].append(f"{stats['max']:.2f}")
        self.all_stats['range'].append(f"{stats['range']:.2f}")
        self.all_stats['std'].append(f"{stats['std']:.2f}")
        self.all_stats['outlier_count'].append(str(outlier_count))

        # 构建备注信息
        remark_parts = []
        if remark:
            remark_parts.append(remark)
        if min_indices:
            remark_parts.append(f"Min at loops: {', '.join(map(str, min_indices))}")
        if max_indices:
            remark_parts.append(f"Max at loops: {', '.join(map(str, max_indices))}")

        self.all_stats['remark'].append("; ".join(remark_parts))

    def update_metadata_json(self):
        """将所有收集到的统计信息写入metadata.json文件"""
        try:
            # 使用config.py中的output_form路径构建metadata.json的完整路径
            metadata_path = Path(output_form) / 'metadata.json'

            # 确保output_form目录存在
            Path(output_form).mkdir(parents=True, exist_ok=True)

            # 读取现有的metadata.json文件
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                logger.error("metadata.json文件不存在，无法更新")
                return

            # 获取当前工作站名称
            workstation_name = os.environ.get('WORKSTATION_NAME')
            if not workstation_name:
                logger.error("未设置环境变量 WORKSTATION_NAME")
                return

            # 更新当前工作站的统计字段
            if workstation_name in metadata:
                metadata[workstation_name]["Median Times(s)"] = self.all_stats['median'][0] if self.all_stats[
                    'median'] else ""
                metadata[workstation_name]["Avg Time(s)"] = self.all_stats['mean'][0] if self.all_stats['mean'] else ""
                metadata[workstation_name]["Min Time(s)"] = self.all_stats['min'][0] if self.all_stats['min'] else ""
                metadata[workstation_name]["Max Time(s)"] = self.all_stats['max'][0] if self.all_stats['max'] else ""
                metadata[workstation_name]["Range(s)"] = self.all_stats['range'][0] if self.all_stats['range'] else ""
                metadata[workstation_name]["Std(s)"] = self.all_stats['std'][0] if self.all_stats['std'] else ""
                metadata[workstation_name]["Outlier Count"] = self.all_stats['outlier_count'][0] if self.all_stats[
                    'outlier_count'] else ""
                metadata[workstation_name]["Remark"] = self.all_stats['remark'][0] if self.all_stats['remark'] else ""

                # 更新折线图路径
                if self.all_chart_paths:
                    # 确保path字段存在
                    if "path" not in metadata[workstation_name]:
                        metadata[workstation_name]["path"] = {}
                    metadata[workstation_name]["path"]["linechart"] = self.all_chart_paths[0]

            # 写回文件
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"已更新metadata.json中的统计信息: {metadata_path}")

        except Exception as e:
            logger.error(f"更新metadata.json时出错: {e}")

    def create_chart(self, workstation_name: str, restore_times: List[float]):
        """为单个工作站创建图表"""
        if not restore_times:
            logger.warning(f"工作站 {workstation_name} 没有数据，跳过图表创建")
            self.all_chart_paths.append("")  # 添加空路径以保持顺序一致
            return None

        # 计算统计信息
        stats = self.calculate_statistics(restore_times)
        min_indices, max_indices = self.find_extreme_indices(restore_times)

        # 计算异常值数量（使用箱线图方法）
        Q1 = np.percentile(restore_times, 25)
        Q3 = np.percentile(restore_times, 75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outlier_count = np.sum((restore_times < lower_bound) | (restore_times > upper_bound))

        # 保存重要索引
        self.save_important_indices(workstation_name, min_indices, max_indices)

        # 收集统计信息
        self.collect_statistics(stats, min_indices, max_indices, outlier_count,
                                f"Outliers determined by boxplot method (Q1-1.5IQR, Q3+1.5IQR)")

        # 创建数据框
        df = pd.DataFrame({
            "Loop": list(range(1, len(restore_times) + 1)),
            "Restore Time": restore_times
        })

        # 创建图表
        plt.figure(figsize=(12, 6))
        sns.set(style="whitegrid")

        # 设置Y轴范围
        data = np.array(restore_times)
        data = np.array(data)
        data_min = np.min(data)
        data_max = np.max(data)
        data_range = data_max - data_min

        # 如果数据范围很小，使用百分比边距
        if data_range < data_max * 0.1:  # 数据变化很小
            margin = data_max * 0.01
            y_min = max(0, data_min - margin)  # 确保最小值不为负
            y_max = data_max + margin
        else:
            # 数据变化较大，使用固定边距
            margin = data_range * 0.1
            y_min = max(0, data_min - margin)
            y_max = data_max + margin
        plt.ylim(y_min, y_max)

        # 绘制折线图
        plt.plot(df["Loop"], df["Restore Time"],
                 marker='o', linestyle='-',
                 color='skyblue',
                 label='Restore Time',
                 markersize=6)

        # 添加数据点标签
        if len(restore_times) <= 20:
            for i, (loop, time) in enumerate(zip(df["Loop"], df["Restore Time"])):
                # 为所有数据点添加标签
                plt.text(loop, time, f'{time:.2f}s',
                         fontsize=8, ha='center', va='bottom',
                         bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7, edgecolor="none"))

        # 添加统计线
        plt.axhline(y=stats['mean'], color='blue',
                    linestyle='--', alpha=0.7,
                    label=f'Average ({stats["mean"]:.2f}s)')

        # 标记极值点
        for min_idx in min_indices:
            plt.plot(min_idx, stats['min'], 'g^', markersize=10,
                     label='Min' if min_idx == min_indices[0] else "")

        for max_idx in max_indices:
            plt.plot(max_idx, stats['max'], 'rv', markersize=10,
                     label='Max' if max_idx == max_indices[0] else "")

        # 添加统计信息框
        stats_lines = [
            f'Average: {stats["mean"]:<8.2f} s',
            f'Minimum: {stats["min"]:<8.2f} s (loop {", ".join(map(str, min_indices))})',
            f'Maximum: {stats["max"]:<8.2f} s (loop {", ".join(map(str, max_indices))})',
            f'Range:   {stats["range"]:<8.2f} s',
            f'Std Dev: {stats["std"]:<8.2f} s'
        ]

        plt.gca().text(1.02, 0.5, '\n'.join(stats_lines),
                       transform=plt.gca().transAxes,
                       fontsize=12, va='center',
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='black'),
                       fontfamily='monospace')

        # 设置标题和标签
        plt.title(f"Restore Time per Loop - {workstation_name}",
                  fontsize=14, fontweight='bold')
        plt.xlabel("Loop Index")
        plt.ylabel("Restore Time (s)")
        plt.grid(True, linestyle='--', alpha=0.5)

        # 设置图例
        plt.legend(loc='upper left', bbox_to_anchor=(1.01, 1), frameon=True, fontsize=11)

        # 调整布局
        plt.tight_layout()
        plt.subplots_adjust(right=0.8)

        # 生成安全文件名
        safe_name = re.sub(r'[^\w\-]', '_', workstation_name)
        filename = self.output_dir / f"{safe_name}_line_chart.png"

        # 保存图表
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"图表已保存至: {filename}")
        self.all_chart_paths.append(str(filename))  # 保存图表路径
        return filename

    def generate_charts(self):
        """生成所有图表"""
        # 清空重要索引文件
        try:
            open(index_path, "w").close()
        except Exception as e:
            logger.error(f"清空索引文件时出错: {e}")

        # 重置统计信息收集器
        self.all_stats = defaultdict(list)
        # 重置图表路径列表
        self.all_chart_paths = []

        # 加载工作站数据
        workstation_data = self.load_workstation_data()

        if not workstation_data:
            logger.error("未找到任何工作站数据")
            return

        # 为每个工作站创建图表
        chart_files = []
        for workstation_name, restore_times in workstation_data.items():
            chart_file = self.create_chart(workstation_name, restore_times)
            if chart_file:
                chart_files.append(chart_file)

        # 所有图表生成完毕后，更新metadata.json
        self.update_metadata_json()

        logger.info(f"成功生成 {len(chart_files)} 个图表")
        return chart_files


def main():
    """主函数"""
    try:
        # 创建图表生成器
        chart_generator = RestoreTimeChartGenerator()

        # 生成图表
        chart_files = chart_generator.generate_charts()

        if chart_files:
            print(f"\n成功生成 {len(chart_files)} 个图表:")
            for chart_file in chart_files:
                print(f"  - {chart_file}")
        else:
            print("未生成任何图表")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == "__main__":
    main()
