#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🍅 番茄钟 (Pomodoro Timer) - 桌面番茄钟应用
基于 Python + tkinter 构建，无需额外依赖
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import threading
from pathlib import Path

# winsound 仅在 Windows 上可用
try:
    import winsound
except ImportError:
    winsound = None

# ============================================================
# 配置文件路径
# ============================================================
SETTINGS_FILE = Path(__file__).parent / "pomodoro_settings.json"


# ============================================================
# PomodoroTimer 主类
# ============================================================
class PomodoroTimer:
    """番茄钟主类"""

    # 默认设置
    DEFAULT_SETTINGS = {
        "work_duration": 25,          # 工作时间（分钟）
        "short_break_duration": 5,    # 短休息时间（分钟）
        "long_break_duration": 15,    # 长休息时间（分钟）
        "sessions_before_long": 4,    # 多少次工作后进入长休息
        "always_on_top": False,
        "sound_enabled": True,
    }

    # 模式常量
    MODE_WORK       = "work"
    MODE_SHORT_BREAK = "short_break"
    MODE_LONG_BREAK  = "long_break"

    # 模式显示名称
    MODE_LABELS = {
        MODE_WORK:        "🍅 工作中",
        MODE_SHORT_BREAK: "☕ 短休息",
        MODE_LONG_BREAK:  "🌴 长休息",
    }

    # 模式主题色
    MODE_COLORS = {
        MODE_WORK:        "#E74C3C",  # 番茄红 — 专注
        MODE_SHORT_BREAK: "#2ECC71",  # 薄荷绿 — 放松
        MODE_LONG_BREAK:  "#3498DB",  # 天空蓝 — 深度休息
    }

    # ============================================================
    # 初始化 & 配置持久化
    # ============================================================
    def __init__(self):
        self.settings = self._load_settings()

        # ----- 主窗口 -----
        self.root = tk.Tk()
        self.root.title("🍅 番茄钟")
        self.root.geometry("420x500")
        self.root.minsize(360, 440)
        self.root.configure(bg="#F5F0EB")  # 暖白背景

        # 关闭窗口行为
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 初始状态
        self.current_mode      = self.MODE_WORK
        self._reset_timer_for_mode(self.current_mode)
        self.completed_sessions = 0
        self.is_running         = False
        self.is_paused          = False
        self.timer_id           = None

        # 始终置顶
        self._apply_always_on_top()

        # 构建 UI
        self._setup_ui()
        self._update_display()

    # ----------------------------------------------------------
    # 设置文件读写
    # ----------------------------------------------------------
    def _load_settings(self) -> dict:
        """从 JSON 文件加载设置，文件不存在时使用默认值"""
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                # 合并默认值，防止旧配置文件缺少新字段
                merged = {**self.DEFAULT_SETTINGS, **data}
                return merged
        except (json.JSONDecodeError, OSError):
            pass
        return dict(self.DEFAULT_SETTINGS)

    def _save_settings(self):
        """保存设置到 JSON 文件"""
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self.settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ----------------------------------------------------------
    # 辅助
    # ----------------------------------------------------------
    def _reset_timer_for_mode(self, mode: str):
        """根据模式设置 remaining_seconds 和 total_seconds"""
        if mode == self.MODE_WORK:
            minutes = self.settings["work_duration"]
        elif mode == self.MODE_SHORT_BREAK:
            minutes = self.settings["short_break_duration"]
        else:
            minutes = self.settings["long_break_duration"]
        self.remaining_seconds = minutes * 60
        self.total_seconds     = self.remaining_seconds

    def _apply_always_on_top(self):
        self.root.attributes("-topmost", self.settings["always_on_top"])

    # ============================================================
    # UI 构建
    # ============================================================
    def _setup_ui(self):
        """构建全部界面组件"""
        root = self.root
        bg   = "#F5F0EB"

        # ---- 顶部标题 ----
        self.title_label = tk.Label(
            root, text="🍅 番茄钟", font=("Microsoft YaHei", 18, "bold"),
            bg=bg, fg="#2C3E50",
        )
        self.title_label.pack(pady=(20, 8))

        # ---- 计时器圆形区域 ----
        timer_frame = tk.Frame(root, bg=bg)
        timer_frame.pack(pady=(4, 6))

        # Canvas 画圆形背景
        self.canvas_size = 220
        self.timer_canvas = tk.Canvas(
            timer_frame, width=self.canvas_size, height=self.canvas_size,
            bg=bg, highlightthickness=0,
        )
        self.timer_canvas.pack()

        # 圆形背景
        self.timer_bg_circle = self._create_circle(
            self.canvas_size / 2, self.canvas_size / 2,
            95, fill="#FFFFFF", outline="#E0D6CC", width=3,
        )

        # 进度圆弧（动态更新）
        self.progress_arc = None

        # 时间文字（放在 Canvas 中央）
        self.time_text = self.timer_canvas.create_text(
            self.canvas_size / 2, self.canvas_size / 2 - 6,
            text="25:00", font=("Consolas", 42, "bold"),
            fill="#2C3E50",
        )

        # 百分比文字
        self.percent_text = self.timer_canvas.create_text(
            self.canvas_size / 2, self.canvas_size / 2 + 36,
            text="100%", font=("Microsoft YaHei", 12),
            fill="#7F8C8D",
        )

        # ---- 模式标签 ----
        self.mode_label = tk.Label(
            root, text=self.MODE_LABELS[self.current_mode],
            font=("Microsoft YaHei", 13, "bold"),
            bg=bg, fg=self.MODE_COLORS[self.current_mode],
        )
        self.mode_label.pack(pady=(4, 2))

        # ---- 会话计数 ----
        self.session_label = tk.Label(
            root, text="第 1 个番茄钟",
            font=("Microsoft YaHei", 10),
            bg=bg, fg="#7F8C8D",
        )
        self.session_label.pack(pady=(0, 6))

        # ---- 番茄进度点 ----
        self.dots_frame = tk.Frame(root, bg=bg)
        self.dots_frame.pack(pady=(0, 8))
        self.session_dots = []
        for i in range(self.settings["sessions_before_long"]):
            dot = tk.Label(
                self.dots_frame, text="○", font=("Arial", 16),
                bg=bg, fg="#D5C8B5",
            )
            dot.pack(side=tk.LEFT, padx=4)
            self.session_dots.append(dot)

        # ---- 控制按钮 ----
        btn_frame = tk.Frame(root, bg=bg)
        btn_frame.pack(pady=(2, 8))

        btn_style = {
            "font": ("Microsoft YaHei", 11, "bold"),
            "relief": "flat", "borderwidth": 0,
            "padx": 20, "pady": 8, "cursor": "hand2",
        }

        self.start_btn = tk.Button(
            btn_frame, text="▶  开 始", command=self.start_timer,
            bg="#E74C3C", fg="#FFFFFF", activebackground="#C0392B",
            activeforeground="#FFFFFF", **btn_style,
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.pause_btn = tk.Button(
            btn_frame, text="⏸  暂 停", command=self.pause_timer,
            bg="#F39C12", fg="#FFFFFF", activebackground="#E67E22",
            activeforeground="#FFFFFF", state=tk.DISABLED, **btn_style,
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        self.reset_btn = tk.Button(
            btn_frame, text="↺  重 置", command=self.reset_timer,
            bg="#95A5A6", fg="#FFFFFF", activebackground="#7F8C8D",
            activeforeground="#FFFFFF", **btn_style,
        )
        self.reset_btn.pack(side=tk.LEFT, padx=5)

        # ---- 跳过按钮 ----
        skip_frame = tk.Frame(root, bg=bg)
        skip_frame.pack(pady=(0, 4))
        self.skip_btn = tk.Button(
            skip_frame, text="⏭  跳过当前阶段", command=self.skip_current,
            font=("Microsoft YaHei", 9), relief="flat", borderwidth=0,
            padx=12, pady=4, cursor="hand2",
            bg="#BDC3C7", fg="#FFFFFF", activebackground="#95A5A6",
            activeforeground="#FFFFFF",
        )
        self.skip_btn.pack()

        # ---- 底部选项栏 ----
        bottom_frame = tk.Frame(root, bg=bg)
        bottom_frame.pack(pady=(8, 12))

        self.top_var = tk.BooleanVar(value=self.settings["always_on_top"])
        self.top_check = tk.Checkbutton(
            bottom_frame, text="📌 窗口置顶", variable=self.top_var,
            command=self.toggle_always_on_top,
            font=("Microsoft YaHei", 9), bg=bg, fg="#2C3E50",
            activebackground=bg, selectcolor=bg, cursor="hand2",
        )
        self.top_check.pack(side=tk.LEFT, padx=8)

        self.settings_btn = tk.Button(
            bottom_frame, text="⚙  设 置", command=self.open_settings,
            font=("Microsoft YaHei", 9), relief="flat", borderwidth=0,
            padx=12, pady=4, cursor="hand2",
            bg="#34495E", fg="#FFFFFF", activebackground="#2C3E50",
            activeforeground="#FFFFFF",
        )
        self.settings_btn.pack(side=tk.RIGHT, padx=8)

    def _create_circle(self, x, y, r, **kwargs):
        """在 Canvas 上创建圆形（返回 item id）"""
        return self.timer_canvas.create_oval(
            x - r, y - r, x + r, y + r, **kwargs
        )

    def _draw_progress_arc(self, progress: float):
        """
        在 Canvas 上绘制/更新进度圆弧。
        progress 取值 0.0 ~ 1.0
        """
        canvas = self.timer_canvas
        # 删除旧弧
        if self.progress_arc is not None:
            canvas.delete(self.progress_arc)
            self.progress_arc = None

        if progress <= 0:
            return

        cx = cy = self.canvas_size / 2
        r  = 95
        # extent: 360 * progress, 从顶部 (90°) 逆时针
        start_angle = 90
        extent = -360 * progress

        self.progress_arc = canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=start_angle, extent=extent,
            style="arc", outline=self.MODE_COLORS[self.current_mode],
            width=6,
        )

    # ============================================================
    # 显示更新
    # ============================================================
    def _update_display(self):
        """刷新所有动态 UI：时间、进度、模式标签、按钮状态"""
        # 时间文本
        mins, secs = divmod(self.remaining_seconds, 60)
        time_str = f"{mins:02d}:{secs:02d}"
        self.timer_canvas.itemconfig(self.time_text, text=time_str)

        # 百分比 & 进度弧
        if self.total_seconds > 0:
            progress = self.remaining_seconds / self.total_seconds
            pct = int(progress * 100)
        else:
            progress = 0
            pct = 0
        self.timer_canvas.itemconfig(self.percent_text, text=f"{pct}%")
        self._draw_progress_arc(progress)

        # 窗口标题
        mode_label = self.MODE_LABELS[self.current_mode]
        # 去掉 emoji 用于标题
        title_mode = mode_label.split(" ", 1)[1] if " " in mode_label else mode_label
        self.root.title(f"🍅 {title_mode} - {time_str}")

        # 模式标签颜色
        self.mode_label.config(
            text=mode_label,
            fg=self.MODE_COLORS[self.current_mode],
        )

        # 会话标签
        total_sessions = self.settings["sessions_before_long"]
        self.session_label.config(
            text=f"第 {self.completed_sessions + 1} / {total_sessions} 个番茄钟"
        )

        # 进度点
        for i, dot in enumerate(self.session_dots):
            if i < self.completed_sessions:
                dot.config(text="●", fg=self.MODE_COLORS[self.MODE_WORK])
            else:
                dot.config(text="○", fg="#D5C8B5")

        # 按钮状态
        if self.is_running:
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
        elif self.is_paused:
            self.start_btn.config(state=tk.NORMAL, text="▶  继 续")
            self.pause_btn.config(state=tk.DISABLED)
        else:
            self.start_btn.config(state=tk.NORMAL, text="▶  开 始")
            self.pause_btn.config(state=tk.DISABLED)

    # ============================================================
    # 计时逻辑
    # ============================================================
    def _countdown(self):
        """每秒回调：递减并刷新，到达 0 时触发阶段切换"""
        if not self.is_running:
            return

        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self._update_display()
            self.timer_id = self.root.after(1000, self._countdown)
        else:
            # 计时结束
            self.is_running = False
            self.timer_id = None
            self._notify()
            self._switch_mode()

    def start_timer(self):
        """开始 / 继续计时"""
        if not self.is_running:
            self.is_running = True
            self.is_paused  = False
            self._update_display()
            self.timer_id = self.root.after(1000, self._countdown)

    def pause_timer(self):
        """暂停计时"""
        if self.is_running:
            self.is_running = False
            self.is_paused  = True
            if self.timer_id is not None:
                self.root.after_cancel(self.timer_id)
                self.timer_id = None
            self._update_display()

    def reset_timer(self):
        """重置当前计时"""
        self.is_running = False
        self.is_paused  = False
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self._reset_timer_for_mode(self.current_mode)
        self._update_display()

    def skip_current(self):
        """跳过当前阶段"""
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.is_running = False
        self.is_paused  = False
        self._switch_mode()

    # ============================================================
    # 模式切换
    # ============================================================
    def _switch_mode(self):
        """根据当前模式和已完成次数切换到下一模式"""
        if self.current_mode == self.MODE_WORK:
            # 完成一个工作会话
            self.completed_sessions += 1
            if self.completed_sessions >= self.settings["sessions_before_long"]:
                self.completed_sessions = 0
                self.current_mode = self.MODE_LONG_BREAK
            else:
                self.current_mode = self.MODE_SHORT_BREAK
        else:
            # 休息结束，进入工作模式
            self.current_mode = self.MODE_WORK

        self._reset_timer_for_mode(self.current_mode)
        self.is_running = False
        self.is_paused  = False
        self._update_display()

    # ============================================================
    # 通知
    # ============================================================
    def _notify(self):
        """计时结束：播放提示音 + 弹窗"""
        should_sound = self.settings.get("sound_enabled", True)

        # 提示音在子线程播放，避免阻塞 UI
        if should_sound:
            threading.Thread(target=self._play_sound, daemon=True).start()

        # 弹窗提示
        mode_name = self.MODE_LABELS[self.current_mode]
        if self.current_mode == self.MODE_WORK:
            msg = "🍅 工作时间结束！休息一下吧~"
        else:
            msg = "☕ 休息时间结束！开始新的番茄钟吧~"
        self.root.after(100, lambda: messagebox.showinfo(mode_name, msg))

    @staticmethod
    def _play_sound():
        """播放提示音：三段递增频率的蜂鸣声"""
        if winsound is None:
            return  # 非 Windows 平台静默跳过
        try:
            for freq in (880, 1100, 1320):
                winsound.Beep(freq, 180)
        except Exception:
            pass

    # ============================================================
    # 设置窗口
    # ============================================================
    def open_settings(self):
        """打开设置窗口"""
        win = tk.Toplevel(self.root)
        win.title("⚙  设 置")
        win.geometry("360x320")
        win.resizable(False, False)
        win.configure(bg="#F5F0EB")
        win.transient(self.root)
        win.grab_set()

        # 居中于主窗口
        win.update_idletasks()
        rx, ry, rw, rh = (
            self.root.winfo_x(),
            self.root.winfo_y(),
            self.root.winfo_width(),
            self.root.winfo_height(),
        )
        ww, wh = 360, 320
        x = rx + (rw - ww) // 2
        y = ry + (rh - wh) // 2
        win.geometry(f"{ww}x{wh}+{x}+{y}")

        bg = "#F5F0EB"
        entry_style = {
            "font": ("Microsoft YaHei", 11),
            "width": 5,
            "justify": "center",
            "relief": "solid",
            "borderwidth": 1,
        }

        # ---- 工作时间 ----
        row1 = tk.Frame(win, bg=bg)
        row1.pack(pady=(16, 8))
        tk.Label(
            row1, text="🍅 工作时间（分钟）", font=("Microsoft YaHei", 11),
            bg=bg, fg="#2C3E50",
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.work_entry = tk.Entry(row1, **entry_style)
        self.work_entry.insert(0, str(self.settings["work_duration"]))
        self.work_entry.pack(side=tk.RIGHT)

        # ---- 短休息 ----
        row2 = tk.Frame(win, bg=bg)
        row2.pack(pady=8)
        tk.Label(
            row2, text="☕ 短休息（分钟）", font=("Microsoft YaHei", 11),
            bg=bg, fg="#2C3E50",
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.short_entry = tk.Entry(row2, **entry_style)
        self.short_entry.insert(0, str(self.settings["short_break_duration"]))
        self.short_entry.pack(side=tk.RIGHT)

        # ---- 长休息 ----
        row3 = tk.Frame(win, bg=bg)
        row3.pack(pady=8)
        tk.Label(
            row3, text="🌴 长休息（分钟）", font=("Microsoft YaHei", 11),
            bg=bg, fg="#2C3E50",
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.long_entry = tk.Entry(row3, **entry_style)
        self.long_entry.insert(0, str(self.settings["long_break_duration"]))
        self.long_entry.pack(side=tk.RIGHT)

        # ---- 长休息前番茄数 ----
        row4 = tk.Frame(win, bg=bg)
        row4.pack(pady=8)
        tk.Label(
            row4, text="📊 长休息前番茄数", font=("Microsoft YaHei", 11),
            bg=bg, fg="#2C3E50",
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.sessions_entry = tk.Entry(row4, **entry_style)
        self.sessions_entry.insert(0, str(self.settings["sessions_before_long"]))
        self.sessions_entry.pack(side=tk.RIGHT)

        # ---- 声音开关 ----
        row5 = tk.Frame(win, bg=bg)
        row5.pack(pady=8)
        tk.Label(
            row5, text="🔔 提示音", font=("Microsoft YaHei", 11),
            bg=bg, fg="#2C3E50",
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.sound_var = tk.BooleanVar(value=self.settings["sound_enabled"])
        tk.Checkbutton(
            row5, variable=self.sound_var, bg=bg,
            activebackground=bg, selectcolor=bg,
        ).pack(side=tk.RIGHT)

        # ---- 保存按钮 ----
        tk.Button(
            win, text="💾  保存设置", command=lambda: self._save_settings_from_win(win),
            font=("Microsoft YaHei", 12, "bold"), relief="flat", borderwidth=0,
            padx=24, pady=8, cursor="hand2",
            bg="#2ECC71", fg="#FFFFFF", activebackground="#27AE60",
            activeforeground="#FFFFFF",
        ).pack(pady=(16, 8))

    def _save_settings_from_win(self, win: tk.Toplevel):
        """从设置窗口读取值并保存"""
        try:
            work_min     = int(self.work_entry.get())
            short_min    = int(self.short_entry.get())
            long_min     = int(self.long_entry.get())
            sessions_num = int(self.sessions_entry.get())

            if work_min < 1 or short_min < 1 or long_min < 1 or sessions_num < 1:
                raise ValueError("所有时长必须 ≥ 1")

            self.settings["work_duration"]         = work_min
            self.settings["short_break_duration"]  = short_min
            self.settings["long_break_duration"]   = long_min
            self.settings["sessions_before_long"]  = sessions_num
            self.settings["sound_enabled"]         = self.sound_var.get()

            self._save_settings()

            # 重建进度点
            for dot in self.session_dots:
                dot.destroy()
            self.session_dots.clear()
            for i in range(sessions_num):
                dot = tk.Label(
                    self.dots_frame, text="○", font=("Arial", 16),
                    bg="#F5F0EB", fg="#D5C8B5",
                )
                dot.pack(side=tk.LEFT, padx=4)
                self.session_dots.append(dot)

            # 如果已完成数超过新的上限，重置
            if self.completed_sessions >= sessions_num:
                self.completed_sessions = 0

            # 重置当前计时
            self.reset_timer()
            win.destroy()
        except ValueError:
            messagebox.showwarning("输入错误", "请输入大于 0 的有效整数。")

    # ============================================================
    # 杂项
    # ============================================================
    def toggle_always_on_top(self):
        self.settings["always_on_top"] = self.top_var.get()
        self._apply_always_on_top()
        self._save_settings()

    def on_close(self):
        """关闭窗口"""
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
        self.root.destroy()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    app = PomodoroTimer()
    app.root.mainloop()
