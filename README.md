# 🎙️ Floating Mic - H2M (STT Widget)

Ứng dụng micro nổi (Desktop Widget) nhập văn bản tiếng Việt bằng giọng nói theo thời gian thực vào Word, Excel, Notepad, trình duyệt...

Bản quyền thuộc về **© H2M**.

---

## ⚙️ 1. Cấu hình Đầu Vào (Input) & Đầu Ra (Output) - `config.json`

File cấu hình chính: **`config.json`** đặt cùng thư mục với mã nguồn và file `.exe`.

```json
{
  "_ghi_chu": "Cấu hình Đầu Vào (Input Mic) và Đầu Ra (Output Văn Bản) - Chuẩn hóa độ chính xác cao",
  "input": {
    "device_index": null,
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
    "dc_offset_removal": true
  },
  "output": {
    "auto_space": true,
    "auto_enter": false,
    "auto_capitalize": true,
    "format_punctuation": true,
    "convert_numbers": true,
    "strip_fillers": true,
    "paste_delay_ms": 60,
    "min_text_length": 1
  },
  "ui": {
    "always_on_top": true,
    "opacity": 0.96,
    "start_expanded": false
  }
}
```

### Chi tiết các thông số tối ưu độ chính xác:
| Nhóm | Tham số | Ý nghĩa & Tác động đến độ chính xác |
| :--- | :--- | :--- |
| **Input** | `device_index` | Chỉ định ID thiết bị Mic (`null` = mặc định hệ thống; hoặc số `0, 1, 2...`). |
| **Input** | `rms_threshold` | **0.005** (Đã hạ từ 0.012): Độ nhạy năng lượng âm thanh. Giúp không bị nuốt âm đầu hay mất từ khi nói nhỏ/âm lượng mic thấp. |
| **Input** | `preroll_blocks` | **2** (~0.5s) (Đã sửa từ 20 blocks = 5.1s): Lưu đệm âm thanh ngay trước khi phát âm. Khắc phục triệt để lỗi đổ 5 giây tạp âm vào model làm nhận diện sai từ đầu câu. |
| **Input** | `silence_seconds_to_commit` | **0.85s**: Thời gian khoảng lặng để chốt câu. Cho phép người dùng lấy hơi tự nhiên mà không bị ngắt ngang câu giữa chừng. |
| **Input** | `dc_offset_removal` | `true`: Tự động khử độ lệch một chiều tín hiệu mic, lọc nhiễu nền tĩnh. |
| **Output** | `convert_numbers` | `true`: Tự động chuyển khẩu lệnh số ("ba trăm bảy mươi lăm" -> "375", "ngày mười lăm tháng tám năm hai nghìn không trăm hai mươi tư" -> "ngày 15 tháng 8 năm 2024"). |
| **Output** | `format_punctuation` | `true`: Nhận diện khẩu lệnh dấu câu ("dấu chấm", "phẩy", "chấm hỏi", "chấm than", "hai chấm", "xuống dòng"...). |
| **Output** | `auto_capitalize` | `true`: Tự động viết hoa chữ cái tiếng Việt đầu câu và sau dấu chấm, chấm than, hỏi. |
| **Output** | `paste_delay_ms` | `60` ms: Độ trễ chuyển focus cửa sổ trước khi gửi `Ctrl+V`, chống trượt phím dán trên Word/Excel. |

---

## 🚀 2. Chạy thử nghiệm trực tiếp (Development)

```powershell
python floating_mic.py
```

---

## 📦 3. Các lệnh đóng gói ứng dụng (Production Build)

Mở **PowerShell** tại thư mục `FloatingMic`:

```powershell
# Bước 1: Biên dịch mã nguồn Python sang C-Extension .pyd (Bảo mật mã nguồn)
python setup.py build_ext --inplace --force

# Bước 2: Đóng gói thành file .exe duy nhất độc lập (~86 MB)
pyinstaller floating_mic.spec --noconfirm --clean
```

> ⚡ **Lệnh đóng gói nhanh 1 dòng (One-liner):**
> ```powershell
> python setup.py build_ext --inplace --force; Remove-Item *.c -Force -ErrorAction SilentlyContinue; pyinstaller floating_mic.spec --noconfirm --clean; Copy-Item config.json dist\ -Force
> ```

---

## 🎯 4. Kết quả đầu ra

- **File thực thi**: `FloatingMic/dist/FloatingMic.exe` (dung lượng **~86.5 MB**).
- Chạy trực tiếp trên mọi máy tính Windows mà không cần cài đặt Python.
