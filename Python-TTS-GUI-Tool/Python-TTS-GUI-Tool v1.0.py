import tkinter as tk
from tkinter import ttk, messagebox
import pyttsx3
from gtts import gTTS
import edge_tts
import pygame
import asyncio
import threading
import io
from collections import defaultdict

# --- 全域設定 ---

# 初始化 pygame mixer
pygame.mixer.init()

# 內建示範文本
TEXT_SAMPLES = {
    "Chinese": "人生充滿了各種哲理，如果可以內化這些人生的道理。",
    "English": "A bird in hand is worth two in the bush.",
    "Japanese": "今日は関東で冷たい雨が降り、山では雪が降っています。"
}

# 用於儲存 Edge TTS 語音的結構化字典
# 結構: {語言群組: {地區/口音: {性別: [語音名稱]}}}
# 例如: {'中文': {'台灣 zh-TW': {'Female': ['zh-TW-HsiaoChenNeural', ...]}}}
edge_tts_voices = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

# --- 核心語音功能 ---

def play_audio_from_memory(audio_bytes):
    """從記憶體中的 bytes 直接播放音訊"""
    try:
        # 使用 io.BytesIO 創建一個記憶體中的二進位檔案
        audio_fp = io.BytesIO(audio_bytes)
        pygame.mixer.music.load(audio_fp, 'mp3')
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.delay(100)
    except pygame.error as e:
        messagebox.showerror("播放錯誤", f"無法播放音訊： {e}")
    finally:
        # 播放完畢後卸載，以便下次播放
        pygame.mixer.music.unload()

def speak_pyttsx3(text, voice_id):
    """使用 pyttsx3 播放語音 (本身就不產生檔案)"""
    try:
        engine = pyttsx3.init()
        engine.setProperty('voice', voice_id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        messagebox.showerror("pyttsx3 錯誤", f"無法初始化或播放語音：\n{e}")

def speak_gtts(text, lang_code):
    """使用 gTTS 生成語音並從記憶體播放"""
    try:
        # 將 gTTS 的輸出直接寫入記憶體
        audio_fp = io.BytesIO()
        tts = gTTS(text=text, lang=lang_code)
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0) # 指到檔案開頭
        play_audio_from_memory(audio_fp.read())
    except Exception as e:
        messagebox.showerror("gTTS 錯誤", f"無法生成語音：\n{e}")

async def _edge_tts_task(text, voice):
    """非同步執行 Edge TTS 語音合成到記憶體"""
    try:
        audio_bytes = b""
        communicate = edge_tts.Communicate(text, voice)
        # 使用 stream() 方法獲取音訊流
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        if audio_bytes:
            play_audio_from_memory(audio_bytes)
        else:
            raise ValueError("未生成任何音訊資料")

    except Exception as e:
        messagebox.showerror("Edge TTS 錯誤", f"無法生成語音：\n{e}")

def speak_edge_tts(text, voice):
    """啟動 Edge TTS 語音合成任務"""
    def run_async_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_edge_tts_task(text, voice))
        loop.close()
    threading.Thread(target=run_async_task).start()

# --- GUI 應用程式 ---

class TTS_App:
    def __init__(self, root):
        self.root = root
        self.root.title("語音合成測試器 v1.0")
        self.root.geometry("480x600")

        # --- 資料變數 ---
        self.engine_var = tk.StringVar(value="Edge TTS")
        self.text_lang_var = tk.StringVar(value="Chinese")
        
        # Edge TTS 階層式選單變數
        self.edge_lang_group_var = tk.StringVar()
        self.edge_region_var = tk.StringVar()
        self.edge_gender_var = tk.StringVar()
        self.edge_voice_var = tk.StringVar()

        # --- 介面框架 ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.create_engine_selector(main_frame).pack(fill=tk.X, pady=5)
        self.create_text_selector(main_frame).pack(fill=tk.X, pady=5)
        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10, padx=5)

        self.options_frame = ttk.Frame(main_frame)
        self.options_frame.pack(fill=tk.X, expand=True)
        
        ttk.Button(main_frame, text="▶ 播放語音", command=self.on_speak, style="Accent.TButton").pack(pady=10, ipady=5, fill=tk.X, padx=5)
        root.style = ttk.Style(root)
        root.style.configure("Accent.TButton", font=('Helvetica', 10, 'bold'))

        # --- 初始化 ---
        self.engine_var.trace_add("write", self.update_options_ui)
        self.text_lang_var.trace_add("write", self.update_text_display)
        self.load_edge_voices()

    def load_edge_voices(self):
        """非同步載入並建構 Edge TTS 語音字典"""
        def fetch():
            lang_map = {'zh': '中文', 'en': '英文', 'ja': '日文'}
            region_map = {
                'CN': '中國', 'TW': '台灣', 'HK': '香港',
                'US': '美國', 'GB': '英國', 'AU': '澳洲', 'CA': '加拿大', 'IN': '印度'
            }

            async def get_voices():
                global edge_tts_voices
                try:
                    voices = await edge_tts.VoicesManager.create()
                    for voice in voices.voices:
                        locale_parts = voice['Locale'].split('-')
                        lang_code, region_code = locale_parts[0], locale_parts[1]
                        
                        lang_group = lang_map.get(lang_code, lang_code)
                        region_name = region_map.get(region_code, region_code)
                        full_region_name = f"{region_name} ({voice['Locale']})"
                        gender = voice['Gender']
                        
                        edge_tts_voices[lang_group][full_region_name][gender].append(voice['ShortName'])

                    self.root.after(0, self.update_options_ui)
                except Exception as e:
                    messagebox.showwarning("Edge TTS 載入失敗", f"無法獲取線上語音列表，請檢查網路連線。\n{e}")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_voices())

        threading.Thread(target=fetch, daemon=True).start()

    def create_engine_selector(self, parent):
        frame = ttk.LabelFrame(parent, text="1. 選擇 TTS 引擎")
        engines = ["Edge TTS", "gTTS", "pyttsx3"]
        for engine in engines:
            ttk.Radiobutton(frame, text=engine, variable=self.engine_var, value=engine).pack(anchor=tk.W, padx=10, pady=2)
        return frame

    def create_text_selector(self, parent):
        frame = ttk.LabelFrame(parent, text="2. 選擇或輸入測試語句")
        for lang, text in TEXT_SAMPLES.items():
            rb = ttk.Radiobutton(frame, text=f"{lang}", variable=self.text_lang_var, value=lang)
            rb.pack(anchor=tk.W, padx=10)
        
        self.text_display = tk.Text(frame, height=4, wrap=tk.WORD, relief="solid", borderwidth=1, font=('Segoe UI', 9))
        self.text_display.pack(fill=tk.X, padx=10, pady=(5,10))
        self.update_text_display()
        return frame

    def update_text_display(self, *args):
        text = TEXT_SAMPLES.get(self.text_lang_var.get(), "")
        self.text_display.delete("1.0", tk.END)
        self.text_display.insert("1.0", text)

    def update_options_ui(self, *args):
        for widget in self.options_frame.winfo_children():
            widget.destroy()

        engine = self.engine_var.get()
        frame = ttk.LabelFrame(self.options_frame, text=f"3. {engine} 設定")
        frame.pack(fill=tk.X, pady=5)

        if engine == "Edge TTS":
            self.create_edge_tts_options(frame)
        elif engine == "gTTS":
            self.create_gtts_options(frame)
        elif engine == "pyttsx3":
            self.create_pyttsx3_options(frame)

    def create_edge_tts_options(self, parent):
        """建立 Edge TTS 的階層式選項介面"""
        # 1. 語言群組
        ttk.Label(parent, text="語言:").pack(anchor=tk.W, padx=10)
        self.edge_lang_group_combo = ttk.Combobox(parent, textvariable=self.edge_lang_group_var, values=sorted(edge_tts_voices.keys()), state="readonly")
        self.edge_lang_group_combo.pack(fill=tk.X, padx=10, pady=2)
        self.edge_lang_group_combo.bind("<<ComboboxSelected>>", self.update_edge_regions)

        # 2. 口音/地區
        ttk.Label(parent, text="口音/地區:").pack(anchor=tk.W, padx=10)
        self.edge_region_combo = ttk.Combobox(parent, textvariable=self.edge_region_var, state="disabled")
        self.edge_region_combo.pack(fill=tk.X, padx=10, pady=2)
        self.edge_region_combo.bind("<<ComboboxSelected>>", self.update_edge_genders)

        # 3. 性別
        ttk.Label(parent, text="性別:").pack(anchor=tk.W, padx=10)
        self.edge_gender_combo = ttk.Combobox(parent, textvariable=self.edge_gender_var, state="disabled")
        self.edge_gender_combo.pack(fill=tk.X, padx=10, pady=2)
        self.edge_gender_combo.bind("<<ComboboxSelected>>", self.update_edge_voices)

        # 4. 語音
        ttk.Label(parent, text="語音:").pack(anchor=tk.W, padx=10)
        self.edge_voice_combo = ttk.Combobox(parent, textvariable=self.edge_voice_var, state="disabled")
        self.edge_voice_combo.pack(fill=tk.X, padx=10, pady=2)

        # 預設選取
        if '中文' in edge_tts_voices:
            self.edge_lang_group_combo.set('中文')
            self.update_edge_regions()

    def update_edge_regions(self, event=None):
        lang_group = self.edge_lang_group_var.get()
        regions = sorted(edge_tts_voices.get(lang_group, {}).keys())
        self.edge_region_combo['values'] = regions
        self.edge_region_combo.config(state="readonly" if regions else "disabled")
        if regions:
            self.edge_region_combo.set(regions[0])
            self.update_edge_genders()
        else:
            self.edge_gender_combo.set('')
            self.edge_voice_combo.set('')
            self.edge_gender_combo.config(state="disabled")
            self.edge_voice_combo.config(state="disabled")

    def update_edge_genders(self, event=None):
        lang_group = self.edge_lang_group_var.get()
        region = self.edge_region_var.get()
        genders = sorted(edge_tts_voices.get(lang_group, {}).get(region, {}).keys())
        self.edge_gender_combo['values'] = genders
        self.edge_gender_combo.config(state="readonly" if genders else "disabled")
        if genders:
            self.edge_gender_combo.set(genders[0])
            self.update_edge_voices()
        else:
            self.edge_voice_combo.set('')
            self.edge_voice_combo.config(state="disabled")

    def update_edge_voices(self, event=None):
        lang_group = self.edge_lang_group_var.get()
        region = self.edge_region_var.get()
        gender = self.edge_gender_var.get()
        voices = sorted(edge_tts_voices.get(lang_group, {}).get(region, {}).get(gender, []))
        self.edge_voice_combo['values'] = voices
        self.edge_voice_combo.config(state="readonly" if voices else "disabled")
        if voices:
            self.edge_voice_combo.set(voices[0])
        else:
            self.edge_voice_combo.set('')

    def create_gtts_options(self, parent):
        """建立 gTTS 的選項介面"""
        ttk.Label(parent, text="語言:").pack(anchor=tk.W, padx=10)
        gtts_options = {"中文 (台灣)": "zh-tw", "中文 (中國)": "zh-cn", "日文": "ja", "英文": "en"}
        self.gtts_lang_combo = ttk.Combobox(parent, values=list(gtts_options.keys()), state="readonly")
        self.gtts_lang_combo.pack(fill=tk.X, padx=10, pady=5)
        self.gtts_lang_combo.set("中文 (台灣)")
        self.gtts_lang_map = gtts_options

    def create_pyttsx3_options(self, parent):
        """建立 pyttsx3 的選項介面"""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            engine.stop()
            self.pyttsx3_voice_ids = {v.name: v.id for v in voices}
            voice_names = list(self.pyttsx3_voice_ids.keys())

            ttk.Label(parent, text="已安裝的語音:").pack(anchor=tk.W, padx=10)
            self.pyttsx3_voice_combo = ttk.Combobox(parent, values=voice_names, state="readonly")
            self.pyttsx3_voice_combo.pack(fill=tk.X, padx=10, pady=5)
            if voice_names:
                self.pyttsx3_voice_combo.set(voice_names[0])
        except Exception:
            ttk.Label(parent, text="無法載入 pyttsx3 語音 (可能未安裝)", foreground="red").pack(padx=10, pady=5)

    def on_speak(self):
        text = self.text_display.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("警告", "請先輸入或選擇要朗讀的文字。")
            return
        
        if pygame.mixer.music.get_busy():
            messagebox.showwarning("提示", "正在播放音訊，請稍後...")
            return

        engine = self.engine_var.get()
        if engine == "Edge TTS":
            voice = self.edge_voice_var.get()
            if voice: speak_edge_tts(text, voice)
        elif engine == "gTTS":
            lang_name = self.gtts_lang_combo.get()
            if lang_name: speak_gtts(text, self.gtts_lang_map[lang_name])
        elif engine == "pyttsx3":
            voice_name = self.pyttsx3_voice_combo.get()
            if voice_name: speak_pyttsx3(text, self.pyttsx3_voice_ids[voice_name])

if __name__ == "__main__":
    root = tk.Tk()
    app = TTS_App(root)
    root.mainloop()