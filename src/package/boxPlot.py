import re
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import ast
import json
import os
from matplotlib.patches import Patch

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


class BoxPlotGenerator:
    """箱线图生成器类"""

    def __init__(self, output_dir: str = output_img):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.saved_indices = set()  # 用于跟踪已保存的索引，避免重复
        # 存储所有单数据集箱线图路径
        self.single_boxplot_paths = []
        # 存储多数据集箱线图路径
        self.multi_boxplot_path = None

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

    def load_all_data_from_json(self) -> Dict[str, List[float]]:
        """从JSON文件加载所有工作站数据"""
        # 加载提取的数据
        data_dir = Path("extracted_data")
        json_file = data_dir / f"all_restore_times.json"
        try:
            if not Path(json_file).exists():
                logger.error(f"找不到数据文件: {json_file}")
                return {}

            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return data

        except Exception as e:
            logger.error(f"从JSON文件加载数据时出错: {e}")
            return {}

    def calculate_statistics(self, data: List[float]) -> Dict[str, float]:
        """计算数据的统计信息"""
        if not data:
            return {}

        q1 = np.percentile(data, 25)
        q3 = np.percentile(data, 75)
        iqr = q3 - q1

        return {
            'mean': np.mean(data),
            'median': np.median(data),
            'q1': q1,
            'q3': q3,
            'iqr': iqr,
            'lower_bound': q1 - 1.5 * iqr,
            'upper_bound': q3 + 1.5 * iqr,
            'min': np.min(data),
            'max': np.max(data)
        }

    def find_extreme_indices(self, data: List[float], lower_bound: float, upper_bound: float) -> List[
        Tuple[int, float]]:
        """找到异常值的索引和值"""
        outliers = []
        for idx, val in enumerate(data, start=1):
            if val < lower_bound or val > upper_bound:
                outliers.append((idx, val))
        return outliers

    def find_median_index(self, data: List[float], median_value: float) -> int:
        """找到最接近中位数的索引"""
        closest_index = 1
        min_diff = float('inf')

        for i, val in enumerate(data, start=1):
            diff = abs(val - median_value)
            if diff < min_diff:
                min_diff = diff
                closest_index = i

        return closest_index

    def save_important_indices(self, dataset_name: str, median_index: int, outlier_indices: List[int]):
        """保存重要索引到文件"""
        try:
            # 确保index_path是Path对象
            index_file = Path(index_path) if not isinstance(index_path, Path) else index_path

            # 确保目录存在
            index_file.parent.mkdir(parents=True, exist_ok=True)

            # 检查是否已经保存过这些索引
            median_key = f"{dataset_name}:median:{median_index}"
            if median_key not in self.saved_indices:
                with open(index_file, 'a', encoding='utf-8') as f:
                    f.write(f"{median_key}\n")
                self.saved_indices.add(median_key)

            for idx in outlier_indices:
                abnormal_key = f"{dataset_name}:abnormal:{idx}"
                if abnormal_key not in self.saved_indices:
                    with open(index_file, 'a', encoding='utf-8') as f:
                        f.write(f"{abnormal_key}\n")
                    self.saved_indices.add(abnormal_key)

        except Exception as e:
            logger.error(f"保存重要索引时出错: {e}")

    def create_single_boxplot(self, workstation_name: str, data: List[float]):
        """为单个工作站创建箱线图"""
        if not data:
            logger.warning(f"工作站 {workstation_name} 没有数据，跳过箱线图创建")
            self.single_boxplot_paths.append("")  # 添加空路径以保持顺序一致
            return None

        # 计算统计信息
        stats = self.calculate_statistics(data)
        outliers = self.find_extreme_indices(data, stats['lower_bound'], stats['upper_bound'])
        median_index = self.find_median_index(data, stats['median'])

        # 保存重要索引
        outlier_indices_list = [idx for idx, _ in outliers]
        self.save_important_indices(workstation_name, median_index, outlier_indices_list)

        # 创建图表
        plt.figure(figsize=(10, 7))
        ax = sns.boxplot(y=data, color='skyblue')

        # 设置标题和标签
        plt.title(f"Restore Time Distribution - {workstation_name}", fontsize=14, fontweight='bold')
        plt.ylabel("Restore Time (s)")

        # 设置横坐标标签
        ax.set_xticks([0])
        ax.set_xticklabels([workstation_name])

        # 高亮异常点并标注
        for idx, val in outliers:
            plt.plot(0, val, 'ro', markersize=8)
            plt.text(0.05, val, f"#{idx}: {val:.3f}",
                     color='red', fontsize=9, va='center')

        # 高亮中位数点并标注
        median_point_val = data[median_index - 1]
        plt.plot(0, median_point_val, 'bo', markersize=8, markeredgewidth=1, markeredgecolor='black')
        plt.text(0.05, median_point_val, f"Median #{median_index}: {median_point_val:.3f}",
                 color='blue', fontsize=10, va='center', fontweight='bold')

        # 添加统计信息框
        stats_lines = [
            f"Mean:         {stats['mean']:<8.2f} s",
            f"Median:       {stats['median']:<8.2f} s",
            f"Q1 (25%):     {stats['q1']:<8.2f} s",
            f"Q3 (75%):     {stats['q3']:<8.2f} s",
            f"IQR:          {stats['iqr']:<8.2f} s",
            f"Lower Bound:  {stats['lower_bound']:<8.2f} s",
            f"Upper Bound:  {stats['upper_bound']:<8.2f} s",
            f"Outliers:     {len(outliers):<8d}",
            f"Median Index: {median_index}"
        ]

        props = dict(boxstyle='round', facecolor='white', alpha=0.9)
        plt.gca().text(1.05, 0.5, '\n'.join(stats_lines),
                       transform=plt.gca().transAxes,
                       fontsize=10, va='center', bbox=props,
                       fontfamily='monospace')

        # 添加图例
        legend_elements = [
            Patch(facecolor='skyblue', edgecolor='blue', label='Boxplot'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=8, label='Outlier'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=8,
                       markeredgecolor='black', label='Median Point')
        ]
        plt.legend(handles=legend_elements, loc='upper right')

        # 调整布局
        plt.tight_layout()

        # 生成安全文件名
        safe_name = re.sub(r'[^\w\-]', '_', workstation_name)
        filename = self.output_dir / f"{safe_name}_boxplot.png"

        # 保存图表
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"箱线图已保存至: {filename}")
        self.single_boxplot_paths.append(str(filename))  # 保存单数据集箱线图路径
        return filename

    def create_multi_boxplot(self):
        """为多个工作站创建箱线图（从JSON文件读取数据）"""
        # 从JSON文件加载所有数据
        all_data = self.load_all_data_from_json()

        if not all_data:
            logger.warning("没有数据可用，跳过箱线图创建")
            return None

        # 准备数据
        data_list = []
        workstation_names = []

        # 遍历所有数据，确保只包含有数据的条目
        for name, data in all_data.items():
            if data:  # 只添加有数据的条目
                data_list.append(data)
                workstation_names.append(name)

        if len(data_list) < 2:
            logger.warning("少于2个数据集，跳过多数据集箱线图创建")
            return None

        # 创建图表
        plt.figure(figsize=(max(12, len(data_list) * 2), 6))
        ax = sns.boxplot(data=data_list, color='skyblue')

        plt.title("Multiple Restore Time Distributions", fontsize=14, fontweight='bold')
        plt.ylabel("Restore Time (s)")

        # 设置横坐标标签
        ax.set_xticks(range(len(data_list)))
        ax.set_xticklabels(workstation_names, rotation=45, ha='right')

        # 为每个数据集处理异常点和中位数点
        for i, (workstation_name, data) in enumerate([(name, data) for name, data in all_data.items() if data]):
            # 计算统计信息
            stats = self.calculate_statistics(data)
            outliers = self.find_extreme_indices(data, stats['lower_bound'], stats['upper_bound'])
            median_index = self.find_median_index(data, stats['median'])

            # 在图上标注异常点
            for idx, val in outliers:
                plt.plot(i, val, 'ro', markersize=8)
                plt.text(i + 0.05, val, f"#{idx}: {val:.3f}",
                         color='red', fontsize=9, va='center')

            # 高亮中位数点并标注
            median_point_val = data[median_index - 1]
            plt.plot(i, median_point_val, 'bo', markersize=12, markeredgewidth=1, markeredgecolor='black')
            plt.text(i + 0.05, median_point_val, f"#{median_index}: {median_point_val:.3f}",
                     color='blue', fontsize=10, va='center', fontweight='bold')

        # 添加图例
        legend_elements = [
            Patch(facecolor='skyblue', edgecolor='blue', label='Boxplot'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=8, label='Outlier'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=12,
                       markeredgecolor='black', label='Median Point')
        ]
        plt.legend(handles=legend_elements, loc='upper right')

        # 调整布局
        plt.tight_layout()

        # 保存图表
        filename = self.output_dir / "multi_boxplot.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"多数据集箱线图已保存至: {filename}")
        self.multi_boxplot_path = str(filename)  # 保存多数据集箱线图路径
        return filename

    def update_metadata_json(self):
        """将箱线图路径写入metadata.json文件"""
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

            # 更新当前工作站的箱线图路径
            if workstation_name in metadata:
                # 确保path字段存在
                if "path" not in metadata[workstation_name]:
                    metadata[workstation_name]["path"] = {}

                # 设置单数据集箱线图路径
                if self.single_boxplot_paths:
                    metadata[workstation_name]["path"]["boxplot"] = self.single_boxplot_paths[0]

            # 写回文件
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"已更新metadata.json中的箱线图路径: {metadata_path}")

        except Exception as e:
            logger.error(f"更新metadata.json时出错: {e}")

    def generate_boxplots(self, multi_plot: bool = True):
        """生成箱线图"""
        # 清空已保存的索引集合
        self.saved_indices.clear()
        # 重置图表路径列表
        self.single_boxplot_paths = []
        self.multi_boxplot_path = None

        # 加载工作站数据
        workstation_data = self.load_workstation_data()

        if not workstation_data:
            logger.error("未找到任何工作站数据")
            return []

        # 为当前工作站创建箱线图
        boxplot_files = []
        for workstation_name, data in workstation_data.items():
            boxplot_file = self.create_single_boxplot(workstation_name, data)
            if boxplot_file:
                boxplot_files.append(boxplot_file)

        # 创建多数据集箱线图（从JSON文件读取数据）
        if multi_plot:
            multi_boxplot_file = self.create_multi_boxplot()
            if multi_boxplot_file:
                boxplot_files.append(multi_boxplot_file)

        # 所有图表生成完毕后，更新metadata.json
        self.update_metadata_json()

        logger.info(f"成功生成 {len(boxplot_files)} 个箱线图")
        return boxplot_files


def main():
    """主函数"""
    try:
        # 创建箱线图生成器
        boxplot_generator = BoxPlotGenerator()

        # 生成箱线图
        boxplot_files = boxplot_generator.generate_boxplots()

        if boxplot_files:
            print(f"\n成功生成 {len(boxplot_files)} 个箱线图:")
            for boxplot_file in boxplot_files:
                print(f"  - {boxplot_file}")
        else:
            print("未生成任何箱线图")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == "__main__":
    main()