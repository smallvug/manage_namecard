#!/usr/bin/env python3
"""
명함 사진 정리 GUI 프로그램

사용법: python manage_gui.py
필요:   pip install anthropic Pillow python-dotenv
"""

import json
import shutil
import base64
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import anthropic
from dotenv import load_dotenv
from PIL import Image, ImageTk
from PIL.ExifTags import TAGS

load_dotenv()

DATA_DIR = Path("_data")
OUTPUT_DIR = Path("_processed")
IMG_EXTS = {".JPG", ".JPEG", ".PNG"}
WINDOW_POS_FILE = Path(".window_pos.json")


# ── 공통 헬퍼 ────────────────────────────────────────────────

def get_photo_date(path: Path) -> str:
    try:
        exif = Image.open(path)._getexif()
        if exif:
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == "DateTimeOriginal":
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S").strftime("%Y.%m.%d")
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y.%m.%d")


def to_base64(path: Path) -> tuple[str, str]:
    media_type = "image/png" if path.suffix.upper() == ".PNG" else "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return data, media_type


def analyze_namecard(client: anthropic.Anthropic, photos: list[Path]) -> str:
    content = []
    for photo in photos:
        data, mt = to_base64(photo)
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    content.append({"type": "text", "text": """이 사진이 명함이면 폴더명을 만들어주세요.
명함이 아니면 "UNKNOWN" 이라고만 출력하세요.

형식: [이름], [기관명], [직책]
규칙:
- 영문/중문 이름: 성(대문자) 이름  예) GLASS John, FEI Qiang
- 한국어 이름: 성 이름  예) 강 남규, 구 옥재
- 기관 내 부서/학과가 있으면 콤마로 추가
  예) FEI Qiang, Xian Jiaotong University, School of Chemical Engineering and Technology, Professor
- 직책이 없으면 기관명까지만

폴더명 한 줄만 출력하세요. 다른 설명 없이."""})

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": content}],
    )
    return resp.content[0].text.strip()


def check_is_back(client: anthropic.Anthropic, front: Path, candidate: Path) -> bool:
    """두 사진이 같은 명함의 앞면/뒷면인지 확인"""
    content = []
    for p in [front, candidate]:
        data, mt = to_base64(p)
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    content.append({"type": "text", "text": "두 사진이 같은 명함의 앞면과 뒷면입니까? '예' 또는 '아니오'로만 답하세요."})
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": content}],
    )
    return resp.content[0].text.strip().startswith("예")


def sanitize(name: str) -> str:
    # 줄바꿈 및 제어문자 제거
    name = name.splitlines()[0] if name else ""
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")
    name = name.strip()
    # Windows 경로 최대 길이 고려해 100자 제한
    return name[:100]


def next_file_num(folder: Path, date: str) -> int:
    n = 1
    prefix = f"[{date}] 명함 "
    for f in folder.iterdir():
        if f.name.startswith(prefix):
            try:
                rest = f.name[len(prefix):]
                n = max(n, int(rest.split(".")[0]) + 1)
            except ValueError:
                pass
    return n


def copy_photos(front: Path, back: Path | None, folder_name: str) -> Path:
    dest = OUTPUT_DIR / folder_name
    dest.mkdir(parents=True, exist_ok=True)
    date = get_photo_date(front)
    num = next_file_num(dest, date)
    shutil.copy2(front, dest / f"[{date}] 명함 {num}{front.suffix.upper()}")
    if back:
        shutil.copy2(back, dest / f"[{date}] 명함 {num + 1}{back.suffix.upper()}")
    return dest


def resolve_back(images: list[Path], back_input: str) -> Path | None:
    try:
        idx = int(back_input) - 1
        if 0 <= idx < len(images):
            return images[idx]
    except ValueError:
        pass
    candidate = DATA_DIR / back_input
    if candidate.exists():
        return candidate
    return None


# ── GUI ──────────────────────────────────────────────────────

class NamecardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("명함 정리")
        self.root.minsize(900, 600)
        self._restore_window_pos()
        self.root.protocol("WM_DELETE_WINDOW", self._save_window_pos)

        self.client = anthropic.Anthropic()
        self.images = sorted(p for p in DATA_DIR.iterdir() if p.suffix.upper() in IMG_EXTS)
        self.used_as_back: set[Path] = set()
        self.current_idx = 0
        self._photo_ref = None   # GC 방지
        self._photo_ref2 = None
        self._current_path: Path | None = None
        self._detected_back: Path | None = None
        self._last_folder_name: str | None = None

        self._build_ui()
        if self.images:
            self.root.after(100, self._load_next)
        else:
            self._log("_data/ 폴더에 이미지가 없습니다.")

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self):
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=6,
                               sashrelief=tk.RAISED, bg="#ccc")
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left = ttk.Frame(paned, width=360)
        right = ttk.Frame(paned)
        paned.add(left, minsize=300)
        paned.add(right, minsize=400)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        parent.columnconfigure(0, weight=1)

        r = 0

        # 이미지 목록
        ttk.Label(parent, text="이미지 목록", font=("", 9, "bold")).grid(
            row=r, column=0, sticky="w", padx=10, pady=(10, 2))
        r += 1

        list_frame = ttk.Frame(parent)
        list_frame.grid(row=r, column=0, sticky="nsew", padx=10)
        parent.rowconfigure(r, weight=2)

        sb = ttk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(list_frame, yscrollcommand=sb.set, height=10,
                                  selectmode=tk.SINGLE, activestyle="none",
                                  font=("Consolas", 9))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self.listbox.yview)
        for i, img in enumerate(self.images):
            self.listbox.insert(tk.END, f"{i+1:2}. {img.name}")

        r += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=r, column=0, sticky="ew", padx=10, pady=6)
        r += 1

        # 상태
        self.status_var = tk.StringVar(value="대기 중")
        ttk.Label(parent, textvariable=self.status_var, foreground="#555",
                  font=("", 9, "italic")).grid(row=r, column=0, sticky="w", padx=10)
        r += 1

        # 폴더명
        ttk.Label(parent, text="폴더명", font=("", 9, "bold")).grid(
            row=r, column=0, sticky="w", padx=10, pady=(10, 2))
        r += 1

        self.folder_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.folder_var, font=("", 10)).grid(
            row=r, column=0, sticky="ew", padx=10)
        r += 1

        # 뒷면 번호
        ttk.Label(parent, text="뒷면 번호  (없으면 비워두기)", font=("", 9, "bold")).grid(
            row=r, column=0, sticky="w", padx=10, pady=(10, 2))
        r += 1

        self.back_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.back_var, width=12).grid(
            row=r, column=0, sticky="w", padx=10)
        r += 1

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=r, column=0, sticky="ew", padx=10, pady=10)
        r += 1

        # 버튼
        btn = ttk.Frame(parent)
        btn.grid(row=r, column=0, padx=10, sticky="ew")
        self.save_btn = ttk.Button(btn, text="💾  저장", command=self._on_save, width=12)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.add_btn = ttk.Button(btn, text="📂  뒷면 추가", command=self._on_add_to_existing, width=12)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.skip_btn = ttk.Button(btn, text="→  건너뜀", command=self._on_skip, width=12)
        self.skip_btn.pack(side=tk.LEFT)
        self.save_btn.config(state=tk.DISABLED)
        r += 1

        # 로그
        ttk.Label(parent, text="처리 로그", font=("", 9, "bold")).grid(
            row=r, column=0, sticky="w", padx=10, pady=(12, 2))
        r += 1

        log_frame = ttk.Frame(parent)
        log_frame.grid(row=r, column=0, sticky="nsew", padx=10, pady=(0, 8))
        parent.rowconfigure(r, weight=1)

        log_sb = ttk.Scrollbar(log_frame)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_box = tk.Text(log_frame, height=6, state=tk.DISABLED,
                               yscrollcommand=log_sb.set, wrap=tk.WORD,
                               font=("Consolas", 9), bg="#f8f8f8")
        self.log_box.pack(fill=tk.BOTH, expand=True)
        log_sb.config(command=self.log_box.yview)

    def _build_right(self, parent):
        self.canvas = tk.Canvas(parent, bg="#e8e8e8", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", lambda e: self._redraw_image())

    # ── 로그 ─────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)

    # ── 창 위치 저장/복원 ────────────────────────────────────

    def _restore_window_pos(self):
        """저장된 위치·크기 복원, 없으면 화면 정중앙"""
        try:
            pos = json.loads(WINDOW_POS_FILE.read_text(encoding="utf-8"))
            self.root.geometry(f"{pos['w']}x{pos['h']}+{pos['x']}+{pos['y']}")
        except Exception:
            w, h = 1200, 720
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _save_window_pos(self):
        """닫기 전 창 위치·크기 저장"""
        try:
            pos = {
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
                "w": self.root.winfo_width(),
                "h": self.root.winfo_height(),
            }
            WINDOW_POS_FILE.write_text(json.dumps(pos), encoding="utf-8")
        except Exception:
            pass
        self.root.destroy()

    # ── 이미지 표시 ───────────────────────────────────────────

    def _show_image(self, path: Path):
        self._current_path = path
        self._detected_back = None
        self._photo_ref2 = None
        self._redraw_image()

    def _redraw_image(self):
        if not self._current_path:
            return
        try:
            cw = max(self.canvas.winfo_width(), 100)
            ch = max(self.canvas.winfo_height(), 100)
            self.canvas.delete("all")

            if self._detected_back:
                # 앞면 위 / 뒷면 아래로 표시
                half_h = (ch - 20) // 2
                img1 = Image.open(self._current_path)
                img1.thumbnail((cw - 16, half_h - 4), Image.LANCZOS)
                img2 = Image.open(self._detected_back)
                img2.thumbnail((cw - 16, half_h - 4), Image.LANCZOS)
                self._photo_ref = ImageTk.PhotoImage(img1)
                self._photo_ref2 = ImageTk.PhotoImage(img2)
                self.canvas.create_text(8, 4, text="앞면", font=("", 8), fill="#888", anchor=tk.NW)
                self.canvas.create_image(cw // 2, half_h // 2, anchor=tk.CENTER, image=self._photo_ref)
                self.canvas.create_line(8, half_h + 10, cw - 8, half_h + 10, fill="#bbb", dash=(4, 4))
                self.canvas.create_text(8, half_h + 14, text="뒷면", font=("", 8), fill="#888", anchor=tk.NW)
                self.canvas.create_image(cw // 2, half_h + 20 + half_h // 2, anchor=tk.CENTER, image=self._photo_ref2)
            else:
                img = Image.open(self._current_path)
                img.thumbnail((cw - 16, ch - 16), Image.LANCZOS)
                self._photo_ref = ImageTk.PhotoImage(img)
                self.canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=self._photo_ref)
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(200, 200, text=f"이미지 로드 실패\n{e}", fill="red")

    # ── 흐름 제어 ─────────────────────────────────────────────

    def _load_next(self):
        """다음 미처리 이미지로 이동"""
        while self.current_idx < len(self.images):
            if self.images[self.current_idx] not in self.used_as_back:
                break
            self.current_idx += 1

        if self.current_idx >= len(self.images):
            self._log("✅ 모든 이미지 처리 완료!")
            self.status_var.set("완료")
            self.save_btn.config(state=tk.DISABLED)
            self.skip_btn.config(state=tk.DISABLED)
            return

        front = self.images[self.current_idx]
        self.folder_var.set("")
        self.back_var.set("")
        self._detected_back = None
        self.save_btn.config(state=tk.DISABLED)
        self.status_var.set(f"분석 중...  {front.name}")

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.current_idx)
        self.listbox.see(self.current_idx)

        # 바로 다음 미처리 이미지를 peek (뒷면 후보)
        peek = None
        peek_idx = self.current_idx + 1
        while peek_idx < len(self.images):
            if self.images[peek_idx] not in self.used_as_back:
                peek = self.images[peek_idx]
                break
            peek_idx += 1

        self._show_image(front)
        threading.Thread(target=self._analyze, args=(front, peek), daemon=True).start()

    def _analyze(self, front: Path, peek: Path | None):
        try:
            name = analyze_namecard(self.client, [front])
            folder_name = sanitize(name)
            detected_back = None
            if peek:
                try:
                    if check_is_back(self.client, front, peek):
                        detected_back = peek
                except Exception:
                    pass
            self.root.after(0, self._on_analyzed, folder_name, detected_back)
        except Exception as e:
            self.root.after(0, self._on_error, str(e))

    def _on_analyzed(self, folder_name: str, detected_back: Path | None):
        if folder_name.upper() == "UNKNOWN":
            self.folder_var.set("")
            self.status_var.set("⚠️ 명함을 인식하지 못했습니다. 직접 입력하세요.")
        else:
            self.folder_var.set(folder_name)
            status = f"분석 완료  ·  {self.images[self.current_idx].name}"
            if detected_back:
                self._detected_back = detected_back
                try:
                    back_num = self.images.index(detected_back) + 1
                    self.back_var.set(str(back_num))
                except ValueError:
                    pass
                self._redraw_image()   # 두 이미지로 다시 그리기
                status += "  ·  뒷면 감지됨 ✓"
            self.status_var.set(status)
        self.save_btn.config(state=tk.NORMAL)

    def _on_error(self, error: str):
        self.status_var.set("오류 발생")
        self._log(f"❌ {error}")
        self.save_btn.config(state=tk.NORMAL)

    # ── 저장 / 건너뜀 ─────────────────────────────────────────

    def _on_save(self):
        folder_name = sanitize(self.folder_var.get().strip())
        if not folder_name:
            messagebox.showwarning("경고", "폴더명을 입력하세요.")
            return

        front = self.images[self.current_idx]
        back = None

        back_input = self.back_var.get().strip()
        if back_input:
            back = resolve_back(self.images, back_input)
            if back is None:
                messagebox.showerror("오류", f"'{back_input}' 을 찾을 수 없습니다.")
                return
            self.used_as_back.add(back)

        try:
            dest = copy_photos(front, back, folder_name)
        except Exception as e:
            messagebox.showerror("저장 오류", str(e))
            return

        self._last_folder_name = folder_name
        back_info = f" + {back.name}" if back else ""
        self._log(f"✓ {dest.name}{back_info}")

        self.listbox.itemconfig(self.current_idx, fg="#aaa")
        if back and back in self.images:
            self.listbox.itemconfig(self.images.index(back), fg="#ccc")

        self.current_idx += 1
        self._load_next()

    def _on_skip(self):
        self._log(f"→ 건너뜀: {self.images[self.current_idx].name}")
        self.current_idx += 1
        self._load_next()

    def _on_add_to_existing(self):
        """현재 이미지를 기존 폴더에 추가 (뒷면 처리)"""
        if not OUTPUT_DIR.exists():
            messagebox.showinfo("알림", "_processed/ 폴더가 없습니다.")
            return

        folders = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())
        if not folders:
            messagebox.showinfo("알림", "저장된 폴더가 없습니다.")
            return

        front = self.images[self.current_idx]
        self._pick_folder_dialog(folders, front)

    def _pick_folder_dialog(self, folders: list[str], photo: Path):
        """폴더 선택 다이얼로그 – 메인 창 가운데, 이전 폴더 볼드·선택"""
        dlg = tk.Toplevel(self.root)
        dlg.title("폴더 선택")
        dlg.transient(self.root)
        dlg.grab_set()

        # 크기 확정 후 메인 창 가운데 배치
        w, h = 480, 420
        dlg.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        ttk.Label(dlg, text="추가할 폴더를 선택하세요:", font=("", 9, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        frame = ttk.Frame(dlg)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        sb = ttk.Scrollbar(frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tree = ttk.Treeview(frame, yscrollcommand=sb.set, show="tree",
                            selectmode="browse", height=16)
        tree.pack(fill=tk.BOTH, expand=True)
        sb.config(command=tree.yview)

        tree.tag_configure("recent", font=("", 9, "bold"))
        tree.tag_configure("normal", font=("", 9))

        last = self._last_folder_name
        last_iid = None
        for f in folders:
            tag = "recent" if f == last else "normal"
            iid = tree.insert("", tk.END, text=f, tags=(tag,))
            if f == last:
                last_iid = iid

        # 이전 폴더(또는 첫 항목) 미리 선택
        target = last_iid or (tree.get_children()[0] if tree.get_children() else None)
        if target:
            tree.selection_set(target)
            tree.see(target)

        def on_ok():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("선택 없음", "폴더를 선택하세요.", parent=dlg)
                return
            folder_name = tree.item(sel[0], "text")
            dest = OUTPUT_DIR / folder_name
            date = get_photo_date(photo)
            num = next_file_num(dest, date)
            shutil.copy2(photo, dest / f"[{date}] 명함 {num}{photo.suffix.upper()}")
            self._log(f"📎 {folder_name} ← 명함 {num} ({photo.name})")
            self.listbox.itemconfig(self.current_idx, fg="#aaa")
            self._last_folder_name = folder_name
            dlg.destroy()
            self.current_idx += 1
            self._load_next()

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="추가", command=on_ok, width=12).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="취소", command=dlg.destroy, width=12).pack(side=tk.LEFT)


# ── 진입점 ───────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    root = tk.Tk()
    NamecardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
