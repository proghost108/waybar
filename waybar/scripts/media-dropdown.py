#!/usr/bin/env python3
"""
Media Dropdown Controller for Waybar & Hyprland
Ultra-Smooth Asynchronous Architecture & Monochrome Topographic Aesthetics
"""

import os
import sys
import time
import signal
import subprocess
import urllib.request
import urllib.parse
import hashlib
import threading
import traceback
import cairo

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

PID_FILE = "/tmp/media-dropdown.pid"
LOG_FILE = "/tmp/media-dropdown.log"
ART_CACHE_DIR = "/tmp/mpris_art_cache"

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{os.getpid()}] {msg}\n")
    except Exception:
        pass

class MediaDropdown(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        log("MediaDropdown.__init__ called")
        
        self.set_title("Media Dropdown")
        try:
            self.set_wmclass("media-dropdown", "media-dropdown")
        except Exception:
            pass
        self.set_role("media-dropdown")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(460, 240)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)

        # Transparent RGBA visual
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        # State tracking
        self.playback_status = "paused"
        self.current_player = None
        self.current_art_url = None
        self.current_pos = 0.0
        self.current_len = 0.0
        self.is_seeking = False
        self.is_adjusting_vol = False
        self.updating_from_playerctl = False
        self.is_querying = False
        self.last_vol_time = 0.0

        os.makedirs(ART_CACHE_DIR, exist_ok=True)

        # Load styling
        self.load_styles()

        # Build UI
        self.build_ui()

        # Connect window events
        self.connect("draw", self.on_draw)
        self.connect("destroy", self.on_destroy)
        self.connect("key-press-event", self.on_key_press)

        # Start non-blocking background workers
        self.start_background_workers()
        log("MediaDropdown initialized successfully")

    def on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.Operator.SOURCE)
        cr.paint()
        return False

    def load_styles(self):
        css = b"""
        * {
            font-family: "JetBrainsMono Nerd Font Propo", "JetBrainsMono Nerd Font", monospace;
        }

        window.background {
            background-color: transparent;
        }
        
        #card {
            background-color: rgba(16, 18, 22, 0.96);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.7);
        }
        
        #player-badge {
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 11px;
            font-weight: 600;
            color: #f4f4f5;
        }

        #status-label {
            font-size: 11px;
            font-weight: 500;
            color: #a1a1aa;
        }

        #btn-close {
            background: transparent;
            border: none;
            color: #71717a;
            font-size: 16px;
            border-radius: 9999px;
            min-width: 28px;
            min-height: 28px;
            padding: 0;
            transition: all 0.2s ease;
        }
        #btn-close:hover {
            color: #ffffff;
            background-color: rgba(255, 255, 255, 0.14);
        }

        #title-label {
            font-size: 13px;
            font-weight: 700;
            color: #f4f4f5;
        }

        #artist-label {
            font-size: 11px;
            font-weight: 500;
            color: #d4d4d8;
        }

        #album-label {
            font-size: 10px;
            font-weight: 400;
            color: #71717a;
        }

        #art-box {
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            min-width: 84px;
            min-height: 84px;
        }

        .media-btn {
            font-family: "JetBrainsMono Nerd Font Propo", "JetBrainsMono Nerd Font", monospace;
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 9999px;
            color: #d4d4d8;
            min-width: 38px;
            min-height: 38px;
            padding: 0;
            font-size: 18px;
            transition: all 0.15s ease;
        }
        .media-btn:hover {
            background-color: rgba(255, 255, 255, 0.18);
            border-color: rgba(255, 255, 255, 0.30);
            color: #ffffff;
        }

        #btn-playpause {
            font-family: "JetBrainsMono Nerd Font Propo", "JetBrainsMono Nerd Font", monospace;
            background-color: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.30);
            border-radius: 9999px;
            color: #ffffff;
            min-width: 48px;
            min-height: 48px;
            padding: 0;
            font-size: 24px;
            font-weight: bold;
            transition: all 0.15s ease;
        }
        #btn-playpause:hover {
            background-color: rgba(255, 255, 255, 0.28);
            border-color: #ffffff;
            box-shadow: 0 0 12px rgba(255, 255, 255, 0.35);
        }

        #time-current, #time-total {
            font-size: 10px;
            font-family: "JetBrainsMono Nerd Font Propo", monospace;
            color: #71717a;
        }

        /* Seek Bar & Volume Bar */
        scale {
            padding: 0;
            margin: 0;
        }
        scale trough {
            min-height: 4px;
            border-radius: 2px;
            background-color: rgba(255, 255, 255, 0.12);
        }
        scale highlight {
            min-height: 4px;
            border-radius: 2px;
            background-color: #ffffff;
        }
        scale slider {
            min-height: 12px;
            min-width: 12px;
            margin: -4px 0;
            border-radius: 9999px;
            background-color: #ffffff;
            box-shadow: 0 0 6px rgba(255, 255, 255, 0.4);
        }
        scale slider:hover {
            background-color: #ffffff;
            min-height: 14px;
            min-width: 14px;
            margin: -5px 0;
        }

        #vol-icon {
            font-family: "JetBrainsMono Nerd Font Propo", "JetBrainsMono Nerd Font", monospace;
            font-size: 16px;
            color: #a1a1aa;
            margin-right: 4px;
        }

        #empty-title {
            font-size: 14px;
            font-weight: 700;
            color: #f4f4f5;
        }
        #empty-desc {
            font-size: 11px;
            color: #71717a;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def build_ui(self):
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.card.set_name("card")
        self.add(self.card)

        # Stack to switch between active media and empty view
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.card.pack_start(self.stack, True, True, 0)

        # ----------------- Active Media View -----------------
        self.media_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.stack.add_named(self.media_view, "media")

        # Top row: Player badge, status, close button
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.player_badge = Gtk.Label(label="󰎆  Media")
        self.player_badge.set_name("player-badge")
        top_box.pack_start(self.player_badge, False, False, 0)

        self.status_label = Gtk.Label(label="● Playing")
        self.status_label.set_name("status-label")
        top_box.pack_start(self.status_label, False, False, 0)

        spacer = Gtk.Box()
        top_box.pack_start(spacer, True, True, 0)

        btn_close = Gtk.Button(label="✕")
        btn_close.set_name("btn-close")
        btn_close.connect("clicked", lambda b: self.close_dropdown())
        top_box.pack_end(btn_close, False, False, 0)

        self.media_view.pack_start(top_box, False, False, 0)

        # Middle row: Artwork + Metadata
        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        # Artwork Box using Gtk.Stack for perfect centering and clean transitions
        self.art_stack = Gtk.Stack()
        self.art_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.art_stack.set_name("art-box")
        self.art_stack.set_size_request(84, 84)

        # Fallback Label with JetBrainsMono Nerd Font
        self.art_label = Gtk.Label()
        self.art_label.set_markup("<span font_desc='JetBrainsMono Nerd Font 40' color='#71717a'>󰎆</span>")
        self.art_label.set_valign(Gtk.Align.CENTER)
        self.art_label.set_halign(Gtk.Align.CENTER)
        self.art_stack.add_named(self.art_label, "fallback")

        # Artwork Image
        self.art_image = Gtk.Image()
        self.art_image.set_valign(Gtk.Align.CENTER)
        self.art_image.set_halign(Gtk.Align.CENTER)
        self.art_stack.add_named(self.art_image, "image")

        self.art_stack.set_visible_child_name("fallback")
        meta_row.pack_start(self.art_stack, False, False, 0)

        # Text labels
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_box.set_valign(Gtk.Align.CENTER)

        self.title_label = Gtk.Label(label="Unknown Title")
        self.title_label.set_name("title-label")
        self.title_label.set_xalign(0.0)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(28)
        info_box.pack_start(self.title_label, False, False, 0)

        self.artist_label = Gtk.Label(label="Unknown Artist")
        self.artist_label.set_name("artist-label")
        self.artist_label.set_xalign(0.0)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.set_max_width_chars(32)
        info_box.pack_start(self.artist_label, False, False, 0)

        self.album_label = Gtk.Label(label="")
        self.album_label.set_name("album-label")
        self.album_label.set_xalign(0.0)
        self.album_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.album_label.set_max_width_chars(36)
        info_box.pack_start(self.album_label, False, False, 0)

        meta_row.pack_start(info_box, True, True, 0)
        self.media_view.pack_start(meta_row, False, False, 0)

        # Seek Bar Row: Current Time, Scale, Total Time
        seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.time_current = Gtk.Label(label="00:00")
        self.time_current.set_name("time-current")
        seek_row.pack_start(self.time_current, False, False, 0)

        self.seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.connect("button-press-event", self.on_seek_press)
        self.seek_scale.connect("button-release-event", self.on_seek_release)
        self.seek_scale.connect("change-value", self.on_seek_change)
        seek_row.pack_start(self.seek_scale, True, True, 0)

        self.time_total = Gtk.Label(label="00:00")
        self.time_total.set_name("time-total")
        seek_row.pack_start(self.time_total, False, False, 0)

        self.media_view.pack_start(seek_row, False, False, 0)

        # Controls Row: Previous, Seek -10s, Play/Pause, Seek +10s, Next, Volume
        ctrl_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        btn_prev = Gtk.Button(label="󰒭")
        btn_prev.get_style_context().add_class("media-btn")
        btn_prev.connect("clicked", lambda b: self.run_player_cmd_async("previous"))
        ctrl_row.pack_start(btn_prev, False, False, 0)

        btn_rewind = Gtk.Button(label="󰑊")
        btn_rewind.get_style_context().add_class("media-btn")
        btn_rewind.connect("clicked", lambda b: self.run_player_cmd_async("position", "10-"))
        ctrl_row.pack_start(btn_rewind, False, False, 0)

        self.btn_playpause = Gtk.Button(label="󰐊")
        self.btn_playpause.set_name("btn-playpause")
        self.btn_playpause.connect("clicked", self.on_toggle_playpause)
        ctrl_row.pack_start(self.btn_playpause, False, False, 0)

        btn_forward = Gtk.Button(label="󰑈")
        btn_forward.get_style_context().add_class("media-btn")
        btn_forward.connect("clicked", lambda b: self.run_player_cmd_async("position", "10+"))
        ctrl_row.pack_start(btn_forward, False, False, 0)

        btn_next = Gtk.Button(label="󰒮")
        btn_next.get_style_context().add_class("media-btn")
        btn_next.connect("clicked", lambda b: self.run_player_cmd_async("next"))
        ctrl_row.pack_start(btn_next, False, False, 0)

        spacer_ctrl = Gtk.Box()
        ctrl_row.pack_start(spacer_ctrl, True, True, 0)

        vol_icon = Gtk.Label(label="󰕾")
        vol_icon.set_name("vol-icon")
        ctrl_row.pack_start(vol_icon, False, False, 0)

        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 2)
        self.vol_scale.set_size_request(65, -1)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.connect("button-press-event", lambda s, e: setattr(self, 'is_adjusting_vol', True))
        self.vol_scale.connect("button-release-event", self.on_vol_release)
        self.vol_scale.connect("value-changed", self.on_vol_change)
        ctrl_row.pack_start(self.vol_scale, False, False, 0)

        self.media_view.pack_start(ctrl_row, False, False, 0)

        # ----------------- Empty View -----------------
        self.empty_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.empty_view.set_valign(Gtk.Align.CENTER)
        self.empty_view.set_halign(Gtk.Align.CENTER)
        self.stack.add_named(self.empty_view, "empty")

        empty_icon = Gtk.Label(label="󰎆")
        empty_icon.set_markup("<span font_desc='JetBrainsMono Nerd Font 40' color='#71717a'>󰎆</span>")
        self.empty_view.pack_start(empty_icon, False, False, 0)

        empty_title = Gtk.Label(label="No Active Media Playback")
        empty_title.set_name("empty-title")
        self.empty_view.pack_start(empty_title, False, False, 0)

        empty_desc = Gtk.Label(label="Play music or video in Spotify, browser, or media player")
        empty_desc.set_name("empty-desc")
        self.empty_view.pack_start(empty_desc, False, False, 0)

        btn_empty_close = Gtk.Button(label="Close")
        btn_empty_close.get_style_context().add_class("media-btn")
        btn_empty_close.set_size_request(80, 32)
        btn_empty_close.connect("clicked", lambda b: self.close_dropdown())
        self.empty_view.pack_start(btn_empty_close, False, False, 4)

    def start_background_workers(self):
        # Local UI ticker (every 250ms): zero subprocesses, buttery-smooth progress bar
        GLib.timeout_add(250, self.tick_ui_progress)
        # Background sync (every 1000ms): async thread queries playerctl
        GLib.timeout_add(1000, self.trigger_async_state_query)
        # Immediate first query
        self.trigger_async_state_query()

    def tick_ui_progress(self):
        if self.playback_status.lower() == "playing" and not self.is_seeking:
            if self.current_len > 0:
                self.current_pos = min(self.current_len, self.current_pos + 0.25)
                self.updating_from_playerctl = True
                self.seek_scale.set_value(self.current_pos)
                self.time_current.set_text(self.format_time(self.current_pos))
                self.updating_from_playerctl = False
        return True

    def trigger_async_state_query(self):
        if not self.is_querying:
            self.is_querying = True
            threading.Thread(target=self.fetch_state_worker, daemon=True).start()
        return True

    def fetch_state_worker(self):
        try:
            res = subprocess.run(
                [
                    "playerctl", "metadata", "--format",
                    "{{playerName}}@@@{{status}}@@@{{title}}@@@{{artist}}@@@{{album}}@@@{{mpris:artUrl}}@@@{{mpris:length}}@@@{{position}}@@@{{volume}}"
                ],
                capture_output=True, text=True, timeout=1
            )
            data = None
            if res.returncode == 0 and res.stdout.strip():
                lines = [l for l in res.stdout.strip().splitlines() if l.strip()]
                if lines:
                    parts = lines[0].split("@@@")
                    if len(parts) >= 8:
                        data = {
                            "player": parts[0] or "media",
                            "status": parts[1] or "Paused",
                            "title": parts[2] or "Unknown Title",
                            "artist": parts[3] or "Unknown Artist",
                            "album": parts[4] or "",
                            "art_url": parts[5] or "",
                            "raw_length": parts[6],
                            "raw_pos": parts[7],
                            "raw_vol": parts[8] if len(parts) > 8 else "1.0",
                        }
            GLib.idle_add(self.apply_media_state, data)
        except Exception as e:
            log(f"fetch_state_worker error: {e}")
        finally:
            self.is_querying = False

    def apply_media_state(self, data):
        if not data:
            self.stack.set_visible_child_name("empty")
            return False

        self.stack.set_visible_child_name("media")

        player = data["player"]
        status = data["status"]
        title = data["title"]
        artist = data["artist"]
        album = data["album"]
        art_url = data["art_url"]
        raw_length = data["raw_length"]
        raw_pos = data["raw_pos"]
        raw_vol = data["raw_vol"]

        self.playback_status = status

        # Player icon & name badge
        p_lower = player.lower()
        if "spotify" in p_lower:
            p_icon = "󰓇"
        elif "firefox" in p_lower:
            p_icon = "󰈹"
        elif "chromium" in p_lower or "chrome" in p_lower:
            p_icon = ""
        else:
            p_icon = "󰎆"
        self.player_badge.set_text(f"{p_icon}  {player.capitalize()}")

        # Status indicator & Play/Pause icon
        if status.lower() == "playing":
            self.status_label.set_markup("<span color='#ffffff'>● Playing</span>")
            self.btn_playpause.set_label("󰏤")
        else:
            self.status_label.set_markup("<span color='#71717a'>○ Paused</span>")
            self.btn_playpause.set_label("󰐊")

        # Track metadata text
        self.title_label.set_text(title)
        self.title_label.set_tooltip_text(title)
        self.artist_label.set_text(artist)
        self.album_label.set_text(album if album else "")

        # Length calculation
        length_sec = 0.0
        if raw_length and raw_length.isdigit():
            length_sec = float(raw_length) / 1000000.0
        elif raw_length:
            try:
                val = float(raw_length)
                length_sec = val / 1000000.0 if val > 100000 else val
            except ValueError:
                length_sec = 0.0
        self.current_len = length_sec

        # Position calculation
        pos_sec = 0.0
        if raw_pos:
            try:
                val = float(raw_pos)
                pos_sec = val / 1000000.0 if val > 100000 else val
            except ValueError:
                pos_sec = 0.0
        self.current_pos = pos_sec

        # Update seek slider if not being dragged
        if not self.is_seeking:
            self.updating_from_playerctl = True
            if length_sec > 0:
                self.seek_scale.set_range(0, length_sec)
                self.seek_scale.set_value(min(pos_sec, length_sec))
                self.time_total.set_text(self.format_time(length_sec))
                self.time_current.set_text(self.format_time(pos_sec))
                self.seek_scale.set_sensitive(True)
            else:
                self.seek_scale.set_range(0, 100)
                self.seek_scale.set_value(0)
                self.time_current.set_text(self.format_time(pos_sec))
                self.time_total.set_text("--:--")
                self.seek_scale.set_sensitive(False)
            self.updating_from_playerctl = False

        # Volume slider update
        if not self.is_adjusting_vol:
            try:
                vol_float = float(raw_vol) if raw_vol else 1.0
                self.updating_from_playerctl = True
                self.vol_scale.set_value(min(100.0, max(0.0, vol_float * 100.0)))
                self.updating_from_playerctl = False
            except ValueError:
                pass

        # Handle artwork changes asynchronously
        if art_url != self.current_art_url:
            self.current_art_url = art_url
            self.load_artwork_async(art_url)

        return False

    def load_artwork_async(self, art_url):
        if not art_url:
            self.set_default_art()
            return

        def worker():
            try:
                local_path = None
                if art_url.startswith("file://"):
                    local_path = urllib.parse.unquote(art_url[7:])
                elif art_url.startswith("http://") or art_url.startswith("https://"):
                    cache_name = hashlib.md5(art_url.encode("utf-8")).hexdigest() + ".jpg"
                    cache_path = os.path.join(ART_CACHE_DIR, cache_name)
                    if not os.path.exists(cache_path):
                        req = urllib.request.Request(art_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=3) as resp, open(cache_path, 'wb') as f:
                            f.write(resp.read())
                    local_path = cache_path
                else:
                    local_path = art_url

                if local_path and os.path.exists(local_path):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(local_path, 84, 84, False)
                    GLib.idle_add(self.apply_pixbuf_artwork, pixbuf)
                    return
            except Exception as e:
                log(f"Artwork loading error: {e}")
            GLib.idle_add(self.set_default_art)

        threading.Thread(target=worker, daemon=True).start()

    def apply_pixbuf_artwork(self, pixbuf):
        self.art_image.set_from_pixbuf(pixbuf)
        self.art_stack.set_visible_child_name("image")

    def set_default_art(self):
        self.art_stack.set_visible_child_name("fallback")

    def format_time(self, seconds):
        try:
            s = max(0, int(float(seconds)))
            m = s // 60
            sec = s % 60
            return f"{m:02d}:{sec:02d}"
        except Exception:
            return "00:00"

    def run_player_cmd_async(self, *args):
        def worker():
            try:
                subprocess.run(["playerctl"] + list(args), timeout=1, check=False)
                # Sync state after command
                self.trigger_async_state_query()
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def on_toggle_playpause(self, widget):
        # Instant UI feedback (0ms latency)
        if self.playback_status.lower() == "playing":
            self.playback_status = "paused"
            self.btn_playpause.set_label("󰐊")
            self.status_label.set_markup("<span color='#71717a'>○ Paused</span>")
        else:
            self.playback_status = "playing"
            self.btn_playpause.set_label("󰏤")
            self.status_label.set_markup("<span color='#ffffff'>● Playing</span>")
        self.run_player_cmd_async("play-pause")

    def on_seek_press(self, widget, event):
        self.is_seeking = True

    def on_seek_release(self, widget, event):
        self.is_seeking = False
        val = self.seek_scale.get_value()
        self.current_pos = val
        self.run_player_cmd_async("position", str(val))

    def on_seek_change(self, widget, scroll, value):
        if self.is_seeking:
            self.time_current.set_text(self.format_time(value))
        return False

    def on_vol_release(self, widget, event):
        self.is_adjusting_vol = False
        val = self.vol_scale.get_value() / 100.0
        self.run_player_cmd_async("volume", f"{val:.2f}")

    def on_vol_change(self, widget):
        if not self.updating_from_playerctl:
            now = time.time()
            if now - self.last_vol_time > 0.05:  # 50ms throttle for smooth drag
                self.last_vol_time = now
                val = self.vol_scale.get_value() / 100.0
                self.run_player_cmd_async("volume", f"{val:.2f}")

    def on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q, Gdk.KEY_Q):
            log("Escape/q pressed, closing dropdown")
            self.close_dropdown()
            return True
        return False

    def close_dropdown(self):
        log("close_dropdown called")
        Gtk.main_quit()

    def on_destroy(self, widget):
        log("on_destroy called")
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
        Gtk.main_quit()

def main():
    log("=== media-dropdown.py main() started ===")
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log(f"Failed to write PID file: {e}")

    def sig_handler(signum, frame):
        log(f"Received signal {signum}, exiting")
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    try:
        app = MediaDropdown()
        app.show_all()
        log("app.show_all() succeeded, entering Gtk.main()")
        Gtk.main()
        log("Gtk.main() exited normally")
    except Exception as e:
        log(f"CRASH in main(): {traceback.format_exc()}")
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
        raise

if __name__ == "__main__":
    main()
