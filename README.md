# Moe Moe Secretary — bản Python (chỉ Azur Lane, giao diện Tiếng Việt)

Linh vật màn hình (desktop mascot) viết lại từ đầu bằng **Python 3.11+ / PySide6**, chỉ giữ
adapter **Azur Lane** (dữ liệu từ <https://azurlane.koumakan.jp>). Đóng gói được thành một file
`MoeMoeSecretary.exe` chạy độc lập trên Windows, không hiện cửa sổ CMD.

## Cách dùng nhanh

1. Chạy `build_exe.bat` (nhấp đúp) → ra `dist\MoeMoeSecretary.exe`.
2. Chép `MoeMoeSecretary.exe` đi đâu tuỳ ý rồi nhấp đúp. Lần đầu chạy, chương trình tự tạo
   `config.yaml` và thư mục `cache\` **ngay cạnh file .exe**, rồi tải nhân vật *Nagato*.
3. Muốn đổi nhân vật: chuột phải vào nhân vật (hoặc icon khay hệ thống) → **Chọn nhân vật...**
4. Cập nhật lên bản mới mà không phải xoá dự án: kéo file `.zip` bản mới lên `update_and_build.bat`
   (xem mục [Cập nhật nhanh](#cập-nhật-nhanh-update_and_buildbat)).

Chạy trực tiếp từ mã nguồn (không cần build):

```bat
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Điều khiển

| Thao tác | Tác dụng |
|---|---|
| Giữ chuột trái + kéo | Di chuyển nhân vật |
| Nhấp chuột trái (1 lần) | Bong bóng thoại ngẫu nhiên theo ngữ cảnh (kèm giọng nói nếu âm lượng > 0) |
| Nhấp chuột trái liên tục **5 lần** (mỗi lần cách nhau < 1,2 s) | Thoại đặc biệt **Affinity (Love)** |
| Nhấn giữ chuột trái **> 1,5 giây** (không kéo) | Thoại **Pledge** của trang phục **mặc định** (bất kể đang mặc bộ nào); nhả chuột không tính là một cú nhấp |
| Nhấp chuột phải | Menu điều khiển (có mục **Trợ giúp**) |
| Nhấp chuột giữa / `Esc` / `Alt+F4` | Thoát gọn gàng |
| `J` / `K` | Trang phục tiếp theo / trước |
| `T` | Bật/tắt luôn hiển thị trên cùng |
| `S` | Lật ngang nhân vật |
| `F` | Bật/tắt hiệu ứng lơ lửng |

Phím tắt chỉ hoạt động khi cửa sổ nhân vật đang được chọn — **nhấp vào nhân vật một lần để lấy tiêu điểm**.
(Nếu dùng bộ gõ như Unikey và phím không ăn, chuyển sang chế độ tiếng Anh/`E` khi đang chọn nhân vật.)

Vùng nền trong suốt của cửa sổ cho chuột xuyên qua; chỉ phần thân nhân vật mới bắt chuột.

### Thoại điều khiển: Hover Mode, khi rảnh, nhấp 5 lần, nhấn giữ

Các thoại này dùng chung một hàm `Controller.play_voice_category(tên_mục, fallback_to_default, force_default)`:
tìm mục thoại theo tên (không phân biệt hoa/thường, chấp nhận biến thể như `Starting Mission` ~ `Mission Start`)
trong **trang phục đang mặc**; thiếu mục đó (hoặc mục đó không có file âm thanh) thì lấy của **trang phục mặc
định**; `force_default=True` thì luôn lấy của trang phục mặc định.

| Sự kiện | Mục thoại |
|---|---|
| Bật Hover Mode | `Start mission` / `Starting mission` |
| Tắt Hover Mode | `Return from mission` |
| Nhấp chuột trái liên tiếp 5 lần | `Affinity (Love)` |
| Nhấn giữ chuột trái > 1,5 giây | `Pledge` (luôn của trang phục mặc định) |
| Không tương tác trong `idle_voice_interval` giây | Luân phiên `Task` → `Mail` → `Commission` → `Task`... (về `Task` khi đổi nhân vật) |

- **Thoại khi rảnh** mặc định mỗi 300 giây (5 phút). Mọi thao tác (nhấp, kéo, nhấn giữ, đổi trang phục / nhân vật,
  bật-tắt Hover Mode, đổi cài đặt...) đều đếm lại từ đầu. Chỉnh ở menu **Thoại khi rảnh** hoặc `idle_voice_interval`
  (giây, `0` = tắt, cho phép 10 – 86400).
- Tên mục trên Wiki có thể khác dự kiến. Lệnh `python -m src.scraper "Nagato"` có mục *Mục thoại điều khiển* cho
  biết mục nào đã nhận diện được và liệt kê các mục chưa phân loại; nếu thiếu, bổ sung luật ở `src/models.py`
  (`_VOICE_RULES`).
- Tiếng của lần nhấp thứ 5 không chồng lên tiếng nhấp thường: câu mới luôn ngắt câu cũ, kể cả câu cũ còn đang tải.

### Tải trước giọng nói (lần đầu vào một trang phục)

Khi mở nhân vật hoặc chuyển sang một trang phục **lần đầu tiên**, chương trình tự tải nền **toàn bộ** giọng nói của
trang phục đó và của trang phục mặc định (để làm dự phòng) vào `cache\<Tàu>\audio\`, không làm đơ giao diện.
Tải xong sẽ ghi dấu mốc `audio\voices_<mã>.json`; các lần sau **bỏ qua hoàn toàn bước tải hàng loạt**.

- Dùng một luồng riêng, tải nối tiếp (nghỉ ~0,12 s giữa các file), tra URL theo lô (≤ 40 tên/yêu cầu API).
- Mỗi bộ thoại chỉ có một tác vụ tại một thời điểm; đổi trang phục liên tục thì tác vụ của trang phục đã bỏ đi tự
  dừng (file đã tải giữ nguyên, lần sau làm tiếp phần còn thiếu, không tải lại).
- Mất mạng / bị Wiki chặn (403): dừng, **không** ghi dấu mốc, lần sau thử lại. File nào thiếu thì vẫn được tải
  theo yêu cầu lúc phát. Wiki thêm câu thoại mới thì dấu mốc tự mất hiệu lực và chỉ tải phần mới.
- `audio_volume: 0` thì không tải file âm thanh nào. Khi thoát, hàng đợi bị huỷ và các luồng nền dừng gọn.

### Trợ giúp

Menu chuột phải (hoặc icon khay) → **Trợ giúp** mở cửa sổ hướng dẫn: các thao tác chuột, phím tắt Hover Mode
(hiển thị đúng phím đang cấu hình), thoại khi rảnh... Cửa sổ luôn nổi lên trên, chỉ mở một cửa sổ duy nhất,
đóng nó **không** thoát ứng dụng.

### Trang phục, độ trong suốt, Hover Mode

- **Nhớ trang phục**: đổi trang phục (hoặc thoát) là tên trang phục được ghi vào `skin_name`; lần mở sau tự mặc
  lại đúng bộ đó. Tên không còn tồn tại hoặc ảnh không tải được thì quay về trang phục mặc định.
- **Độ trong suốt**: menu chuột phải → *Độ trong suốt* (100 / 80 / 60 / 40 / 20 %) hoặc sửa `opacity` trong
  `config.yaml` (0.1 – 1.0). Chỉ nhân vật mờ đi, bong bóng thoại vẫn rõ chữ.
- **Hover Mode** (`F12` mặc định): chuột **xuyên qua** nhân vật xuống ứng dụng bên dưới, không kéo / nhấp /
  mở menu được. Bật/tắt bằng phím tắt toàn cục ở bất kỳ ứng dụng nào, hoặc mục *Chế độ Hover* trong menu ở
  icon khay hệ thống. Luôn khởi động ở trạng thái TẮT. Đổi phím bằng `hover_hotkey` (ví dụ `Ctrl+Alt+H`,
  `Shift+F9`; phím chữ/số phải đi kèm Ctrl/Alt/Shift/Win). **Lưu ý**: phím tắt toàn cục bị chiếm ở *mọi* ứng dụng
  khi chương trình chạy (F12 mặc định sẽ mất tác dụng với DevTools của trình duyệt) – nếu vướng thì đổi phím khác.

## Thoại riêng theo trang phục

Nhiều trang phục có bộ thoại và giọng nói riêng (mục riêng trên trang `<Tàu>/Quotes`). Ứng dụng ghép từng
trang phục với mục thoại của nó rồi:

- **Nhấp chuột**: chỉ lấy câu thoại của trang phục đang mặc (Idle / Touch / Details), **không trộn** với trang phục
  mặc định. (Nhấp dồn 5 lần giờ phát "Affinity (Love)" thay cho "Special Touch" trước đây.)
- **Đổi trang phục (`J`/`K`/menu)**: hiện "Đã đổi sang trang phục: …", khoảng 1 giây sau tự nói câu giới thiệu bộ đồ
  (ưu tiên Acquisition → Login → Self Introduction → Ship Description) kèm giọng nói. Bấm đổi liên tiếp thì chỉ
  trang phục cuối cùng nói. Tắt bằng `skin_voice: false` trong `config.yaml`.
- Trang phục không có mục thoại riêng: khi đổi thì im lặng, còn nhấp chuột vẫn dùng thoại của trang phục mặc định.

Thư viện ảnh của Wiki đặt tên trang phục theo **mã chủ đề trong tên file** (Wedding, Christmas, RaceQueen,
Hot Springs…), còn mục thoại dùng **tên chính thức** (Starlight Oath, Reindeer Master, Wind Catcher…), nên việc ghép
(`src/skinmatch.py`) đi qua nhiều lớp, từ chắc chắn tới phỏng đoán:

1. Trang phục mặc định ↔ mục "Default".
2. **Biến thể** (ví dụ `Hot SpringsCN` là bản CN của `Hot Springs`) dùng chung thoại với bản gốc.
3. Tên hoặc tên phụ trùng khớp; rồi giống nhau về từ ngữ (có quy ước Wedding = Oath).
4. **Theo thứ tự phát hành** (cả hai trang đều liệt kê theo thứ tự này): các mục đã ghép chắc chắn làm mốc; phần
   còn lại ghép tuần tự, phần dư ở cuối được coi là bộ mới nhất chưa có thoại.

Thông báo đổi trang phục hiển thị **tên chính thức** nếu ghép được (ví dụ "Starlight Oath" thay vì "Wedding").
Với Enterprise, 10 trang phục chính ghép đúng, `Hot SpringsCN` dùng chung thoại với `Hot Springs`, còn
`Highspeed Etoile` (bộ mới, chưa có thoại) giữ thoại mặc định. Xem kết quả ghép của một nhân vật bằng:

```bat
python -m src.scraper "Enterprise"
```

Bảng "Thoại riêng theo trang phục" cho biết mỗi trang phục khớp với mục thoại nào (kèm số câu, số câu có giọng) và
liệt kê mục thoại chưa ghép được. Mục ghép bằng phỏng đoán theo thứ tự được đánh dấu `[ĐOÁN ...]` — nếu thấy sai với tàu nào, hãy gửi bảng này
để chỉnh; tạm thời có thể tắt bằng `skin_voice: false` (chỉ tắt phần tự nói khi đổi trang phục). Dữ liệu cache từ bản cũ được tự làm mới đúng một lần để lấy tên phụ.

## Menu chuột phải & icon khay hệ thống (dùng chung một menu)

Chọn nhân vật... · Trang phục tiếp theo [J] · Trang phục trước [K] · ☑ Luôn hiển thị trên cùng [T] ·
☑ Hiệu ứng lơ lửng [F] · ☑ Lật ngang nhân vật [S] · ☑ Chế độ Hover [F12] · Độ trong suốt ▸ ·
Thoại khi rảnh ▸ Tắt / 1 / 5 / 15 / 30 phút / 1 giờ · Ngôn ngữ ▸ Tiếng Việt / English ·
Mở thư mục dữ liệu · **Trợ giúp** · Thoát

## `config.yaml` (đặt cạnh file .exe, UTF-8)

```yaml
ship_name: Nagato         # tên tàu trên Wiki: Enterprise, Belfast, New Jersey, ...
skin_name: ''             # trang phục đang mặc (tự ghi khi đổi/thoát); trống = mặc định
language: vi              # vi | en
scale: 1                  # 1.0 ≈ cao 600 px (0.2 – 2.0)
floating: true
always_on_top: true
audio_volume: 50          # 0 = tắt tiếng (và không tải file âm thanh)
skin_voice: true          # tự nói câu thoại riêng của trang phục khi đổi trang phục
flipped: false
opacity: 1                # độ trong suốt của nhân vật (0.1 – 1.0)
hover_hotkey: F12         # phím tắt TOÀN CỤC bật/tắt Hover Mode
idle_voice_interval: 300  # giây không tương tác trước khi tự nói Task/Mail/Commission (0 = tắt)
```

**Lưu file là áp dụng ngay** (chương trình theo dõi file bằng `QFileSystemWatcher`, không polling).
Các thay đổi từ menu/phím tắt cũng được ghi ngược lại vào file này.

## Cập nhật nhanh (`update_and_build.bat`)

Để lên bản mới mà **không xoá thư mục dự án**: kéo file `.zip` bản cập nhật (bản đầy đủ, có `main.py` và `src\`)
lên biểu tượng `update_and_build.bat`; hoặc nhấp đúp rồi kéo/nhập đường dẫn khi được hỏi; hoặc chạy
`update_and_build.bat "đường\dẫn\bản-mới.zip"`. Script lần lượt:

1. **Sao lưu** `config.yaml` hiện có vào `backup\config_<ngày_giờ>.yaml` (không sao lưu được thì dừng ngay).
2. Giải nén vào thư mục tạm `.update_tmp\` (tự nhận cả zip có thư mục gốc `MoeMoeSecretary\`).
3. Đồng bộ mã nguồn bằng `robocopy /E`: `src\`, `assets\`, `tools\`, `tests\`, `main.py`, `MoeMoeSecretary.spec`,
   `requirements.txt`, `requirements-dev.txt`, `build_exe.bat`, `README.md`, `.gitignore`. Chỉ **ghi đè/thêm**, không xoá gì.
4. **Không bao giờ đụng tới** `config.yaml`, `cache\`, `dist\`, `.venv\` / `venv\`. Config mẫu của bản mới được lưu
   thành `config.yaml.new` để bạn đối chiếu các mục mới (các mục thiếu sẽ tự được bổ sung khi chương trình ghi lại file).
5. Kích hoạt môi trường ảo có sẵn (`.venv` hoặc `venv`; chưa có thì tạo `.venv`), chạy `pip install -q -r requirements.txt
   -r requirements-dev.txt`, xoá thư mục `build\` tạm rồi `pyinstaller --noconfirm --clean MoeMoeSecretary.spec` →
   `dist\MoeMoeSecretary.exe`.

Nên thoát ứng dụng trước khi chạy (file `.exe` đang mở không ghi đè được; script sẽ nhắc). Nếu bản cập nhật có
`update_and_build.bat` khác, bản mới được lưu thành `update_and_build.bat.new` (script không tự ghi đè lên chính nó
khi đang chạy) — đổi tên để dùng từ lần sau.

## Cấu trúc dự án

```
main.py                    điểm vào
config.yaml                cấu hình mẫu (bản chạy thật nằm cạnh .exe)
requirements.txt           thư viện chạy (requirements-dev.txt: pyinstaller, psutil)
build_exe.bat              build một cú nhấp chuột
update_and_build.bat       cập nhật mã nguồn từ file .zip rồi build lại .exe (giữ config.yaml, cache, .venv)
MoeMoeSecretary.spec       cấu hình PyInstaller (onefile, windowed, loại module thừa)
src/
  paths.py                 đường dẫn an toàn khi đóng băng (Path(sys.executable).parent)
  config.py                đọc/ghi config.yaml (UTF-8, tự tạo bản mặc định, có chú thích tiếng Việt)
  locales.py               từ điển vi/en siêu nhẹ
  models.py / errors.py    dataclass Ship/Skin/Quote, nhận diện tên mục thoại (voice_matches) và các lỗi
  scraper.py               bộ thu thập Azur Lane Wiki (fallback nhiều lớp)
  skinmatch.py             ghép trang phục <-> mục thoại riêng của nó
  cache.py                 cache ổ cứng + thu nhỏ ảnh bằng Pillow + tải trước trọn bộ giọng nói (dấu mốc)
  audio.py                 phát giọng nói bằng miniaudio
  workers.py               tác vụ nền (QThreadPool): hàng đợi chính 2 luồng, hàng đợi tải giọng nói 1 luồng, chống trùng key
  overlay.py               cửa sổ nhân vật (không viền, trong suốt, kéo thả, phím tắt, lơ lửng, độ mờ, Hover Mode)
  bubble.py                bong bóng thoại
  tray_menu.py             menu chuột phải + icon khay
  help_dialog.py           cửa sổ Trợ giúp
  controller.py            nối mọi thứ lại
  keyspec.py               đọc chuỗi phím tắt ("F12", "Ctrl+Alt+H") -> mã Windows (thuần Python)
  icons.py, winutil.py     icon vẽ bằng code; "luôn trên cùng", xuyên chuột, phím tắt toàn cục (user32)
tools/make_icon.py         sinh assets/icon.ico
tools/measure_resources.py đo RAM/CPU bằng psutil
tools/diagnose_wiki.py     chẩn đoán lỗi truy cập Wiki (403...)
tests/                     kiểm thử ngoại tuyến (scraper, luồng tải, config, locales, nhận diện thoại, tải trước giọng nói)
```

## Cách lấy dữ liệu từ Wiki

Các trang HTML của Wiki (`/wiki/...`) được bảo vệ bởi **Anubis** (thử thách JavaScript chống bot) nên chương
trình không đọc được chúng. Vì vậy mọi dữ liệu được lấy qua **MediaWiki API** (`/w/api.php`), giao diện
chính thức để chương trình đọc Wiki, rồi ảnh/giọng nói được tải từ máy chủ ảnh `azurlane.netojuu.com`.
Chương trình **không** cố giải hay vượt thử thách chống bot.

1. Tìm trang tàu: thử các biến thể tên (`new jersey` → `New Jersey`), theo chuyển hướng, rồi dự phòng bằng tìm
   kiếm gần đúng; xác nhận đó là trang tàu (dùng `Template:Ship` hoặc có trang con `/Quotes`, `/Gallery`).
2. **Câu thoại**: HTML của `<Tàu>/Quotes` (qua `action=parse`). Trang liệt kê lần lượt nhóm tiếng Anh, Trung,
   Nhật (mỗi nhóm lặp lại "Default Skin" + từng trang phục); chỉ lấy nhóm đầu (tiếng Anh), giữ nguyên lời gốc.
   Link giọng nói lấy từ cột *VO* (`.ogg`).
3. **Ảnh/trang phục**: HTML của trang chính và `<Tàu>/Gallery` — đọc từng tab trang phục, loại ảnh icon/chibi/nền
   (BG), đổi link thumbnail về ảnh gốc. Dự phòng cuối: tìm `File:<Tàu>.png` bằng API.
4. Mọi thứ được lưu vào `cache\` nên mỗi nhân vật chỉ tải một lần; ảnh trang phục chỉ tải khi bạn chuyển tới nó.
   Mỗi nhân vật mất khoảng 5–6 lần gọi API, tuần tự, chỉ một lần duy nhất.

Nếu Wiki đổi cấu trúc trang, chạy thử để xem chương trình thấy gì:

```bat
python -m src.scraper "Enterprise" --dump dump
```

Lệnh này in số trang phục/câu thoại tìm được và lưu HTML gốc vào thư mục `dump\` để chỉnh bộ chọn
trong `src/scraper.py` (`parse_quotes`, `parse_skins`).

## Vì sao nhẹ

| Ràng buộc | Cách thực hiện |
|---|---|
| RAM < 1 GB (mục tiêu 80–200 MB) | PySide6 gốc (không Electron/Chromium); chỉ giữ **một** pixmap trang phục đang hiển thị, đổi trang phục là giải phóng pixmap cũ + `gc.collect()`; nhập muộn `httpx`/`bs4`/`PIL`/`miniaudio` |
| Ảnh lớn | Ảnh Wiki (2000+ px) được cắt viền trong suốt và thu nhỏ ≤ 800 px bằng Pillow **trước** khi vào cache/giao diện |
| CPU ≈ 0 khi nghỉ | Hoàn toàn hướng sự kiện; chỉ có một timer 33 ms (30 FPS) khi bật lơ lửng, tắt hẳn khi tắt; cửa sổ chỉ di chuyển khi đổi pixel; thiết bị âm thanh chỉ mở lúc phát |
| Không đơ giao diện | Mạng + đọc/ghi file chạy trên luồng nền; kết quả cũ (do đổi nhân vật nhanh) bị bỏ qua; tải trước giọng nói chạy ở luồng riêng nên không làm chậm việc đổi trang phục |
| .exe gọn | `PySide6-Essentials`, `.spec` loại QtWebEngine/Qt3D/QtQuick/QtQml/matplotlib/numpy/scipy/pandas… và DLL OpenGL mềm |

Đo thực tế sau khi build: `python tools\measure_resources.py` (cộng cả hai tiến trình của bản `--onefile`).

## Xử lý sự cố

- **"Wiki từ chối truy cập (lỗi 403)"**: Wiki chặn client tự động. Ứng dụng chỉ dùng API chính thức và **không
  thử lại dồn dập** khi bị 403; nó cũng **không** cố vượt thử thách chống bot. Nếu API cũng bắt đầu bị chặn,
  chạy `.venv\Scripts\python.exe tools\diagnose_wiki.py` (cần chạy `build_exe.bat` ít nhất một lần để có `.venv`)
  rồi xem `wiki_diagnose.txt`; chi tiết phản hồi 403 cũng nằm trong `moe_moe_secretary.log`.
- **"Không kết nối được tới Wiki"**: kiểm tra mạng/tường lửa/proxy; lỗi tạm thời (429/5xx) được thử lại một lần.
- **Một thoại điều khiển (Start mission, Pledge...) không phát**: tên mục trên Wiki có thể khác dự kiến — chạy
  `python -m src.scraper "<Tàu>"` và xem mục *Mục thoại điều khiển* (xem phần trên).
- **Không có tiếng**: kiểm tra `audio_volume` > 0. `miniaudio` giải mã Vorbis/MP3/WAV/FLAC; file Opus sẽ bị bỏ qua (xem `moe_moe_secretary.log`).
- **Muốn tải lại dữ liệu một nhân vật**: xoá thư mục của nhân vật đó trong `cache\` (và dòng tương ứng trong `cache\index.json`, hoặc xoá cả `index.json`).
- **Antivirus báo nhầm file .exe** (thường gặp với PyInstaller `--onefile`): build từ mã nguồn trên máy bạn, hoặc dùng chế độ chạy từ mã nguồn ở trên.
- Nhật ký lỗi: `moe_moe_secretary.log` cạnh file .exe.

## Ghi chú

Dự án dùng dữ liệu công khai từ Azur Lane Wiki cho mục đích cá nhân; hình ảnh và giọng nói thuộc bản quyền
của Manjuu / Yongshi / Yostar. Chương trình chỉ tải mỗi thứ một lần rồi cache; đừng dùng nó để cào hàng loạt.
