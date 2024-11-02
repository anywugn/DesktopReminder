import sys
import json
import os
import winreg
from datetime import datetime, timedelta
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QCheckBox, QPushButton, QSystemTrayIcon, QMenu, QAction, QTimeEdit, QHBoxLayout
from PyQt5.QtGui import QIcon, QColor, QPainter, QBrush
from PyQt5.QtCore import QTime, QTimer, Qt, QPoint


# 获取打包后运行的文件路径
def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class DesktopReminderWidget(QWidget):
            

    def __init__(self):
        super().__init__()
        self.setWindowTitle("每日提醒器")
        self.setGeometry(100, 100, 400, 550)  # 默认窗口大小
        
        # 设置窗口样式
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)  # 设置窗口为透明背景
        self.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 150);
                border-radius: 15px;
                font-family: 'Microsoft YaHei';
                font-size: 20px;
                color: white;
            }
            QCheckBox {
                font-size: 20px;
                color: white;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 5px;
            }
            QCheckBox::indicator:checked {
                background-color: #4caf50;
            }
            QCheckBox::indicator:unchecked {
                background-color: #ccc;
            }
            QPushButton {
                font-size: 20px;
                color: white;
                background-color: #4caf50;
                border-radius: 10px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QTimeEdit {
                font-size: 20px;
                color: white;
            }
        """)

        # 载入上次窗口位置
        self.load_window_position()

        self.layout = QVBoxLayout()
        
        # 初始化托盘图标
        self.tray_icon = QSystemTrayIcon(QIcon(resource_path("icon.png")), self)
        self.tray_icon.setToolTip("每日提醒器正在运行")
        self.tray_icon.activated.connect(self.toggle_visibility)  # 绑定点击事件


        # 创建托盘菜单
        tray_menu = QMenu()
        
        # 添加开机启动选项
        self.auto_start_action = QAction("开机启动", self, checkable=True)
        self.auto_start_action.setChecked(self.is_auto_start_enabled())
        self.auto_start_action.triggered.connect(self.toggle_auto_start)
        tray_menu.addAction(self.auto_start_action)

        # 退出选项
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close_application)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # 读取任务和重置时间
        self.tasks = self.load_tasks()
        self.task_checkboxes = []

        # 初始化任务与重置时间
        for task, task_data in self.tasks.items():
            task_layout = QHBoxLayout()
            checkbox = QCheckBox(task)
            checkbox.setChecked(task_data["completed"])
            checkbox.stateChanged.connect(self.save_tasks)
            self.task_checkboxes.append(checkbox)
            task_layout.addWidget(checkbox)

            # 设置重置时间编辑框
            reset_time_edit = QTimeEdit()
            reset_time_edit.setDisplayFormat("HH:mm")
            reset_time_edit.setTime(QTime.fromString(task_data["reset_time"], "HH:mm"))
            reset_time_edit.timeChanged.connect(lambda time, t=task: self.update_reset_time(t, time))
            task_layout.addWidget(reset_time_edit)

            # 设置重置时间显示为文字
            #reset_time_label = QLabel(task_data["reset_time"])  # 显示重置时间的标签
            #reset_time_label.setAlignment(Qt.AlignCenter)  # 设置居中对齐
            #reset_time_label.setStyleSheet("font-size: 20px; color: white;")  # 设置样式
            #task_layout.addWidget(reset_time_label)


            self.layout.addLayout(task_layout)
        
        # 添加完成按钮
        self.complete_button = QPushButton("完成所有任务")
        self.complete_button.clicked.connect(self.complete_all_tasks)
        self.layout.addWidget(self.complete_button)
        
        # 启动时检查并重置过期任务状态
        self.reset_overdue_tasks()

        # 设置定时器来每分钟检查任务状态
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_and_reset_tasks)
        self.timer.start(60000)  # 每分钟检查一次
        self.setLayout(self.layout)

        # 初始化移动相关参数
        self.dragging = False
        self.drag_position = QPoint()

    def toggle_visibility(self, reason):
        """切换窗口显示和隐藏状态"""
        if reason == QSystemTrayIcon.Trigger:  # 仅响应单击事件
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()  # 确保窗口在最上层显示

    def toggle_auto_start(self):
        """切换开机启动状态"""
        if self.auto_start_action.isChecked():
            self.enable_auto_start()
        else:
            self.disable_auto_start()

    def enable_auto_start(self):
        """在注册表中添加启动项"""
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        exe_path = os.path.abspath(sys.argv[0])
        winreg.SetValueEx(key, "DesktopReminder", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)

    def disable_auto_start(self):
        """从注册表中删除启动项"""
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "DesktopReminder")
        except FileNotFoundError:
            pass  # 如果不存在，不处理
        winreg.CloseKey(key)

    def is_auto_start_enabled(self):
        """检查启动项是否已添加"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "DesktopReminder")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        
    def load_tasks(self):
        try:
            with open("tasks.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                for task, task_data in data.items():
                    if "reset_time" not in task_data:
                        task_data["reset_time"] = "00:00"
                    if "last_completed_datetime" not in task_data:
                        task_data["last_completed_datetime"] = ""  # 初始化为空
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "任务1": {"completed": False, "reset_time": "00:00", "last_completed_datetime": ""},
                "任务2": {"completed": False, "reset_time": "00:00", "last_completed_datetime": ""},
                "任务3": {"completed": False, "reset_time": "00:00", "last_completed_datetime": ""}
            }
    
    def save_tasks(self):
        """仅在任务状态或时间变化时保存任务"""
        tasks_to_save = False  # 标记是否需要保存
        for checkbox in self.task_checkboxes:
            task_name = checkbox.text()
            current_state = checkbox.isChecked()

            # 检查状态或完成时间是否实际发生了变化
            if self.tasks[task_name]["completed"] != current_state:
                self.tasks[task_name]["completed"] = current_state
                if current_state:
                    # 如果任务完成，更新完成时间
                    self.tasks[task_name]["last_completed_datetime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # 否则，清空完成时间
                    self.tasks[task_name]["last_completed_datetime"] = ""
                tasks_to_save = True  # 状态有变化，需要保存

        # 仅在状态有变化时保存文件
        if tasks_to_save:
            with open("tasks.json", "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False)

    def update_reset_time(self, task_name, time):
        """仅在重置时间实际更改时更新并保存"""
        new_reset_time = time.toString("HH:mm")
        # 检查重置时间是否变化
        if self.tasks[task_name]["reset_time"] != new_reset_time:
            self.tasks[task_name]["reset_time"] = new_reset_time
            with open("tasks.json", "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False)

    def reset_overdue_tasks(self):
        """重置过期任务，仅在任务状态被修改时保存"""
        current_time = datetime.now()
        tasks_to_save = False
        for checkbox in self.task_checkboxes:
            task_name = checkbox.text()
            task_data = self.tasks[task_name]
            reset_time = datetime.strptime(task_data["reset_time"], "%H:%M").time()
            last_completed_datetime = task_data.get("last_completed_datetime", "")

            if last_completed_datetime:
                last_completed_time = datetime.strptime(last_completed_datetime, "%Y-%m-%d %H:%M:%S")
                reset_datetime = last_completed_time.replace(hour=reset_time.hour, minute=reset_time.minute)

                if last_completed_time <= reset_datetime:
                    reset_datetime = reset_datetime - timedelta(days=1)

                if current_time >= reset_datetime + timedelta(days=1):
                    checkbox.setChecked(False)
                    task_data["completed"] = False
                    task_data["last_completed_datetime"] = ""
                    tasks_to_save = True  # 标记需要保存

        if tasks_to_save:  # 仅在有变化时保存
            self.save_tasks()

    def check_and_reset_tasks(self):
        """每分钟检查并重置，仅在任务状态被修改时保存"""
        current_time = datetime.now()
        tasks_to_save = False
        for checkbox in self.task_checkboxes:
            task_name = checkbox.text()
            reset_time = datetime.strptime(self.tasks[task_name]["reset_time"], "%H:%M").time()
            last_completed_datetime = self.tasks[task_name].get("last_completed_datetime", "")

            if last_completed_datetime:
                last_completed_time = datetime.strptime(last_completed_datetime, "%Y-%m-%d %H:%M:%S")
                reset_datetime = last_completed_time.replace(hour=reset_time.hour, minute=reset_time.minute)

                if last_completed_time <= reset_datetime:
                    reset_datetime = reset_datetime - timedelta(days=1)

                if current_time >= reset_datetime + timedelta(days=1):
                    checkbox.setChecked(False)
                    self.tasks[task_name]["completed"] = False
                    self.tasks[task_name]["last_completed_datetime"] = ""
                    tasks_to_save = True  # 标记需要保存

        if tasks_to_save:  # 仅在有变化时保存
            self.save_tasks()




    def complete_all_tasks(self):
        for checkbox in self.task_checkboxes:
            checkbox.setChecked(True)
        self.save_tasks()


    def close_application(self):
        # 记录窗口位置
        self.save_window_position()
        self.tray_icon.hide()  # 关闭时隐藏托盘图标
        QApplication.quit()

    def save_window_position(self):
        position = {"x": self.x(), "y": self.y()}
        with open("window_position.json", "w") as f:
            json.dump(position, f)

    def load_window_position(self):
        try:
            with open("window_position.json", "r") as f:
                position = json.load(f)
                self.move(position["x"], position["y"])
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # 如果文件不存在或格式不对，则忽略

    # 实现窗口移动
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()

    # 绘制毛玻璃效果
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 15, 15)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = DesktopReminderWidget()
    widget.show()
    sys.exit(app.exec_())
