import sys
import os
import subprocess
import logging
import shutil
import json
import re
from pathlib import Path
from typing import Dict, Any
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QPushButton, QTextEdit, QFileDialog,
                             QProgressBar, QMessageBox, QGroupBox, QTabWidget,
                             QLineEdit, QFormLayout, QScrollArea, QSplitter, QFrame,
                             QDialog, QDialogButtonBox, QSpinBox, QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QFont

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 常量定义
DEFAULT_METADATA = {
    "Test Name": "Restore Loop Test",
    "Test Date": "2025-08-15",
    "Tester": "William",
    "Number of Workstations": "1",
    "DUT per Workstation": "1",
    "Loops per DUT": "19",
    "Restore Tool Version": "PurpleRabbit",
    "Remark": "NULL"
}

DEFAULT_WORKSTATION = {
    "Host Info": "J274_14.4.1_16G_256G",
    "Cable Info": "Spartan-FW: 1.11.3",
    "DUT Model": "Zonda (P1BU) 48GB_2T",
    "Variant": "Factory-Software Download",
    "Bundle Version": "CheerEAmber25E40600u",
    "Loop #": "19",
    "Restore Status": "0/19T",
    "Folder Name": "logs_0u"
}

FIELD_ORDER = ["Host Info", "DUT Model", "Bundle Version", "Restore Status", "Cable Info", "Variant", "Loop #",
               "Folder Name"]


class DraggableLineEdit(QLineEdit):
    """支持拖放的文件路径输入框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            # 获取第一个文件的路径
            file_path = urls[0].toLocalFile()
            self.setText(file_path)
            event.acceptProposedAction()


class JSONEditorWindow(QDialog):
    """JSON 数据编辑器窗口"""

    def __init__(self, script_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JSON 数据编辑器")
        self.setGeometry(100, 100, 1000, 700)
        self.file_path = "info.json"
        self.script_dir = script_dir  # 存储脚本目录
        self.data = {}
        self.original_data = {}
        self.field_widgets = {}
        self.workstation_tabs = None

        self.init_ui()
        self.load_data()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)

        # 标题
        title_label = QLabel("JSON 数据编辑器")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 创建选项卡控件
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 创建元数据选项卡
        self.metadata_tab = QWidget()
        self.metadata_layout = QFormLayout(self.metadata_tab)
        self.tab_widget.addTab(self.metadata_tab, "Metadata 数据")

        # 创建工作站数据选项卡
        self.workstation_tab = QWidget()
        self.workstation_layout = QVBoxLayout(self.workstation_tab)
        self.tab_widget.addTab(self.workstation_tab, "工作站数据")

        # 按钮布局
        button_layout = QHBoxLayout()

        self.reset_button = QPushButton("重置更改")
        self.reset_button.clicked.connect(self.reset_data)
        button_layout.addWidget(self.reset_button)

        self.save_button = QPushButton("保存更改")
        self.save_button.clicked.connect(self.save_data)
        self.save_button.setDefault(True)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def load_data(self):
        """加载JSON数据"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
                self.original_data = json.loads(json.dumps(self.data))  # 深度拷贝

                # 确保数据结构正确
                if "metadata_dict" not in self.data:
                    self.data["metadata_dict"] = DEFAULT_METADATA.copy()

                self.populate_metadata()
                self.populate_workstations()

        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或格式错误，创建默认结构
            self.data = {"metadata_dict": DEFAULT_METADATA.copy()}
            self.original_data = json.loads(json.dumps(self.data))
            self.populate_metadata()

    def populate_metadata(self):
        """填充元数据表单"""
        # 清除现有内容
        for i in reversed(range(self.metadata_layout.count())):
            self.metadata_layout.itemAt(i).widget().setParent(None)

        metadata_dict = self.data["metadata_dict"]
        self.field_widgets["metadata"] = {}

        for key, value in metadata_dict.items():
            line_edit = QLineEdit(str(value))
            self.field_widgets["metadata"][key] = line_edit
            self.metadata_layout.addRow(f"{key}:", line_edit)

    def populate_workstations(self):
        """填充工作站数据"""
        # 清除现有内容
        for i in reversed(range(self.workstation_layout.count())):
            widget = self.workstation_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # 获取工作站数量
        try:
            num_workstations = int(self.data["metadata_dict"].get("Number of Workstations", "1"))
            num_workstations = max(1, num_workstations)  # 确保至少有一个工作站
        except (ValueError, TypeError):
            num_workstations = 1

        # 同步工作站数量
        self.sync_workstation_count(num_workstations)

        # 获取所有工作站键
        ws_keys = self.get_workstation_keys()

        if not ws_keys:
            label = QLabel("没有工作站数据。请设置 'Number of Workstations' 字段。")
            self.workstation_layout.addWidget(label)
            return

        # 创建工作站选项卡
        self.workstation_tabs = QTabWidget()
        self.workstation_layout.addWidget(self.workstation_tabs)

        self.field_widgets["workstations"] = {}

        for ws_key in ws_keys:
            ws_tab = QWidget()
            ws_layout = QFormLayout(ws_tab)

            ws_data = self.data[ws_key].copy()

            # 确保所有字段都存在
            for field in FIELD_ORDER:
                if field not in ws_data:
                    ws_data[field] = ""

            self.field_widgets["workstations"][ws_key] = {}

            for field in FIELD_ORDER:
                if field == "Folder Name":
                    # 为 Folder Name 字段使用可拖放的文件路径输入框
                    line_edit = DraggableLineEdit()
                    line_edit.setPlaceholderText("拖放文件或文件夹到这里...")
                else:
                    line_edit = QLineEdit()

                line_edit.setText(str(ws_data[field]))
                self.field_widgets["workstations"][ws_key][field] = line_edit
                ws_layout.addRow(f"{field}:", line_edit)

            self.workstation_tabs.addTab(ws_tab, ws_key)

    def get_workstation_keys(self):
        """获取排序后的工作站键列表"""
        ws_keys = [key for key in self.data.keys() if key.startswith("WS-")]
        # 按数字排序
        ws_keys.sort(key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
        return ws_keys

    def sync_workstation_count(self, target_count):
        """同步工作站数量到目标值"""
        ws_keys = self.get_workstation_keys()
        current_count = len(ws_keys)

        if current_count < target_count:
            # 添加缺少的工作站
            for i in range(current_count + 1, target_count + 1):
                ws_key = f"WS-{i}"
                if ws_key not in self.data:
                    self.data[ws_key] = DEFAULT_WORKSTATION.copy()
        elif current_count > target_count:
            # 删除多余的工作站
            for i in range(current_count, target_count, -1):
                ws_key = f"WS-{i}"
                if ws_key in self.data:
                    del self.data[ws_key]

    def reset_data(self):
        """重置数据到原始状态"""
        self.data = json.loads(json.dumps(self.original_data))
        self.populate_metadata()
        self.populate_workstations()

    def generate_metadata(self):
        """生成metadata.json文件"""
        try:
            # 构建generate_metadata.py脚本的完整路径
            generate_script = os.path.join(self.script_dir, "generate_metadata.py")

            # 运行generate_metadata.py脚本
            result = subprocess.run(
                [sys.executable, generate_script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd()  # 在工作目录下运行
            )

            if result.returncode == 0:
                logger.info("成功生成metadata.json")
                return True
            else:
                logger.error(f"生成metadata.json失败: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("生成metadata.json超时")
            return False
        except Exception as e:
            logger.error(f"生成metadata.json时发生异常: {str(e)}")
            return False

    def save_data(self):
        """保存数据到JSON文件"""
        # 更新元数据
        for key, widget in self.field_widgets["metadata"].items():
            self.data["metadata_dict"][key] = widget.text()

        # 更新工作站数据
        if "workstations" in self.field_widgets:
            for ws_key, fields in self.field_widgets["workstations"].items():
                for field, widget in fields.items():
                    self.data[ws_key][field] = widget.text()

        # 处理特殊值
        metadata = self.data["metadata_dict"]
        if metadata.get("Remark") == "":
            metadata["Remark"] = "NULL"
        if metadata.get("Test Date") == "":
            metadata["Test Date"] = "2025-08-15"

        # 保存到文件
        try:
            Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

            self.original_data = json.loads(json.dumps(self.data))  # 更新原始数据

            # 检查工作站数量是否变化，如果是则刷新工作站选项卡
            old_num_workstations = len(self.get_workstation_keys())
            new_num_workstations = int(self.data["metadata_dict"].get("Number of Workstations", "1"))

            if old_num_workstations != new_num_workstations:
                self.populate_workstations()

            # 生成metadata.json
            metadata_success = self.generate_metadata()

            if metadata_success:
                QMessageBox.information(self, "成功", "数据已成功保存并生成metadata.json！")
            else:
                QMessageBox.warning(self, "警告", "数据已保存，但生成metadata.json时出现问题。")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存数据失败: {str(e)}")


class ScriptRunnerThread(QThread):
    """脚本运行线程，用于按顺序执行脚本"""
    progress = pyqtSignal(int, str)  # 进度百分比, 当前步骤描述
    finished = pyqtSignal(bool, str)  # 成功标志, 完成消息
    error = pyqtSignal(str)  # 错误消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scripts = [
            ("提取循环时间数据", "getCycleTime.py"),
            ("生成折线图", "lineChart.py"),
            ("生成箱线图", "boxPlot.py"),
            ("处理日志文件", "sortCycletime.py"),
            ("比较最小最大值", "compare_min_max.py"),
            ("生成excel", "forExcel.py")
        ]
        # 设置脚本目录
        self.script_dir = os.path.join(os.path.dirname(__file__), "src", "package")

    def run_script_for_workstation(self, script_name, description, folder_path, workstation_name):
        """为特定工作站运行单个Python脚本"""
        self.progress.emit(0, f"开始为 {workstation_name} {description}...")
        try:
            # 使用当前Python解释器运行脚本
            script_path = os.path.join(self.script_dir, script_name)

            # 设置环境变量，传递文件夹路径和工作站名称
            env = os.environ.copy()
            env['FOLDER_PATH'] = folder_path
            env['WORKSTATION_NAME'] = workstation_name

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                cwd=self.script_dir,  # 设置工作目录为脚本所在目录
                env=env  # 传递环境变量
            )

            if result.returncode != 0:
                error_msg = f"{workstation_name} {description}执行失败: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg

            logger.info(f"{workstation_name} {description}执行成功")
            return True, f"{workstation_name} {description}完成"

        except subprocess.TimeoutExpired:
            error_msg = f"{workstation_name} {description}执行超时"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"{workstation_name} {description}执行异常: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def run(self):
        """主运行方法"""
        try:
            # 清空 extracted_data 文件夹
            extracted_dir = Path("extracted_data")
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
            extracted_dir.mkdir(parents=True, exist_ok=True)
            # 加载工作站信息
            info_path = "info.json"
            if not os.path.exists(info_path):
                self.error.emit("找不到 info.json 文件")
                return

            with open(info_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 获取所有工作站INFO_JSON_PATH
            ws_keys = [key for key in data.keys() if key.startswith("WS-")]
            if not ws_keys:
                self.error.emit("没有配置工作站数据")
                return

            total_workstations = len(ws_keys)
            total_steps = len(self.scripts) * total_workstations

            current_step = 0

            # 为每个工作站执行所有脚本
            for ws_index, ws_key in enumerate(ws_keys):
                ws_data = data[ws_key]
                folder_name = ws_data.get("Folder Name", "")

                if not folder_name or not os.path.exists(folder_name):
                    self.error.emit(f"{ws_key} 的 Folder Name 不存在或未设置")
                    return

                # 为当前工作站执行所有脚本
                for script_index, (description, script_name) in enumerate(self.scripts):
                    current_step = ws_index * len(self.scripts) + script_index
                    progress_percent = int((current_step + 1) / total_steps * 100)

                    self.progress.emit(progress_percent, f"开始为 {ws_key} {description}...")

                    success, message = self.run_script_for_workstation(
                        script_name, description, folder_name, ws_key
                    )

                    if not success:
                        self.error.emit(message)
                        return

                    self.progress.emit(progress_percent, message)

            # 所有步骤执行成功
            self.finished.emit(True, "所有脚本执行完成！")

        except Exception as e:
            error_msg = f"执行过程中发生未知错误: {str(e)}"
            logger.error(error_msg)
            self.error.emit(error_msg)


class MainControllerWindow(QMainWindow):
    """主控制窗口"""

    def __init__(self):
        super().__init__()
        self.script_dir = os.path.join(os.path.dirname(__file__), "src", "package")
        self.init_ui()
        self.worker_thread = None

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("循环时间分析工具 - 主控制器")
        self.setGeometry(100, 100, 800, 600)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        layout = QVBoxLayout(central_widget)

        # 标题
        title_label = QLabel("循环时间分析工具")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        # 说明文本
        info_label = QLabel(
            "本工具用于分析循环时间数据。请先配置JSON数据，然后点击\"执行\"按钮开始处理。\n"
            "处理过程包括：按工作站提取循环时间数据、生成图表、处理日志文件和比较最小最大值。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        layout.addWidget(info_label)

        # 按钮区域
        button_layout = QHBoxLayout()

        # JSON编辑器按钮
        self.json_editor_button = QPushButton("打开JSON编辑器")
        self.json_editor_button.clicked.connect(self.open_json_editor)
        button_layout.addWidget(self.json_editor_button)

        self.execute_button = QPushButton("执行")
        self.execute_button.clicked.connect(self.execute_scripts)
        button_layout.addWidget(self.execute_button)

        layout.addLayout(button_layout)

        # 进度区域
        progress_group = QGroupBox("执行进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("padding: 5px;")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

        # 输出区域
        output_group = QGroupBox("输出信息")
        output_layout = QVBoxLayout(output_group)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        output_layout.addWidget(self.output_text)

        layout.addWidget(output_group)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def open_json_editor(self):
        """打开JSON编辑器"""
        self.editor = JSONEditorWindow(self.script_dir, self)
        self.editor.exec_()

    def execute_scripts(self):
        """执行脚本序列"""
        # 检查脚本文件是否存在
        missing_scripts = []
        scripts = ["getCycleTime.py", "lineChart.py", "boxPlot.py", "sortCycletime.py", "compare_min_max.py",
                   "forExcel.py"]

        for script in scripts:
            script_path = os.path.join(self.script_dir, script)
            if not Path(script_path).exists():
                missing_scripts.append(script)

        if missing_scripts:
            QMessageBox.critical(
                self,
                "错误",
                f"找不到以下脚本文件:\n{', '.join(missing_scripts)}\n请确保所有脚本文件都在 {self.script_dir} 目录下。"
            )
            return

        # 检查info.json是否存在
        if not os.path.exists("info.json"):
            QMessageBox.critical(
                self,
                "错误",
                "找不到 info.json 文件，请先配置JSON数据。"
            )
            return

        # 禁用按钮，显示进度条
        self.json_editor_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.output_text.clear()

        # 创建工作线程
        self.worker_thread = ScriptRunnerThread(self)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.finished.connect(self.on_execution_finished)
        self.worker_thread.error.connect(self.on_execution_error)
        self.worker_thread.start()

    def update_progress(self, percent, message):
        """更新进度"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self.output_text.append(message)
        self.statusBar().showMessage(message)

    def on_execution_finished(self, success, message):
        """执行完成"""
        # 启用按钮
        self.json_editor_button.setEnabled(True)
        self.execute_button.setEnabled(True)

        self.output_text.append(message)
        self.statusBar().showMessage(message)
        self.status_label.setText(message)

        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "完成", message)

    def on_execution_error(self, error_msg):
        """执行错误"""
        # 启用按钮
        self.json_editor_button.setEnabled(True)
        self.execute_button.setEnabled(True)

        self.output_text.append(f"错误: {error_msg}")
        self.statusBar().showMessage(f"错误: {error_msg}")
        self.status_label.setText("执行失败")
        QMessageBox.critical(self, "错误", error_msg)


def main():
    """主函数"""

    app = QApplication(sys.argv)
    window = MainControllerWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()