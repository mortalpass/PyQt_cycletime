import json
import logging
from pathlib import Path
from datetime import datetime
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
    from config import output_form, output_img, PROJECT_ROOT
except ImportError:
    logger.error("无法导入配置模块，请确保 config.py 存在")
    raise


class MetadataGenerator:
    """元数据生成器类，用于根据info.json生成metadata.json"""

    def __init__(self, info_path: str, output_dir: str = output_form):
        self.info_path = Path(info_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.output_dir / "metadata.json"

    def load_info_json(self) -> dict:
        """加载info.json文件"""
        if not self.info_path.exists():
            logger.error(f"info.json文件不存在: {self.info_path}")
            return {}

        try:
            with open(self.info_path, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
            logger.info(f"成功加载info.json文件")
            return info_data
        except Exception as e:
            logger.error(f"加载info.json文件时出错: {e}")
            return {}

    def create_metadata_structure(self, info_data: dict) -> dict:
        """根据info.json创建metadata.json的基本结构"""
        metadata = {}

        # 复制metadata_dict
        if "metadata_dict" in info_data:
            metadata["metadata_dict"] = info_data["metadata_dict"]

            # 确保Test Date字段是完整的时间格式
            if "Test Date" in metadata["metadata_dict"]:
                test_date = metadata["metadata_dict"]["Test Date"]
                if len(test_date) == 10:  # 只有日期部分
                    metadata["metadata_dict"]["Test Date"] = f"{test_date} 00:00:00"

        # 处理每个工作站
        workstation_keys = [key for key in info_data.keys() if key.startswith("WS-")]
        for ws_key in workstation_keys:
            metadata[ws_key] = info_data[ws_key].copy()

            # 添加统计字段（初始为空）
            metadata[ws_key]["Median Times(s)"] = ""
            metadata[ws_key]["Avg Time(s)"] = ""
            metadata[ws_key]["Min Time(s)"] = ""
            metadata[ws_key]["Max Time(s)"] = ""
            metadata[ws_key]["Range(s)"] = ""
            metadata[ws_key]["Std(s)"] = ""
            metadata[ws_key]["Outlier Count"] = ""
            metadata[ws_key]["Remark"] = ""

            # 添加路径字段
            metadata[ws_key]["path"] = {
                "linechart": "",
                "boxplot": ""
            }

        # 添加全局note
        metadata[
            "note"] = "Outliers are determined based on the boxplot method, where a data point is considered an outlier if it is greater than Q3 + 1.5×IQR or less than Q1 - 1.5×IQR."

        # 添加全局路径
        metadata["path"] = {
            "boxplot": str(Path(output_img) / "multi_boxplot.png"),
            "form": str(self.metadata_path),
            "json": str(self.metadata_path)
        }

        return metadata

    def generate_metadata(self):
        """生成metadata.json文件"""
        # 加载info.json
        info_data = self.load_info_json()
        if not info_data:
            return False

        # 创建metadata结构
        metadata = self.create_metadata_structure(info_data)

        # 保存metadata.json
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logger.info(f"metadata.json已成功生成: {self.metadata_path}")
            return True
        except Exception as e:
            logger.error(f"保存metadata.json时出错: {e}")
            return False


def main():
    """主函数"""
    try:
        # 从环境变量获取info.json路径，或使用默认路径
        info_path = os.path.join(PROJECT_ROOT, 'info.json')
        print(info_path)

        # 创建元数据生成器
        generator = MetadataGenerator(info_path)

        # 生成metadata.json
        success = generator.generate_metadata()

        if success:
            logger.info("metadata.json生成完成!")
        else:
            logger.error("metadata.json生成失败!")

    except Exception as e:
        logger.exception(f"处理过程中发生严重错误: {e}")


if __name__ == "__main__":
    main()