# Auto subtitle generator

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk
import concurrent.futures
import speech_recognition as sr
from pydub import AudioSegment
from deep_translator import GoogleTranslator
from datetime import timedelta
import queue
import time

# Dictionary to map language names to language codes for both source and target
LANGUAGES = {
    "English": "en",
    "Urdu": "ur",
    "Turkish": "tr",
    "German": "de",
    "Spanish": "es",
    "French": "fr",
    "Arabic": "ar",
    "Hindi": "hi",
    "Chinese": "zh-CN",
    "Japanese": "ja",
    "Russian": "ru",
    "Polish": "pl",
}

# Define a class to encapsulate the subtitle generation process.
class SRTAudioGenerator:
    """
    Generates a single SRT subtitle file from a video/audio file.
    """
    def __init__(self, media_file_path, target_language_name, source_language_code):
        """
        Initializes the generator with a media file path and the target/source languages.
        
        Args:
            media_file_path (str): The path to the video or audio file.
            target_language_name (str): The name of the language to translate to.
            source_language_code (str): The language code of the audio in the video.
        """
        if not os.path.exists(media_file_path):
            raise FileNotFoundError(f"Error: The media file was not found at '{media_file_path}'")
        
        self.media_file_path = media_file_path
        self.recognizer = sr.Recognizer()
        self.target_language_name = target_language_name
        self.source_language_code = source_language_code
        self.target_language_code = LANGUAGES[target_language_name]

    def _format_time(self, milliseconds):
        """
        Formats milliseconds into SRT timecode format (HH:MM:SS,mmm).
        
        Args:
            milliseconds (int): The time in milliseconds.
            
        Returns:
            str: The formatted time string.
        """
        td = timedelta(milliseconds=milliseconds)
        seconds = td.total_seconds()
        hours, remainder = divmod(seconds, 3600)
        minutes, remainder = divmod(remainder, 60)
        seconds, milliseconds = divmod(remainder, 1)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02},{int(milliseconds*1000):03}"

    def _transcribe_chunk(self, chunk_data):
        """
        Transcribes a single audio chunk in a separate thread.
        Returns a dictionary with transcription result and metadata.
        """
        chunk_index, chunk_segment = chunk_data
        temp_wav_path = f"chunk_{chunk_index}.wav"
        chunk_segment.export(temp_wav_path, format="wav")
        
        transcribed_text = None
        
        try:
            with sr.AudioFile(temp_wav_path) as source:
                audio_data = self.recognizer.record(source)
            # Use the selected source language for transcription
            transcribed_text = self.recognizer.recognize_google(audio_data, language=self.source_language_code)
        except sr.UnknownValueError:
            transcribed_text = "(No speech detected)"
        except Exception as e:
            transcribed_text = f"Error: {e}"
        finally:
            if os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)

        return {
            "index": chunk_index,
            "transcribed_text": transcribed_text,
            "duration": len(chunk_segment)
        }

    def _split_and_translate(self, text, max_chars=4500):
        """
        Splits a long text into smaller pieces and translates each piece.
        This prevents the 5000-character limit error.
        """
        if not text or text == "(No speech detected)":
            return ""
        
        translator = GoogleTranslator(source=self.source_language_code, target=self.target_language_code)

        if len(text) <= max_chars:
            return translator.translate(text)

        # Split the text into smaller chunks
        chunks = []
        start = 0
        while start < len(text):
            end = start + max_chars
            # Try to split at a natural boundary like a space
            if end < len(text) and text[end] != ' ':
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start:
                    end = last_space
            chunks.append(text[start:end].strip())
            start = end

        translated_chunks = []
        for chunk in chunks:
            if chunk:
                translated_chunks.append(translator.translate(chunk))
        
        return " ".join(translated_chunks)

    def generate_subtitles(self, progress_callback=None, edit_callback=None):
        """
        Main method to generate the SRT file using parallel processing.
        
        Args:
            progress_callback (function): A function to update progress in the GUI.
            edit_callback (function): A function to call for user-editable transcription.
        """
        if progress_callback:
            progress_callback("Loading video/audio file...", 0)
        
        try:
            audio = AudioSegment.from_file(self.media_file_path)
        except Exception as e:
            if progress_callback:
                progress_callback(f"Error loading media file. Make sure FFmpeg is installed and in your PATH: {e}", 0)
            return

        # Use 5-second chunks to prevent initial transcription from being too long
        chunk_length_ms = 5000
        chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
        
        # Phase 1: Parallel Transcription
        progress_callback("Phase 1/2: Transcribing all audio chunks...", 0)
        transcriptions = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_chunk = {
                executor.submit(self._transcribe_chunk, (i, chunk)): i
                for i, chunk in enumerate(chunks)
            }
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_chunk)):
                try:
                    transcription_data = future.result()
                    # We now append all transcription results, even if no speech was detected.
                    if transcription_data:
                        transcriptions.append(transcription_data)
                except Exception as exc:
                    print(f"Generated an exception: {exc}")
                
                progress_value = int((i + 1) / len(chunks) * 50) # Use 50% for this phase
                progress_callback(f"Transcribing chunk {i + 1}/{len(chunks)}...", progress_value)
        
        transcriptions.sort(key=lambda x: x["index"])

        # Phase 2: Sequential Editing, Translation, and Writing
        progress_callback("Phase 2/2: Reviewing and translating...", 50)
        
        base_name = os.path.splitext(os.path.basename(self.media_file_path))[0]
        output_srt_path = f"{base_name}_{self.target_language_name}.srt"
        
        subtitle_index = 1
        current_time_ms = 0
        yes_all_clicked = False

        with open(output_srt_path, "w", encoding="utf-8") as srt_file:
            for i, data in enumerate(transcriptions):
                if not yes_all_clicked:
                    # Get initial translations
                    initial_translations = {
                        "Source (" + self.source_language_code + ")": data["transcribed_text"],
                        "Target (" + self.target_language_name + ")": self._split_and_translate(data["transcribed_text"])
                    }
                    
                    # Get the corrected text from the user and the flag
                    final_texts, yes_all_clicked = edit_callback(initial_translations)
                else:
                    # If "Yes All" was clicked, just use the automatic translations
                    final_texts = {
                        "Target (" + self.target_language_name + ")": self._split_and_translate(data["transcribed_text"])
                    }

                start_time = self._format_time(current_time_ms)
                end_time = self._format_time(current_time_ms + data["duration"])
                
                # Write the single subtitle block
                srt_file.write(f"{subtitle_index}\n")
                srt_file.write(f"{start_time} --> {end_time}\n")
                
                # Use the corrected target text
                target_text = final_texts.get("Target (" + self.target_language_name + ")", "")
                srt_file.write(f"{target_text}\n\n")
                
                subtitle_index += 1
                
                progress_value = 50 + int((i + 1) / len(transcriptions) * 50)
                progress_callback(f"Reviewing and translating chunk {i + 1}/{len(transcriptions)}...", progress_value)
                current_time_ms += data["duration"]
        
        progress_callback(f"\nSubtitle generation complete! SRT file saved to: {output_srt_path}", 100)


# Main application class for the GUI.
class SubtitleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Single-Language Subtitle Generator")
        self.geometry("600x650")
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Media File Selection
        ttk.Label(main_frame, text="Select a Video/Audio File:").pack(pady=(0, 5), anchor="w")
        
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.file_path_entry = ttk.Entry(file_frame)
        self.file_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(file_frame, text="Browse", command=self.browse_file).pack(side=tk.RIGHT)

        # 2. Source Language Selection
        ttk.Label(main_frame, text="Select Source Language (Spoken in video):").pack(pady=(0, 5), anchor="w")
        self.source_lang_var = tk.StringVar(self)
        self.source_lang_menu = ttk.Combobox(main_frame, textvariable=self.source_lang_var, state="readonly")
        self.source_lang_menu['values'] = list(LANGUAGES.keys())
        self.source_lang_menu.current(0) # Default to English
        self.source_lang_menu.pack(fill=tk.X, pady=(0, 10))

        # 3. Target Language Selection
        ttk.Label(main_frame, text="Select Target Language:").pack(pady=(0, 5), anchor="w")
        
        self.target_lang_var = tk.StringVar(self)
        self.target_lang_menu = ttk.Combobox(main_frame, textvariable=self.target_lang_var, state="readonly")
        self.target_lang_menu['values'] = list(LANGUAGES.keys())
        self.target_lang_menu.current(0) # Default to English
        self.target_lang_menu.pack(fill=tk.X, pady=(0, 10))

        # 4. Progress Bar
        self.progress_bar = ttk.Progressbar(main_frame, orient="horizontal", length=400, mode="determinate")
        self.progress_bar.pack(pady=(10, 5), fill=tk.X)
        
        self.progress_label = ttk.Label(main_frame, text="Ready.")
        self.progress_label.pack(pady=(0, 10), anchor="w")

        # 5. Generate Button
        self.generate_button = ttk.Button(main_frame, text="Generate Subtitles", command=self.start_generation_thread)
        self.generate_button.pack(fill=tk.X, pady=(0, 15))
        
        # 6. Log Display
        ttk.Label(main_frame, text="Log:").pack(pady=(0, 5), anchor="w")
        self.log_text = tk.Text(main_frame, wrap=tk.WORD, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a Video/Audio File",
            filetypes=[("Media Files", "*.mp3 *.wav *.flac *.m4a *.mp4 *.avi *.mkv")]
        )
        if file_path:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, file_path)
            self.update_progress("File selected.", 0)
    
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def update_progress(self, message, value):
        self.log(message)
        self.progress_label.config(text=message)
        self.progress_bar["value"] = value
        self.update_idletasks() # Force GUI update

    def show_editor_window(self, initial_translations):
        """Creates a pop-up window for editing transcription and translations."""
        final_texts = {}
        yes_all_clicked = False
        
        editor_window = tk.Toplevel(self)
        editor_window.title("Review & Edit Subtitles")
        editor_window.geometry("500x350")
        editor_window.transient(self)
        editor_window.grab_set()

        source_lang_text = initial_translations.get("Source (" + self.source_lang_var.get() + ")", "")
        target_lang_text = initial_translations.get("Target (" + self.target_lang_var.get() + ")", "")

        ttk.Label(editor_window, text=f"Source ({self.source_lang_var.get()}):").pack(pady=(10, 2), padx=10, anchor="w")
        source_text_box = tk.Text(editor_window, wrap=tk.WORD, height=3)
        source_text_box.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        source_text_box.insert(tk.END, source_lang_text)
        
        ttk.Label(editor_window, text=f"Target ({self.target_lang_var.get()}):").pack(pady=(10, 2), padx=10, anchor="w")
        target_text_box = tk.Text(editor_window, wrap=tk.WORD, height=3)
        target_text_box.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        target_text_box.insert(tk.END, target_lang_text)

        def yes_and_close():
            nonlocal final_texts
            nonlocal yes_all_clicked
            final_texts["Source (" + self.source_lang_var.get() + ")"] = source_text_box.get("1.0", tk.END).strip()
            final_texts["Target (" + self.target_lang_var.get() + ")"] = target_text_box.get("1.0", tk.END).strip()
            yes_all_clicked = False
            editor_window.destroy()

        def yes_all_and_close():
            nonlocal final_texts
            nonlocal yes_all_clicked
            final_texts["Source (" + self.source_lang_var.get() + ")"] = source_text_box.get("1.0", tk.END).strip()
            final_texts["Target (" + self.target_lang_var.get() + ")"] = target_text_box.get("1.0", tk.END).strip()
            yes_all_clicked = True
            editor_window.destroy()

        button_frame = ttk.Frame(editor_window)
        button_frame.pack(pady=10)

        yes_button = ttk.Button(button_frame, text="Yes", command=yes_and_close)
        yes_button.pack(side=tk.LEFT, padx=5)

        yes_all_button = ttk.Button(button_frame, text="Yes all", command=yes_all_and_close)
        yes_all_button.pack(side=tk.LEFT, padx=5)
        
        editor_window.wait_window()
        return final_texts, yes_all_clicked

    def start_generation_thread(self):
        media_file_path = self.file_path_entry.get()
        if not media_file_path:
            self.update_progress("Please select a video or audio file first.", 0)
            return
        
        source_lang_name = self.source_lang_var.get()
        target_lang_name = self.target_lang_var.get()
        if not source_lang_name or not target_lang_name:
            self.update_progress("Please select both source and target languages.", 0)
            return
        
        source_language_code = LANGUAGES[source_lang_name]

        self.generate_button.config(state=tk.DISABLED)
        self.update_progress("Starting subtitle generation...", 0)

        thread = threading.Thread(
            target=self.run_generation,
            args=(media_file_path, target_lang_name, source_language_code)
        )
        thread.start()

    def run_generation(self, media_file_path, target_language_name, source_language_code):
        try:
            srt_gen = SRTAudioGenerator(media_file_path, target_language_name, source_language_code)
            srt_gen.generate_subtitles(
                progress_callback=self.update_progress,
                edit_callback=self.show_editor_window
            )
        except FileNotFoundError as e:
            self.update_progress(str(e), 0)
        except Exception as e:
            self.update_progress(f"An unexpected error occurred: {e}", 0)
        finally:
            self.generate_button.config(state=tk.NORMAL)


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    os.chdir(application_path)

    app = SubtitleApp()
    app.mainloop()