import os
import sys
import re
import json
import time
import queue
import threading
from collections import deque
import numpy as np

import sounddevice as sd
import sherpa_onnx

# ── 1. CẤU HÌNH VÀ TÌM ĐƯỜNG DẪN ───────────────────────────────────────────
CONFIG_FILENAME = "config.json"

DEFAULT_CONFIG = {
    "input": {
        "device_index": None,
        "sample_rate": 16000,
        "block_size": 4096,
        "channels": 1,
        "rms_threshold": 0.005,
        "vad_threshold": 0.35,
        "silence_seconds_to_commit": 0.85,
        "preroll_blocks": 2,
        "step_seconds": 0.20,
        "min_decode_seconds": 0.3,
        "max_window_seconds": 6.0,
        "ring_buffer_seconds": 12,
        "dc_offset_removal": True
    },
    "output": {
        "auto_space": True,
        "auto_enter": False,
        "auto_capitalize": True,
        "format_punctuation": True,
        "convert_numbers": True,
        "strip_fillers": True,
        "paste_delay_ms": 60,
        "min_text_length": 1
    },
    "ui": {
        "always_on_top": True,
        "opacity": 0.96,
        "start_expanded": False
    }
}

def get_config_path() -> str:
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    exe_dir = os.path.dirname(sys.executable)
    search_paths = [
        os.path.join(base_dir, CONFIG_FILENAME),
        os.path.join(exe_dir, CONFIG_FILENAME),
        os.path.abspath(CONFIG_FILENAME),
        os.path.join(os.path.dirname(base_dir), CONFIG_FILENAME)
    ]
    for p in search_paths:
        if os.path.isfile(p):
            return p
    return os.path.join(base_dir, CONFIG_FILENAME)

def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg_path = get_config_path()
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                for section in ["input", "output", "ui"]:
                    if section in user_cfg and isinstance(user_cfg[section], dict):
                        cfg[section].update(user_cfg[section])
        except Exception as e:
            print(f"[DirectSTT] Lỗi đọc {CONFIG_FILENAME}: {e}")
    return cfg

def save_config(cfg: dict) -> bool:
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[DirectSTT] Lỗi ghi {CONFIG_FILENAME}: {e}")
        return False

VN_ALPHA = "a-zA-ZàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
NOISE_FILLER_WORDS = {"ừ", "à", "ờ", "uh", "ừm", "ơ", "ư", "hà", "hử", "ê", "ha", "hm", "hmm"}

def find_sherpa_onnx_paths():
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    exe_dir = os.path.dirname(sys.executable)
    search_dirs = [
        os.path.abspath(os.path.join(base_dir, "SpeechFunc", "SherpaONNX", "sherpa-onnx-zipformer")),
        os.path.abspath(os.path.join(exe_dir, "SpeechFunc", "SherpaONNX", "sherpa-onnx-zipformer")),
        os.path.abspath(os.path.join(base_dir, "..", "SpeechFunc", "SherpaONNX", "sherpa-onnx-zipformer")),
        os.path.abspath(os.path.join(exe_dir, "..", "SpeechFunc", "SherpaONNX", "sherpa-onnx-zipformer")),
        os.path.abspath(os.path.join(base_dir, "..", "SpeechFunc", "models")),
        os.path.abspath(os.path.join(base_dir, "..", "SpeechFunc")),
        base_dir,
        exe_dir
    ]

    for d in search_dirs:
        if os.path.isdir(d):
            tokens = os.path.join(d, "tokens.txt")
            if os.path.exists(tokens):
                for root, dirs, files in os.walk(d):
                    enc_int8 = [f for f in files if f.startswith("encoder") and f.endswith(".int8.onnx")]
                    enc_fp32 = [f for f in files if f.startswith("encoder") and f.endswith(".onnx") and not f.endswith(".int8.onnx")]
                    encoder = os.path.join(root, enc_int8[0] if enc_int8 else enc_fp32[0]) if (enc_int8 or enc_fp32) else None

                    dec_int8 = [f for f in files if f.startswith("decoder") and f.endswith(".int8.onnx")]
                    dec_fp32 = [f for f in files if f.startswith("decoder") and f.endswith(".onnx") and not f.endswith(".int8.onnx")]
                    decoder = os.path.join(root, dec_int8[0] if dec_int8 else dec_fp32[0]) if (dec_int8 or dec_fp32) else None

                    join_int8 = [f for f in files if f.startswith("joiner") and f.endswith(".int8.onnx")]
                    join_fp32 = [f for f in files if f.startswith("joiner") and f.endswith(".onnx") and not f.endswith(".int8.onnx")]
                    joiner = os.path.join(root, join_int8[0] if join_int8 else join_fp32[0]) if (join_int8 or join_fp32) else None

                    if encoder and decoder and joiner and tokens:
                        return root, encoder, decoder, joiner, tokens
    return "", None, None, None, None

DIGITS_MAP = {
    "không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4,
    "năm": 5, "lăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9
}

def parse_vietnamese_number_tokens(words: list):
    if not words:
        return None
    if len(words) == 1:
        w = words[0]
        if w in DIGITS_MAP:
            return str(DIGITS_MAP[w])
        if w == "mười":
            return "10"
        return None

    scale_words = {"mươi", "mười", "chục", "trăm", "nghìn", "ngàn", "triệu", "tỷ", "linh", "lẻ"}
    if not any(w in scale_words for w in words):
        if all(w in DIGITS_MAP for w in words):
            return "".join(str(DIGITS_MAP[w]) for w in words)
        return None

    def parse_under_1000(sub_words):
        val = 0
        i = 0
        while i < len(sub_words):
            w = sub_words[i]
            if w in DIGITS_MAP:
                d = DIGITS_MAP[w]
                if i + 1 < len(sub_words):
                    nxt = sub_words[i + 1]
                    if nxt == "trăm":
                        val += d * 100
                        i += 2
                        continue
                    elif nxt in ["mươi", "chục"]:
                        val += d * 10
                        i += 2
                        continue
                val += d
                i += 1
            elif w == "mười":
                val += 10
                i += 1
            elif w in ["linh", "lẻ"]:
                i += 1
            elif w == "trăm":
                if val == 0:
                    val = 100
                i += 1
            elif w in ["mươi", "chục"]:
                if val == 0:
                    val = 10
                i += 1
            else:
                return None
        return val

    i = 0
    sub_chunk = []
    res_val = 0
    accum = 0
    n = len(words)

    while i < n:
        w = words[i]
        if w == "tỷ":
            sub_res = parse_under_1000(sub_chunk) if sub_chunk else 1
            if sub_res is None: return None
            accum = (accum + sub_res) * 1000000000
            res_val += accum
            accum = 0
            sub_chunk = []
        elif w == "triệu":
            sub_res = parse_under_1000(sub_chunk) if sub_chunk else 1
            if sub_res is None: return None
            accum = (accum + sub_res) * 1000000
            res_val += accum
            accum = 0
            sub_chunk = []
        elif w in ["nghìn", "ngàn"]:
            sub_res = parse_under_1000(sub_chunk) if sub_chunk else 1
            if sub_res is None: return None
            accum = (accum + sub_res) * 1000
            res_val += accum
            accum = 0
            sub_chunk = []
        else:
            sub_chunk.append(w)
        i += 1

    if sub_chunk:
        sub_res = parse_under_1000(sub_chunk)
        if sub_res is None: return None
        res_val += sub_res

    return str(res_val)

def normalize_vietnamese_numbers(text: str) -> str:
    text = re.sub(r"\b(thứ\s+(?:hai|ba|tư|năm|sáu|bảy))\b", r"__THU_\1__", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(tháng\s+[a-zà-ỹá-ỵ]+?)\s+năm\s+", r"\1 __NAM_YEAR__ ", text, flags=re.IGNORECASE)

    vocab = r"(?:không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|bẩy|tám|chín|mười|mươi|chục|trăm|nghìn|ngàn|triệu|tỷ|linh|lẻ)"
    multi_pattern = rf"\b{vocab}(?:\s+{vocab})+\b"

    def multi_repl(m):
        words = m.group(0).split()
        num = parse_vietnamese_number_tokens(words)
        return num if num is not None else m.group(0)

    text = re.sub(multi_pattern, multi_repl, text, flags=re.IGNORECASE)

    single_prefix = r"\b(số|ngày|tháng|năm|lúc|giờ|phút|giây|tập|phần|chương|điều|khoản|mục|bước|lầu|tầng|phòng|bàn|trung\s+đoàn|sư\s+đoàn|tiểu\s+đoàn|đại\s+đội)\s+(không|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\b"
    def single_repl(m):
        prefix = m.group(1)
        w = m.group(2).lower()
        if w in DIGITS_MAP:
            return f"{prefix} {DIGITS_MAP[w]}"
        if w == "mười":
            return f"{prefix} 10"
        return m.group(0)

    text = re.sub(single_prefix, single_repl, text, flags=re.IGNORECASE)
    text = re.sub(r"__NAM_YEAR__", "năm", text)
    text = re.sub(r"__THU_(.+?)__", r"\1", text)
    return text

def clean_text(text: str, cfg: dict = None) -> str:
    if not text:
        return ""

    if cfg is None:
        cfg = DEFAULT_CONFIG

    out_cfg = cfg.get("output", DEFAULT_CONFIG["output"])
    text = str(text).strip()

    if out_cfg.get("strip_fillers", True):
        filler_lead = r"^(?:\s*(?:ừ|à|ờ|ừm|ơ|ư|ứ|um|uh|hà|hử|ê|ha|hm|hmm)\b\s*)+"
        text = re.sub(filler_lead, "", text, flags=re.IGNORECASE)
        filler_trail = r"(?:\s*\b(?:ừ|à|ờ|ừm|ơ|ư|ứ|um|uh|hà|hử|ê|ha|hm|hmm)\s*)+$"
        text = re.sub(filler_trail, "", text, flags=re.IGNORECASE)

    if out_cfg.get("format_punctuation", True):
        patterns = [
            (r"(?i)\b(?:dấu\s+ba\s+chấm|dấu\s+3\s+chấm|dấu\s+chấm\s+lửng|ba\s+chấm)\b", "..."),
            (r"(?i)\b(?:dấu\s+chấm\s+than|chấm\s+than|dấu\s+than)\b", "!"),
            (r"(?i)\b(?:dấu\s+chấm\s+hỏi|chấm\s+hỏi|dấu\s+hỏi)\b", "?"),
            (r"(?i)\b(?:dấu\s+chấm\s+phẩy|chấm\s+phẩy)\b", ";"),
            (r"(?i)\b(?:dấu\s+hai\s+chấm|hai\s+chấm)\b", ":"),
            (r"(?i)\b(?:dấu\s+gạch\s+ngang|gạch\s+đầu\s+dòng|dấu\s+gạch|gạch\s+ngang)\b", " - "),
            (r"(?i)\b(?:dấu\s+chấm|chấm\s+hết|dấu\s+châm)\b", "."),
            (r"(?i)(?<=[a-zà-ỹá-ỵ0-9])\s+chấm\s*$", "."),
            (r"(?i)\b(?:dấu\s+phẩy|phẩy(?!\s+(?:tay|bút)))\b", ","),
            (r"(?i)\b(?:mở\s+ngoặc\s+đơn|mở\s+ngoặc)\b", "("),
            (r"(?i)\b(?:đóng\s+ngoặc\s+đơn|đóng\s+ngoặc)\b", ")"),
            (r"(?i)\b(?:mở\s+ngoặc\s+kép)\b", "\""),
            (r"(?i)\b(?:đóng\s+ngoặc\s+kép)\b", "\""),
            (r"(?i)\b(?:xuống\s+dòng|ngắt\s+dòng|dòng\s+mới|sang\s+dòng)\b", "\n"),
        ]
        for p, rep in patterns:
            text = re.sub(p, rep, text)

    if out_cfg.get("convert_numbers", True):
        text = normalize_vietnamese_numbers(text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"\s+([,;:.!?])", r"\1", text)
    text = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"(\.\.\.|[.!?])(?=[^\s])", r"\1 ", text)
    text = re.sub(r"\s*(\n)\s*", r"\1", text)
    text = text.strip()

    if out_cfg.get("auto_capitalize", True):
        text = re.sub(
            r"([.!?\n]+)(\s*)([" + VN_ALPHA + "0-9])",
            lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
            text
        )

    return text.strip()

def is_bad_text(text: str, min_len: int = 1) -> bool:
    clean = text.lower().strip()
    if not clean:
        return True
    if clean in NOISE_FILLER_WORDS:
        return True
    if re.match(r"^[.,!?:;\-\n\"'()]+$", clean):
        return False
    if len(clean) < min_len:
        return True
    return False

def rms_value(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio ** 2)))

class AudioRingBuffer:
    def __init__(self, max_samples: int):
        self.max_samples = max_samples
        self.buffer = []
        self.total_samples = 0
        self.lock = threading.Lock()

    def append(self, audio: np.ndarray):
        if audio.size == 0:
            return
        audio = audio.astype(np.float32, copy=False)
        with self.lock:
            self.buffer.append(audio)
            self.total_samples += audio.size
            while self.total_samples > self.max_samples and self.buffer:
                removed = self.buffer.pop(0)
                self.total_samples -= removed.size

    def get_audio(self) -> np.ndarray:
        with self.lock:
            if not self.buffer:
                return np.array([], dtype=np.float32)
            return np.concatenate(self.buffer).astype(np.float32, copy=False)

    def clear(self):
        with self.lock:
            self.buffer.clear()
            self.total_samples = 0

    def size(self) -> int:
        with self.lock:
            return self.total_samples

class DirectSTTEngine:
    def __init__(self, on_text_callback=None, on_status_callback=None):
        self.on_text = on_text_callback
        self.on_status = on_status_callback
        self.is_running = False

        self.cfg = load_config()
        inp_cfg = self.cfg.get("input", DEFAULT_CONFIG["input"])

        self.sample_rate = inp_cfg.get("sample_rate", 16000)
        self.block_size = inp_cfg.get("block_size", 4096)
        self.rms_threshold = inp_cfg.get("rms_threshold", 0.005)
        self.silence_to_commit = inp_cfg.get("silence_seconds_to_commit", 0.85)
        self.preroll_blocks = max(1, inp_cfg.get("preroll_blocks", 2))
        self.step_seconds = inp_cfg.get("step_seconds", 0.20)
        self.min_decode_samples = int(self.sample_rate * inp_cfg.get("min_decode_seconds", 0.3))
        self.max_window_samples = int(self.sample_rate * inp_cfg.get("max_window_seconds", 6.0))
        self.ring_buffer_samples = int(self.sample_rate * inp_cfg.get("ring_buffer_seconds", 12))
        self.dc_offset_removal = inp_cfg.get("dc_offset_removal", True)
        self.device_index = inp_cfg.get("device_index", None)

        m_dir, enc, dec, join, tok = find_sherpa_onnx_paths()
        if not enc:
            raise FileNotFoundError("Không tìm thấy mô hình Sherpa-ONNX zipformer trong hệ thống!")

        cpu_threads = max(1, min(4, os.cpu_count() or 4))
        print(f"[DirectSTT] Nạp mô hình từ: {m_dir}")
        print(f"[DirectSTT] Cấu hình: RMS={self.rms_threshold}, SilenceCommit={self.silence_to_commit}s, PrerollBlocks={self.preroll_blocks}")

        if hasattr(sherpa_onnx, "OfflineRecognizer") and hasattr(sherpa_onnx.OfflineRecognizer, "from_transducer"):
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=enc, decoder=dec, joiner=join, tokens=tok,
                num_threads=cpu_threads, sample_rate=self.sample_rate, feature_dim=80, decoding_method="greedy_search"
            )
        else:
            self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                encoder=enc, decoder=dec, joiner=join, tokens=tok,
                num_threads=cpu_threads, sample_rate=self.sample_rate, feature_dim=80, decoding_method="greedy_search"
            )

        self.audio_queue = queue.Queue()
        self.audio_buffer = AudioRingBuffer(self.ring_buffer_samples)
        self.preroll_buffer = deque(maxlen=self.preroll_blocks)

        self.last_voice_time = time.time()
        self.has_current_voice = False
        self.current_text = ""
        self.last_sent_text = ""
        self.last_decode_time = 0.0

        self.stream = None
        self.worker_thread = None

    def reload_config(self):
        self.cfg = load_config()
        inp_cfg = self.cfg.get("input", DEFAULT_CONFIG["input"])
        self.rms_threshold = inp_cfg.get("rms_threshold", 0.005)
        self.silence_to_commit = inp_cfg.get("silence_seconds_to_commit", 0.85)
        self.preroll_blocks = max(1, inp_cfg.get("preroll_blocks", 2))
        self.preroll_buffer = deque(maxlen=self.preroll_blocks)
        self.step_seconds = inp_cfg.get("step_seconds", 0.20)
        self.dc_offset_removal = inp_cfg.get("dc_offset_removal", True)
        self.device_index = inp_cfg.get("device_index", None)

    def start(self):
        if self.is_running:
            return
        self.reload_config()
        self.is_running = True
        self.audio_buffer.clear()
        self.preroll_buffer.clear()
        self.has_current_voice = False
        self.current_text = ""
        self.last_sent_text = ""

        def audio_cb(indata, frames, time_info, status):
            if self.is_running:
                self.audio_queue.put(indata[:, 0].copy())

        stream_kwargs = {
            "samplerate": self.sample_rate,
            "blocksize": self.block_size,
            "channels": 1,
            "dtype": "float32",
            "callback": audio_cb
        }
        if self.device_index is not None:
            stream_kwargs["device"] = self.device_index

        try:
            self.stream = sd.InputStream(**stream_kwargs)
            self.stream.start()
        except Exception as e:
            print(f"[DirectSTT] Không thể mở thiết bị mic {self.device_index}: {e}. Dùng thiết bị mặc định.")
            stream_kwargs.pop("device", None)
            self.stream = sd.InputStream(**stream_kwargs)
            self.stream.start()

        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        if self.on_status:
            self.on_status("Đang nghe...", "#4ade80")

    def stop(self):
        self.is_running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.on_status:
            self.on_status("Đã dừng", "#94a3b8")

    def _transcribe(self, audio: np.ndarray) -> str:
        if audio.size < self.min_decode_samples:
            return ""
        try:
            st = self.recognizer.create_stream()
            st.accept_waveform(self.sample_rate, audio)
            self.recognizer.decode_stream(st)
            res = st.result if hasattr(st, "result") else self.recognizer.get_result(st)
            raw = res.text if hasattr(res, "text") else str(res)
            txt = clean_text(raw, self.cfg)
            min_len = self.cfg.get("output", {}).get("min_text_length", 1)
            return "" if is_bad_text(txt, min_len) else txt
        except Exception:
            return ""

    def _worker_loop(self):
        while self.is_running:
            try:
                while not self.audio_queue.empty():
                    chunk = self.audio_queue.get_nowait()
                    if self.dc_offset_removal and chunk.size > 0:
                        chunk = chunk - np.mean(chunk)

                    chunk_rms = rms_value(chunk)
                    is_voice = (chunk_rms >= self.rms_threshold)
                    self.preroll_buffer.append(chunk)

                    if is_voice:
                        self.last_voice_time = time.time()
                        if not self.has_current_voice:
                            self.has_current_voice = True
                            while self.preroll_buffer:
                                self.audio_buffer.append(self.preroll_buffer.popleft())
                        else:
                            self.audio_buffer.append(chunk)
                    elif self.has_current_voice:
                        self.audio_buffer.append(chunk)
            except Exception:
                pass

            now = time.time()

            if self.has_current_voice:
                if now - self.last_voice_time >= self.silence_to_commit:
                    if self.current_text and self.on_text:
                        commit_text = self.current_text
                        self.current_text = ""
                        self.last_sent_text = ""
                        self.has_current_voice = False
                        self.audio_buffer.clear()
                        self.preroll_buffer.clear()
                        self.on_text("commit", commit_text)
                    else:
                        self.has_current_voice = False
                        self.audio_buffer.clear()
                        self.preroll_buffer.clear()
                    time.sleep(0.04)
                    continue

            if now - self.last_decode_time < self.step_seconds:
                time.sleep(0.02)
                continue

            self.last_decode_time = now
            size = self.audio_buffer.size()
            if size < self.min_decode_samples:
                time.sleep(0.02)
                continue

            audio = self.audio_buffer.get_audio()
            if audio.size > self.max_window_samples:
                audio = audio[-self.max_window_samples:]

            txt = self._transcribe(audio)
            if txt and txt != self.last_sent_text:
                if not self.current_text or len(txt) >= len(self.current_text):
                    self.current_text = txt
                    self.last_sent_text = txt
                    if self.on_text:
                        self.on_text("partial", txt)

            time.sleep(0.02)
