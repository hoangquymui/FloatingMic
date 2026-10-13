import os
import sys
import re
import time
import threading
import tkinter as tk

try:
    import sounddevice as sd
    SD_OK = True
except Exception:
    SD_OK = False

try:
    import pyperclip
    CLIP_OK = True
except Exception:
    CLIP_OK = False

try:
    import win32gui, win32con, win32api, win32process
    WIN32_OK = True
except Exception:
    WIN32_OK = False

try:
    from stt_engine import DirectSTTEngine, load_config, save_config, VN_ALPHA
    DIRECT_ENGINE_OK = True
except Exception as e:
    print(f"[CẢNH BÁO] Không thể nạp DirectSTTEngine: {e}")
    DIRECT_ENGINE_OK = False
    VN_ALPHA = "a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    def load_config(): return {"input": {}, "output": {}, "ui": {}}
    def save_config(cfg): return False

OUR_PID     = os.getpid()

W_EXPANDED  = 340
H_EXPANDED  = 405
W_COLLAPSED = 340
H_COLLAPSED = 76

C_BG          = "#181825"
C_CARD        = "#1e1e2e"
C_BORDER      = "#313244"
C_PREVIEW     = "#11111b"
C_SEP         = "#313244"
C_TXT         = "#cdd6f4"
C_TXT2        = "#a6adc8"
C_MUTED       = "#6c7086"
C_BLUE        = "#89b4fa"
C_BLUE_HOVER  = "#b4befe"
C_RED         = "#f38ba8"
C_RED_HOVER   = "#eba0ac"
C_GREEN       = "#a6e3a1"
C_YELLOW      = "#f9e2af"
C_ACCENT      = "#cba6f7"
C_CLOSE_HOVER = "#e78284"
C_BTN_HOVER   = "#313244"


class FloatingMicApp:
    def __init__(self):
        self.is_expanded  = False
        self.is_listening = False
        self.prev_hwnd    = None

        self.engine       = None
        self._drag_x      = 0
        self._drag_y      = 0

        self.cfg = load_config()

        self.root = tk.Tk()
        self.auto_space_var = tk.BooleanVar(value=self.cfg.get("output", {}).get("auto_space", True))
        self.auto_enter_var = tk.BooleanVar(value=self.cfg.get("output", {}).get("auto_enter", False))

        self.auto_space_var.trace_add("write", lambda *_: self._sync_output_cfg())
        self.auto_enter_var.trace_add("write", lambda *_: self._sync_output_cfg())

        self._setup_window()
        self._build_collapsed()
        self._build_expanded()

        if self.cfg.get("ui", {}).get("start_expanded", False):
            self._show_expanded()
        else:
            self._show_collapsed()

        self.root.update_idletasks()

        self._close_splash()
        self.root.after(50, self._close_splash)
        self.root.after(250, self._close_splash)

        self._init_stt_engine()

        if WIN32_OK:
            self._track_focus()

    def _sync_output_cfg(self):
        if "output" not in self.cfg:
            self.cfg["output"] = {}
        self.cfg["output"]["auto_space"] = bool(self.auto_space_var.get())
        self.cfg["output"]["auto_enter"] = bool(self.auto_enter_var.get())
        save_config(self.cfg)

    def _get_mic_name(self) -> str:
        dev_idx = self.cfg.get("input", {}).get("device_index", None)
        if dev_idx is None:
            return "Mặc định hệ thống"
        if SD_OK:
            try:
                info = sd.query_devices(dev_idx)
                name = info.get("name", f"Thiết bị #{dev_idx}")
                return name[:24]
            except Exception:
                pass
        return f"Thiết bị #{dev_idx}"

    def _close_splash(self):
        try:
            import pyi_splash
            pyi_splash.close()
        except Exception:
            pass

        if WIN32_OK:
            try:
                def _close_splash_cb(hwnd, _):
                    if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                        cls = win32gui.GetClassName(hwnd).lower()
                        if "_pyi_splash" in cls or "pyinstaller" in cls or "splash" in cls:
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                win32gui.EnumWindows(_close_splash_cb, None)
            except Exception:
                pass

    def _init_stt_engine(self):
        def _load():
            try:
                self.engine = DirectSTTEngine(
                    on_text_callback=self._handle_stt_text,
                    on_status_callback=lambda text, color: self.root.after(0, lambda: self._set_status(text, color))
                )
                self.root.after(0, lambda: self._set_status("Sẵn sàng", C_GREEN))
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda: self._set_status(f"Lỗi Model: {msg}", C_RED))

        self._set_status("Đang nạp mô hình STT...", C_YELLOW)
        threading.Thread(target=_load, daemon=True).start()

    def _handle_stt_text(self, event_type, text):
        if event_type == "partial":
            self.root.after(0, lambda: self._set_preview(text))
        elif event_type == "commit":
            self.root.after(0, lambda: self._set_preview(""))
            if text:
                self.root.after(0, lambda: self._paste_text(text))

    def _setup_window(self):
        self.root.title("FloatingMic_H2M_MainWidget")
        self.root.overrideredirect(True)

        is_top = self.cfg.get("ui", {}).get("always_on_top", True)
        opacity = self.cfg.get("ui", {}).get("opacity", 0.96)
        self.root.attributes("-topmost", is_top)
        self.root.attributes("-alpha", opacity)

        self.root.configure(bg=C_BG, highlightthickness=1, highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - W_EXPANDED - 30
        y  = sh - H_EXPANDED - 80
        self.root.geometry(f"{W_EXPANDED}x{H_EXPANDED}+{x}+{y}")

    def _build_collapsed(self):
        self.f_col = tk.Frame(self.root, bg=C_BG, relief="flat")

        top_bar = tk.Frame(self.f_col, bg=C_BG)
        top_bar.pack(fill="x", expand=False)

        top_bar.bind("<ButtonPress-1>", self._drag_start)
        top_bar.bind("<B1-Motion>",     self._drag_move)

        self.btn_mic_col = tk.Button(
            top_bar, text="BẬT MIC",
            font=("Segoe UI", 9, "bold"),
            fg="#11111b", bg=C_BLUE,
            activebackground=C_BLUE_HOVER, activeforeground="#11111b",
            relief="flat", bd=0, padx=10, pady=3,
            cursor="hand2", command=self._toggle_mic
        )
        self.btn_mic_col.pack(side="left", padx=(8, 8), pady=5)

        self.lbl_st_col = tk.Label(
            top_bar, text="Sẵn sàng",
            font=("Segoe UI", 8, "bold"), fg=C_GREEN, bg=C_BG,
            anchor="w"
        )
        self.lbl_st_col.pack(side="left", fill="x", expand=True)

        btn_close_col = tk.Button(
            top_bar, text=" ✕ ",
            font=("Segoe UI", 8, "bold"),
            fg=C_TXT2, bg=C_BG,
            activebackground=C_CLOSE_HOVER, activeforeground="#11111b",
            relief="flat", bd=0, padx=6, pady=3,
            cursor="hand2", command=self._on_close
        )
        btn_close_col.pack(side="right", padx=(0, 6), pady=5)
        btn_close_col.bind("<Enter>", lambda e: btn_close_col.configure(bg=C_RED, fg="#11111b"))
        btn_close_col.bind("<Leave>", lambda e: btn_close_col.configure(bg=C_BG, fg=C_TXT2))

        btn_exp_col = tk.Button(
            top_bar, text=" ▼ ",
            font=("Segoe UI", 8),
            fg=C_TXT2, bg=C_BG,
            activebackground=C_CARD, activeforeground=C_TXT,
            relief="flat", bd=0, padx=6, pady=3,
            cursor="hand2", command=self._toggle_expand
        )
        btn_exp_col.pack(side="right", padx=(0, 2), pady=5)
        btn_exp_col.bind("<Enter>", lambda e: btn_exp_col.configure(bg=C_CARD, fg=C_TXT))
        btn_exp_col.bind("<Leave>", lambda e: btn_exp_col.configure(bg=C_BG, fg=C_TXT2))

        pf_col = tk.Frame(self.f_col, bg=C_PREVIEW, padx=8, pady=3, highlightthickness=1, highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        pf_col.pack(fill="x", expand=True, padx=8, pady=(0, 6))

        self.lbl_preview_col = tk.Label(
            pf_col, text="Chờ phát âm thanh...",
            font=("Segoe UI", 8, "italic"), fg=C_MUTED, bg=C_PREVIEW,
            anchor="w", justify="left"
        )
        self.lbl_preview_col.pack(fill="x", expand=True)

    def _build_expanded(self):
        self.f_exp = tk.Frame(self.root, bg=C_BG, relief="flat")

        title = tk.Frame(self.f_exp, bg=C_BG, height=36)
        title.pack(fill="x")
        title.pack_propagate(False)
        title.bind("<ButtonPress-1>", self._drag_start)
        title.bind("<B1-Motion>",     self._drag_move)

        tk.Label(
            title, text="Floating Mic - H2M",
            font=("Segoe UI", 9, "bold"),
            fg=C_ACCENT, bg=C_BG, anchor="w"
        ).pack(side="left", padx=10, pady=6)

        btn_close_exp = tk.Button(
            title, text=" ✕ ",
            font=("Segoe UI", 8, "bold"),
            fg=C_TXT2, bg=C_BG,
            activebackground=C_CLOSE_HOVER, activeforeground="#11111b",
            relief="flat", bd=0, padx=8, pady=4,
            cursor="hand2", command=self._on_close
        )
        btn_close_exp.pack(side="right", padx=(0, 6), pady=4)
        btn_close_exp.bind("<Enter>", lambda e: btn_close_exp.configure(bg=C_RED, fg="#11111b"))
        btn_close_exp.bind("<Leave>", lambda e: btn_close_exp.configure(bg=C_BG, fg=C_TXT2))

        btn_col_exp = tk.Button(
            title, text=" ▲ ",
            font=("Segoe UI", 8),
            fg=C_TXT2, bg=C_BG,
            activebackground=C_CARD, activeforeground=C_TXT,
            relief="flat", bd=0, padx=8, pady=4,
            cursor="hand2", command=self._toggle_expand
        )
        btn_col_exp.pack(side="right", padx=(0, 2), pady=4)
        btn_col_exp.bind("<Enter>", lambda e: btn_col_exp.configure(bg=C_CARD, fg=C_TXT))
        btn_col_exp.bind("<Leave>", lambda e: btn_col_exp.configure(bg=C_BG, fg=C_TXT2))

        tk.Frame(self.f_exp, bg=C_SEP, height=1).pack(fill="x")

        self.lbl_st_exp = tk.Label(
            self.f_exp, text="Sẵn sàng",
            font=("Segoe UI", 8, "bold"), fg=C_GREEN, bg=C_BG, anchor="w"
        )
        self.lbl_st_exp.pack(fill="x", padx=12, pady=(6, 2))

        lbl_title_prev = tk.Label(
            self.f_exp, text="VĂN BẢN ĐANG XỬ LÝ",
            font=("Segoe UI", 7, "bold"), fg=C_TXT2, bg=C_BG, anchor="w"
        )
        lbl_title_prev.pack(fill="x", padx=12, pady=(2, 2))

        pf = tk.Frame(self.f_exp, bg=C_PREVIEW, pady=8, padx=10, highlightthickness=1, highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        pf.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.lbl_preview = tk.Label(
            pf, text="Nhấn BẬT MIC rồi nói để nhập văn bản...",
            font=("Segoe UI", 9, "italic"), fg=C_MUTED, bg=C_PREVIEW,
            wraplength=310, justify="left", anchor="nw"
        )
        self.lbl_preview.pack(fill="both", expand=True)

        bf = tk.Frame(self.f_exp, bg=C_BG)
        bf.pack(fill="x", padx=12, pady=(0, 6))

        self.btn_mic = tk.Button(
            bf, text="BẬT MIC",
            font=("Segoe UI", 9, "bold"),
            fg="#11111b", bg=C_BLUE,
            activebackground=C_BLUE_HOVER, activeforeground="#11111b",
            relief="flat", bd=0, padx=16, pady=5,
            cursor="hand2", command=self._toggle_mic
        )
        self.btn_mic.pack(side="left")

        cfg_frame = tk.Frame(self.f_exp, bg=C_BG)
        cfg_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.chk_space = tk.Checkbutton(
            cfg_frame, text="Tự động cách",
            variable=self.auto_space_var,
            font=("Segoe UI", 8), fg=C_TXT, bg=C_BG,
            activebackground=C_BG, activeforeground=C_ACCENT,
            selectcolor=C_CARD, bd=0, cursor="hand2"
        )
        self.chk_space.pack(side="left", padx=(0, 10))

        self.chk_enter = tk.Checkbutton(
            cfg_frame, text="Tự động xuống dòng",
            variable=self.auto_enter_var,
            font=("Segoe UI", 8), fg=C_TXT, bg=C_BG,
            activebackground=C_BG, activeforeground=C_ACCENT,
            selectcolor=C_CARD, bd=0, cursor="hand2"
        )
        self.chk_enter.pack(side="left")

        guide_frame = tk.Frame(self.f_exp, bg=C_CARD, padx=10, pady=6, highlightthickness=1, highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        guide_frame.pack(fill="x", padx=12, pady=(0, 4))

        lbl_guide_title = tk.Label(
            guide_frame, text="HƯỚNG DẪN ĐẶT DẤU CÂU:",
            font=("Segoe UI", 8, "bold"), fg=C_ACCENT, bg=C_CARD, anchor="w"
        )
        lbl_guide_title.pack(fill="x", pady=(0, 4))

        table_frame = tk.Frame(guide_frame, bg=C_CARD)
        table_frame.pack(fill="x")

        rows_col1 = [
            ("dấu chấm", "➔  ."),
            ("dấu phẩy", "➔  ,"),
            ("dấu chấm phẩy", "➔  ;"),
            ("dấu 3 chấm", "➔  ...")
        ]
        rows_col2 = [
            ("dấu hai chấm", "➔  :"),
            ("dấu chấm hỏi", "➔  ?"),
            ("dấu gạch ngang", "➔  -"),
            ("xuống dòng", "➔  ↵")
        ]

        for i, (spoken, symbol) in enumerate(rows_col1):
            tk.Label(table_frame, text=spoken, font=("Segoe UI", 8), fg=C_TXT2, bg=C_CARD, anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            tk.Label(table_frame, text=symbol, font=("Segoe UI", 8, "bold"), fg=C_BLUE, bg=C_CARD, anchor="w").grid(row=i, column=1, sticky="w", padx=(4, 14), pady=1)

        for i, (spoken, symbol) in enumerate(rows_col2):
            tk.Label(table_frame, text=spoken, font=("Segoe UI", 8), fg=C_TXT2, bg=C_CARD, anchor="w").grid(row=i, column=2, sticky="w", pady=1)
            tk.Label(table_frame, text=symbol, font=("Segoe UI", 8, "bold"), fg=C_BLUE, bg=C_CARD, anchor="w").grid(row=i, column=3, sticky="w", padx=(4, 0), pady=1)

        rms_val = self.cfg.get("input", {}).get("rms_threshold", 0.005)
        silence_val = self.cfg.get("input", {}).get("silence_seconds_to_commit", 0.85)
        mic_name = self._get_mic_name()

        lbl_device_info = tk.Label(
            self.f_exp,
            text=f"Mic: {mic_name} | Ngưỡng: {rms_val} | Chốt: {silence_val}s",
            font=("Segoe UI", 7), fg=C_TXT2, bg=C_BG, anchor="center"
        )
        lbl_device_info.pack(fill="x", pady=(2, 2))

        tk.Frame(self.f_exp, bg=C_SEP, height=1).pack(fill="x", pady=(2, 2))
        lbl_copy = tk.Label(
            self.f_exp, text="Bản quyền thuộc về © H2M",
            font=("Segoe UI", 7, "italic"), fg=C_MUTED, bg=C_BG, anchor="center"
        )
        lbl_copy.pack(fill="x", pady=(1, 2))

    def _show_collapsed(self):
        self.f_exp.place_forget()
        self.f_col.place(x=0, y=0, width=W_COLLAPSED, height=H_COLLAPSED)
        self.root.geometry(f"{W_COLLAPSED}x{H_COLLAPSED}")
        self.is_expanded = False

    def _show_expanded(self):
        self.f_col.place_forget()
        self.f_exp.place(x=0, y=0, width=W_EXPANDED, height=H_EXPANDED)
        self.root.geometry(f"{W_EXPANDED}x{H_EXPANDED}")
        self.is_expanded = True

    def _toggle_expand(self):
        if self.is_expanded:
            self._show_collapsed()
        else:
            self._show_expanded()

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _track_focus(self):
        if WIN32_OK:
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd and win32gui.IsWindow(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid != OUR_PID:
                        self.prev_hwnd = hwnd
            except Exception:
                pass
        self.root.after(150, self._track_focus)

    def _toggle_mic(self):
        if self.is_listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        if not self.engine:
            self._set_status("Đang nạp model, thử lại sau!", C_YELLOW)
            return
        self.is_listening = True
        self._last_ended_with_dot = True
        self._last_had_autospace = False
        self._update_mic_ui(True)
        self.engine.start()

    def _stop_listening(self):
        self.is_listening = False
        self._update_mic_ui(False)
        if self.engine:
            self.engine.stop()
        self._set_preview("")

    def _paste_text(self, text):
        if not text or not CLIP_OK:
            return
        try:
            out_text = text.strip()
            if not out_text:
                return

            starts_with_punct = bool(re.match(r"^[.,!?:;\-]", out_text))

            auto_cap = self.cfg.get("output", {}).get("auto_capitalize", True)
            if auto_cap and getattr(self, "_last_ended_with_dot", True):
                out_text = re.sub(r"^(\s*)([" + VN_ALPHA + "0-9])", lambda m: m.group(1) + m.group(2).upper(), out_text)

            self._last_ended_with_dot = bool(re.search(r"[.!?\n]\s*$", out_text))

            if self.auto_space_var.get():
                out_text += " "
            if self.auto_enter_var.get():
                out_text += "\n"

            pyperclip.copy(out_text)

            paste_delay_sec = self.cfg.get("output", {}).get("paste_delay_ms", 60) / 1000.0

            if WIN32_OK:
                cur_hwnd = win32gui.GetForegroundWindow()
                if cur_hwnd and win32gui.IsWindow(cur_hwnd):
                    _, cur_pid = win32process.GetWindowThreadProcessId(cur_hwnd)
                    if cur_pid != OUR_PID:
                        self.prev_hwnd = cur_hwnd

                target_hwnd = self.prev_hwnd
                if target_hwnd and win32gui.IsWindow(target_hwnd):
                    try:
                        cur_fg = win32gui.GetForegroundWindow()
                        if cur_fg != target_hwnd:
                            win32gui.BringWindowToTop(target_hwnd)
                            win32gui.SetForegroundWindow(target_hwnd)
                            time.sleep(paste_delay_sec)
                    except Exception:
                        pass

                VK_BACK = 0x08
                VK_CTRL = 0x11
                VK_V    = 0x56
                KEYUP   = win32con.KEYEVENTF_KEYUP

                if starts_with_punct and getattr(self, "_last_had_autospace", False):
                    win32api.keybd_event(VK_BACK, 0, 0, 0)
                    win32api.keybd_event(VK_BACK, 0, KEYUP, 0)
                    time.sleep(0.02)

                win32api.keybd_event(VK_CTRL, 0, 0, 0)
                win32api.keybd_event(VK_V,    0, 0, 0)
                win32api.keybd_event(VK_V,    0, KEYUP, 0)
                win32api.keybd_event(VK_CTRL, 0, KEYUP, 0)

            self._last_had_autospace = bool(self.auto_space_var.get())
        except Exception as e:
            print(f"Lỗi paste: {e}")

    def _update_mic_ui(self, listening: bool):
        bg_col = C_RED if listening else C_BLUE
        fg_col = "#11111b"
        label_exp = "DỪNG LẠI" if listening else "BẬT MIC"
        label_col = "DỪNG" if listening else "BẬT MIC"
        if hasattr(self, "btn_mic"):
            self.btn_mic.configure(bg=bg_col, fg=fg_col, text=label_exp)
        if hasattr(self, "btn_mic_col"):
            self.btn_mic_col.configure(bg=bg_col, fg=fg_col, text=label_col)

    def _set_status(self, text, color=None):
        c = color or C_TXT2
        if hasattr(self, "lbl_st_exp"):
            self.lbl_st_exp.configure(text=text, fg=c)
        if hasattr(self, "lbl_st_col"):
            self.lbl_st_col.configure(text=text, fg=c)

    def _set_preview(self, text):
        if text:
            if hasattr(self, "lbl_preview"):
                self.lbl_preview.configure(text=text, fg=C_TXT)
            if hasattr(self, "lbl_preview_col"):
                self.lbl_preview_col.configure(text=text, fg=C_YELLOW)
        else:
            if hasattr(self, "lbl_preview"):
                self.lbl_preview.configure(text="Nhấn BẬT MIC rồi nói để nhập văn bản...", fg=C_MUTED)
            if hasattr(self, "lbl_preview_col"):
                self.lbl_preview_col.configure(text="Chờ phát âm thanh...", fg=C_MUTED)

    def _on_close(self):
        self._stop_listening()
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()


def main():
    if not SD_OK:
        print("[CẢNH BÁO] Thiếu sounddevice")
    if not CLIP_OK:
        print("[CẢNH BÁO] Thiếu pyperclip")
    if not WIN32_OK:
        print("[CẢNH BÁO] Thiếu pywin32")

    app = FloatingMicApp()
    app.run()


if __name__ == "__main__":
    main()
