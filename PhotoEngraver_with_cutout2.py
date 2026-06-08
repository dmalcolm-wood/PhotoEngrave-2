import subprocess
import sys
import importlib.util

# Function to check and install required packages
def install_package(package_name):
    """Check if a package is installed, if not, install it"""
    spec = importlib.util.find_spec(package_name)
    if spec is None:
        print(f"{package_name} not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"{package_name} installed successfully!")
            return True
        except Exception as e:
            print(f"Failed to install {package_name}: {e}")
            return False
    else:
        print(f"{package_name} is already installed.")
        return True

# Try to install Pillow if needed
if not install_package("PIL"):
    print("ERROR: Could not install Pillow. Please install it manually using: pip install pillow")
    input("Press Enter to exit...")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import os
import json
import traceback
import math

# ------------------------------------------------------------
# Simple Image to Mach3 G-code Engraving App
# ------------------------------------------------------------

CONFIG_FILE = "image_engrave_settings.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass


# Default parameters
default_params = {
    "input_image": "",
    "width_mm": 100.0,
    "height_mm": 80.0,
    "line_spacing_mm": 0.5,
    "pixel_spacing_mm": 0.5,
    "safe_z": 5.0,
    "surface_z": 0.0,
    "max_depth": 1.0,
    "feed_rate": 800,
    "plunge_rate": 300,
    "spindle_speed": 12000,
    "invert_image": False,
    "crop_to_subject": False,
    "background_threshold": 240,
    # Cut-out settings
    "cutout_enabled": False,
    "cutout_margin_mm": 1.0,
    "cutout_depth_mm": 3.0,
    "cutout_pass_depth_mm": 1.0,
    "cutout_feed_rate": 500,
    "cutout_plunge_rate": 200,
    "cutout_tool_number": 2,
    "cutout_silhouette_simplify": 0.5,
}


class EngraveApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Engrave G-code Generator - Pet Portrait Edition")
        self.root.geometry("1200x800")

        self.params = default_params.copy()
        self.tk_img = None
        self.orig_img_size = None
        self.cropped_img = None
        self.subject_mask = None

        self.config = load_config()
        default_output_dir = os.path.expanduser("~/Desktop/CNC_Gcode")
        self.output_dir = self.config.get("output_dir", default_output_dir)
        
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            print(f"Could not create output directory: {e}")
            self.output_dir = os.path.expanduser("~/Desktop")
        
        self.output_path = ""

        self.create_widgets()
        self.update_output_path()

    def create_widgets(self):
        # Create ALL StringVar variables FIRST
        self.status_var = tk.StringVar(value="Ready.")
        self.img_info_var = tk.StringVar(value="")
        self.output_path_var = tk.StringVar(value="")
        
        # Main paned window for left controls and right preview
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left frame for tabs
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Right frame for preview
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Create notebook (tabs) on the left
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Main Settings
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="Engraving Settings")
        
        # Tab 2: Silhouette Cut-out
        self.cutout_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cutout_tab, text="Silhouette Cut-out")
        
        # Build the tabs
        self.build_main_tab()
        self.build_cutout_tab()
        
        # Status bar at bottom
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        ttk.Label(status_bar, textvariable=self.status_var, relief=tk.SUNKEN, 
                 anchor=tk.W, padding=(5, 2)).pack(fill=tk.X, side=tk.LEFT, expand=True)
        ttk.Label(status_bar, textvariable=self.img_info_var, relief=tk.SUNKEN,
                 anchor=tk.W, padding=(5, 2)).pack(fill=tk.X, side=tk.RIGHT, expand=True)
        
        # Image preview on the right
        preview_frame = ttk.LabelFrame(right_frame, text="Image Preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.img_label = tk.Label(
            preview_frame,
            text="No image loaded.\nClick 'Browse / Load Image' to start",
            bg="white",
            relief=tk.SUNKEN
        )
        self.img_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def build_main_tab(self):
        """Build the main engraving settings tab"""
        # Create a canvas with scrollbar for main tab
        canvas = tk.Canvas(self.main_tab, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.main_tab, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Input image section
        input_frame = ttk.LabelFrame(scrollable_frame, text="Input Image", padding=(10, 5))
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(input_frame, text="Image File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.input_entry = ttk.Entry(input_frame, width=50)
        self.input_entry.grid(row=0, column=1, padx=5, pady=2)
        self.input_entry.insert(0, self.params["input_image"])
        
        ttk.Button(input_frame, text="Browse / Load Image", command=self.browse_image).grid(row=0, column=2, padx=5, pady=2)
        
        # Output section
        output_frame = ttk.LabelFrame(scrollable_frame, text="Output Settings", padding=(10, 5))
        output_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(output_frame, text="Output G-code:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(output_frame, textvariable=self.output_path_var, foreground="gray").grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(output_frame, text="Set Output Folder", command=self.browse_output_folder).grid(row=0, column=2, padx=5)
        
        # Subject detection section
        subject_frame = ttk.LabelFrame(scrollable_frame, text="Subject Detection (for pet portraits)", padding=(10, 5))
        subject_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.crop_to_subject_var = tk.BooleanVar(value=self.params["crop_to_subject"])
        self.background_threshold_var = tk.IntVar(value=self.params["background_threshold"])
        
        ttk.Checkbutton(subject_frame, text="Crop to subject only", 
                       variable=self.crop_to_subject_var,
                       command=self.on_crop_setting_changed).pack(anchor=tk.W, pady=2)
        
        threshold_frame = ttk.Frame(subject_frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        ttk.Label(threshold_frame, text="Background Brightness Threshold:", width=25).pack(side=tk.LEFT)
        threshold_scale = tk.Scale(threshold_frame, from_=200, to=255, 
                                   orient=tk.HORIZONTAL, variable=self.background_threshold_var,
                                   length=200, command=self.on_threshold_changed)
        threshold_scale.pack(side=tk.LEFT, padx=5)
        ttk.Label(threshold_frame, text="(lower = more aggressive)").pack(side=tk.LEFT, padx=5)
        ttk.Label(subject_frame, text="Tip: Use white/light backgrounds for best results", 
                 foreground="gray").pack(anchor=tk.W, pady=2)
        
        # Engraving settings section
        engrave_frame = ttk.LabelFrame(scrollable_frame, text="Engraving Settings", padding=(10, 5))
        engrave_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Tk variables for engraving settings
        self.width_var = tk.DoubleVar(value=self.params["width_mm"])
        self.height_var = tk.DoubleVar(value=self.params["height_mm"])
        self.line_spacing_var = tk.DoubleVar(value=self.params["line_spacing_mm"])
        self.pixel_spacing_var = tk.DoubleVar(value=self.params["pixel_spacing_mm"])
        self.safe_z_var = tk.DoubleVar(value=self.params["safe_z"])
        self.surface_z_var = tk.DoubleVar(value=self.params["surface_z"])
        self.max_depth_var = tk.DoubleVar(value=self.params["max_depth"])
        self.feed_rate_var = tk.IntVar(value=self.params["feed_rate"])
        self.plunge_rate_var = tk.IntVar(value=self.params["plunge_rate"])
        self.spindle_speed_var = tk.IntVar(value=self.params["spindle_speed"])
        self.invert_image_var = tk.BooleanVar(value=self.params["invert_image"])
        
        engrave_settings = [
            ("Width (mm):", self.width_var),
            ("Height (mm):", self.height_var),
            ("Line spacing (mm):", self.line_spacing_var),
            ("Pixel spacing (mm):", self.pixel_spacing_var),
            ("Safe Z (mm):", self.safe_z_var),
            ("Surface Z (mm):", self.surface_z_var),
            ("Max depth (mm):", self.max_depth_var),
            ("Feed rate (mm/min):", self.feed_rate_var),
            ("Plunge rate (mm/min):", self.plunge_rate_var),
            ("Spindle speed (RPM):", self.spindle_speed_var),
        ]
        
        for i, (label, var) in enumerate(engrave_settings):
            row = ttk.Frame(engrave_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=20, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var, width=12).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(engrave_frame, text="Invert image (engrave dark areas)", 
                       variable=self.invert_image_var).pack(anchor=tk.W, pady=5)
        
        # Create button
        ttk.Button(scrollable_frame, text="CREATE G-CODE", command=self.save_gcode_button,
                  style="Accent.TButton").pack(pady=15)
        
        # Configure style for accent button
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 12, "bold"))

    def build_cutout_tab(self):
        """Build the silhouette cut-out settings tab"""
        # Create a canvas with scrollbar for cutout tab
        canvas = tk.Canvas(self.cutout_tab, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.cutout_tab, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Cut-out variables
        self.cutout_enabled_var = tk.BooleanVar(value=self.params["cutout_enabled"])
        self.cutout_margin_var = tk.DoubleVar(value=self.params["cutout_margin_mm"])
        self.cutout_depth_var = tk.DoubleVar(value=self.params["cutout_depth_mm"])
        self.cutout_pass_depth_var = tk.DoubleVar(value=self.params["cutout_pass_depth_mm"])
        self.cutout_feed_var = tk.IntVar(value=self.params["cutout_feed_rate"])
        self.cutout_plunge_var = tk.IntVar(value=self.params["cutout_plunge_rate"])
        self.cutout_tool_var = tk.IntVar(value=self.params["cutout_tool_number"])
        self.cutout_simplify_var = tk.DoubleVar(value=self.params["cutout_silhouette_simplify"])
        
        # Enable section
        enable_frame = ttk.LabelFrame(scrollable_frame, text="Enable Silhouette Cut-out", padding=(10, 5))
        enable_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Checkbutton(enable_frame, text="Generate silhouette cut-out toolpath", 
                       variable=self.cutout_enabled_var,
                       command=self.on_cutout_enabled_changed).pack(anchor=tk.W, pady=5)
        
        ttk.Label(enable_frame, text="Note: Requires 'Crop to subject' to be enabled in Engraving Settings",
                 foreground="blue").pack(anchor=tk.W, pady=2)
        
        # Settings frame
        self.cutout_settings_frame = ttk.LabelFrame(scrollable_frame, text="Cut-out Settings", padding=(10, 5))
        self.cutout_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        cutout_settings = [
            ("Margin around subject (mm):", self.cutout_margin_var, "Adds extra space around the pet"),
            ("Total cut depth (mm):", self.cutout_depth_var, "How deep to cut through material"),
            ("Depth per pass (mm):", self.cutout_pass_depth_var, "Smaller = smoother cut, more passes"),
            ("Feed rate (mm/min):", self.cutout_feed_var, "Cutting speed (lower = smoother)"),
            ("Plunge rate (mm/min):", self.cutout_plunge_var, "Vertical entry speed"),
            ("Tool number (T#):", self.cutout_tool_var, "Tool change number in Mach3"),
            ("Simplify tolerance (mm):", self.cutout_simplify_var, "Higher = smoother path, fewer points"),
        ]
        
        for label, var, tip in cutout_settings:
            row = ttk.Frame(self.cutout_settings_frame)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=label, width=22, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var, width=10).pack(side=tk.LEFT, padx=5)
            ttk.Label(row, text=tip, foreground="gray", font=("Arial", 8)).pack(side=tk.LEFT, padx=5)
        
        # Initially disable settings if cutout is not enabled
        self.update_cutout_settings_state()
        
        # Info box
        info_frame = ttk.LabelFrame(scrollable_frame, text="How It Works", padding=(10, 5))
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = """
        The silhouette cut-out traces the exact outline of your pet (plus optional margin)
        and creates a separate toolpath file for cutting the piece out of the material.
        
        Workflow:
        1. Engrave the portrait with your engraving bit (uses main settings)
        2. Change to an end mill (1/8" or 3mm recommended)
        3. Run the cut-out file (saved as *_cutout.nc)
        4. The piece will drop out cleanly along the pet's outline!
        
        Tips:
        • Use a small margin (0.5-1mm) for easier fitting
        • Set total depth slightly deeper than material thickness
        • Lower feed rates (300-500) give smoother cuts
        • Test on scrap wood first!
        """
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, foreground="darkgreen")
        info_label.pack(anchor=tk.W)
    
    def on_cutout_enabled_changed(self):
        """Handle cut-out enable/disable"""
        self.update_cutout_settings_state()
    
    def update_cutout_settings_state(self):
        """Enable/disable cut-out settings based on checkbox"""
        state = tk.NORMAL if self.cutout_enabled_var.get() else tk.DISABLED
        for child in self.cutout_settings_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                for subchild in child.winfo_children():
                    if isinstance(subchild, ttk.Entry):
                        subchild.config(state=state)

    def on_crop_setting_changed(self):
        """Handle crop setting change"""
        if self.input_entry.get().strip() and os.path.exists(self.input_entry.get().strip()):
            self.load_image(self.input_entry.get().strip())

    def on_threshold_changed(self, value):
        """Handle threshold slider change"""
        if self.crop_to_subject_var.get() and self.input_entry.get().strip() and os.path.exists(self.input_entry.get().strip()):
            self.load_image(self.input_entry.get().strip())

    def find_subject_bounds(self, img_array, threshold=240):
        """Find the bounding box of the subject (non-background area)"""
        if img_array.mode != 'L':
            img_array = img_array.convert('L')
        
        pixels = img_array.load()
        width, height = img_array.size
        
        min_x = width
        max_x = 0
        min_y = height
        max_y = 0
        found_pixels = False
        
        for y in range(height):
            for x in range(width):
                if pixels[x, y] < threshold:
                    found_pixels = True
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
        
        if not found_pixels:
            return None
        
        padding_x = int((max_x - min_x) * 0.05)
        padding_y = int((max_y - min_y) * 0.05)
        
        min_x = max(0, min_x - padding_x)
        max_x = min(width - 1, max_x + padding_x)
        min_y = max(0, min_y - padding_y)
        max_y = min(height - 1, max_y + padding_y)
        
        return (min_x, min_y, max_x, max_y)

    def create_subject_mask(self, img, threshold=240):
        """Create a binary mask where subject is white (255) and background is black (0)"""
        if img.mode != 'L':
            img = img.convert('L')
        mask = img.point(lambda p: 255 if p < threshold else 0)
        return mask

    def trace_silhouette(self, mask, margin_px=0):
        """Trace the outline of the subject in the mask"""
        from PIL import ImageFilter
        
        if margin_px > 0:
            dilated = mask.copy()
            for _ in range(margin_px):
                dilated = dilated.filter(ImageFilter.MaxFilter(3))
            mask = dilated
        
        width, height = mask.size
        pixels = mask.load()
        
        # Find starting point
        start_x = start_y = None
        for y in range(height):
            for x in range(width):
                if pixels[x, y] > 128:
                    start_x, start_y = x, y
                    break
            if start_x is not None:
                break
        
        if start_x is None:
            return []
        
        # Moore-Neighbor tracing
        contour = []
        current_x, current_y = start_x, start_y
        direction = 0
        max_points = 10000
        
        while len(contour) < max_points:
            contour.append((current_x, current_y))
            
            found = False
            for i in range(8):
                check_dir = (direction + 7 + i) % 8
                nx, ny = current_x, current_y
                
                if check_dir == 0: nx += 1
                elif check_dir == 1: nx += 1; ny += 1
                elif check_dir == 2: ny += 1
                elif check_dir == 3: nx -= 1; ny += 1
                elif check_dir == 4: nx -= 1
                elif check_dir == 5: nx -= 1; ny -= 1
                elif check_dir == 6: ny -= 1
                elif check_dir == 7: nx += 1; ny -= 1
                
                if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] > 128:
                    current_x, current_y = nx, ny
                    direction = check_dir
                    found = True
                    break
            
            if not found:
                break
            
            if current_x == start_x and current_y == start_y and len(contour) > 10:
                break
        
        if len(contour) > 3:
            contour = self.simplify_contour(contour, 1.0)
        
        return contour

    def simplify_contour(self, points, tolerance=1.0):
        """Ramer-Douglas-Peucker algorithm to simplify a polyline"""
        if len(points) <= 2:
            return points
        
        start = points[0]
        end = points[-1]
        
        max_dist = 0
        max_index = 0
        
        for i in range(1, len(points) - 1):
            dist = self.point_line_distance(points[i], start, end)
            if dist > max_dist:
                max_dist = dist
                max_index = i
        
        if max_dist > tolerance:
            left = self.simplify_contour(points[:max_index + 1], tolerance)
            right = self.simplify_contour(points[max_index:], tolerance)
            return left[:-1] + right
        else:
            return [start, end]
    
    def point_line_distance(self, point, line_start, line_end):
        """Calculate distance from point to line segment"""
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end
        
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return math.hypot(x0 - x1, y0 - y1)
        
        t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        
        return math.hypot(x0 - proj_x, y0 - proj_y)

    def contour_to_mm(self, contour, img_width, img_height, output_width_mm, output_height_mm, margin_mm):
        """Convert pixel contour coordinates to mm coordinates"""
        scale_x = output_width_mm / img_width
        scale_y = output_height_mm / img_height
        
        mm_points = []
        for x, y in contour:
            x_mm = x * scale_x
            y_mm = (img_height - y) * scale_y
            mm_points.append((x_mm, y_mm))
        
        if margin_mm > 0:
            cx = sum(p[0] for p in mm_points) / len(mm_points)
            cy = sum(p[1] for p in mm_points) / len(mm_points)
            
            expanded = []
            for x, y in mm_points:
                dx = x - cx
                dy = y - cy
                dist = math.hypot(dx, dy)
                if dist > 0:
                    scale = (dist + margin_mm) / dist
                    x_new = cx + dx * scale
                    y_new = cy + dy * scale
                else:
                    x_new, y_new = x, y
                expanded.append((x_new, y_new))
            mm_points = expanded
        
        return mm_points

    def generate_cutout_gcode(self, contour_mm, safe_z, surface_z, cut_depth, pass_depth, feed_rate, plunge_rate, tool_number):
        """Generate G-code for cutting along the silhouette contour"""
        if not contour_mm or len(contour_mm) < 3:
            return None
        
        gcode = []
        gcode.append("(Silhouette cut-out toolpath)")
        gcode.append(f"(Tool T{tool_number})")
        gcode.append(f"M6 T{tool_number}")
        gcode.append(f"G0 Z{safe_z:.3f}")
        
        total_depth = abs(cut_depth)
        depth_per_pass = abs(pass_depth)
        num_passes = max(1, int(math.ceil(total_depth / depth_per_pass)))
        
        for pass_num in range(num_passes):
            current_depth = min(total_depth, (pass_num + 1) * depth_per_pass)
            z_cut = surface_z - current_depth
            
            first_x, first_y = contour_mm[0]
            gcode.append(f"G0 X{first_x:.3f} Y{first_y:.3f}")
            gcode.append(f"G1 Z{z_cut:.3f} F{plunge_rate}")
            
            for x, y in contour_mm[1:]:
                gcode.append(f"G1 X{x:.3f} Y{y:.3f} F{feed_rate}")
            
            gcode.append(f"G1 X{first_x:.3f} Y{first_y:.3f} F{feed_rate}")
            
            if pass_num < num_passes - 1:
                gcode.append(f"G0 Z{safe_z:.3f}")
        
        gcode.append(f"G0 Z{safe_z:.3f}")
        gcode.append("M5")
        
        return gcode

    def load_image(self, path):
        try:
            if not os.path.exists(path):
                self.status_var.set(f"Image not found: {path}")
                self.img_label.config(image="", text="No image loaded.")
                self.img_info_var.set("")
                return

            print(f"Opening image: {path}")
            original_img = Image.open(path)
            print(f"Original image size: {original_img.size}")
            
            if self.crop_to_subject_var.get():
                print("Detecting subject...")
                self.subject_mask = self.create_subject_mask(original_img, self.background_threshold_var.get())
                
                bounds = self.find_subject_bounds(original_img, self.background_threshold_var.get())
                
                if bounds:
                    min_x, min_y, max_x, max_y = bounds
                    print(f"Subject bounds: {bounds}")
                    
                    self.cropped_img = original_img.crop((min_x, min_y, max_x + 1, max_y + 1))
                    self.subject_mask = self.subject_mask.crop((min_x, min_y, max_x + 1, max_y + 1))
                    preview_img = self.cropped_img.copy()
                    self.orig_img_size = self.cropped_img.size
                    
                    original_area = original_img.size[0] * original_img.size[1]
                    cropped_area = self.cropped_img.size[0] * self.cropped_img.size[1]
                    savings = (1 - cropped_area / original_area) * 100
                    
                    self.status_var.set(f"Cropped to subject (saved {savings:.0f}% material)")
                else:
                    self.status_var.set("Warning: Could not detect subject, using full image")
                    preview_img = original_img.copy()
                    self.orig_img_size = original_img.size
                    self.cropped_img = None
                    self.subject_mask = None
                    messagebox.showwarning("Warning", "Could not detect subject with current threshold. Try adjusting the brightness threshold or disable 'Crop to subject'.")
            else:
                preview_img = original_img.copy()
                self.orig_img_size = original_img.size
                self.cropped_img = None
                self.subject_mask = None
            
            preview_width = 700
            preview_height = 520
            preview_img.thumbnail((preview_width, preview_height))
            preview_w, preview_h = preview_img.size

            self.tk_img = ImageTk.PhotoImage(preview_img)
            self.img_label.config(image=self.tk_img, text="")

            self.update_img_info(preview_w, preview_h)

        except Exception as e:
            error_msg = f"Error loading image: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.status_var.set(f"Error loading image: {str(e)}")
            self.img_label.config(image="", text=f"Error loading image:\n{str(e)}")
            self.img_info_var.set("")

    def update_output_path(self):
        try:
            input_path = self.input_entry.get().strip()
            if input_path and os.path.exists(input_path):
                base = os.path.splitext(os.path.basename(input_path))[0]
                if self.crop_to_subject_var.get():
                    base += "_cropped"
            else:
                base = "photo_engrave"
            self.output_path = os.path.join(self.output_dir, base + ".gc")
            self.output_path_var.set(self.output_path)
        except Exception as e:
            print(f"Error updating output path: {e}")
            self.output_path_var.set("Error generating path")

    def browse_image(self):
        try:
            filename = filedialog.askopenfilename(
                title="Select Image File",
                filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif"), ("All files", "*.*")],
                parent=self.root
            )
            
            if filename and os.path.exists(filename):
                self.input_entry.delete(0, tk.END)
                self.input_entry.insert(0, filename)
                self.update_output_path()
                self.load_image(filename)
                self.status_var.set(f"Loaded: {os.path.basename(filename)}")
            elif filename:
                self.status_var.set(f"File not found: {filename}")
        except Exception as e:
            error_msg = f"Error browsing for image: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.status_var.set(f"Error: {str(e)}")

    def browse_output_folder(self):
        try:
            new_dir = filedialog.askdirectory(title="Select CNC Output Folder", initialdir=self.output_dir, parent=self.root)
            if new_dir and os.path.exists(new_dir):
                self.output_dir = new_dir
                self.config["output_dir"] = new_dir
                save_config(self.config)
                self.update_output_path()
                self.status_var.set(f"Output folder set to: {new_dir}")
        except Exception as e:
            print(f"Error selecting folder: {e}")

    def update_img_info(self, preview_w=None, preview_h=None):
        if self.orig_img_size:
            w, h = self.orig_img_size
            info_text = f"Image size: {w} x {h} px"
            if self.crop_to_subject_var.get() and self.cropped_img:
                info_text += " (cropped to subject)"
            info_text += f" | Output: {self.width_var.get()} x {self.height_var.get()} mm"
            if preview_w and preview_h:
                info_text += f" | Preview: {preview_w} x {preview_h} px"
            self.img_info_var.set(info_text)

    def save_gcode_button(self):
        self.update_output_path()

        self.params["input_image"] = self.input_entry.get()
        self.params["output_gcode"] = self.output_path
        self.params["width_mm"] = self.width_var.get()
        self.params["height_mm"] = self.height_var.get()
        self.params["line_spacing_mm"] = self.line_spacing_var.get()
        self.params["pixel_spacing_mm"] = self.pixel_spacing_var.get()
        self.params["safe_z"] = self.safe_z_var.get()
        self.params["surface_z"] = self.surface_z_var.get()
        self.params["max_depth"] = self.max_depth_var.get()
        self.params["feed_rate"] = self.feed_rate_var.get()
        self.params["plunge_rate"] = self.plunge_rate_var.get()
        self.params["spindle_speed"] = self.spindle_speed_var.get()
        self.params["invert_image"] = self.invert_image_var.get()
        self.params["crop_to_subject"] = self.crop_to_subject_var.get()
        self.params["background_threshold"] = self.background_threshold_var.get()
        self.params["cutout_enabled"] = self.cutout_enabled_var.get()
        self.params["cutout_margin_mm"] = self.cutout_margin_var.get()
        self.params["cutout_depth_mm"] = self.cutout_depth_var.get()
        self.params["cutout_pass_depth_mm"] = self.cutout_pass_depth_var.get()
        self.params["cutout_feed_rate"] = self.cutout_feed_var.get()
        self.params["cutout_plunge_rate"] = self.cutout_plunge_var.get()
        self.params["cutout_tool_number"] = self.cutout_tool_var.get()
        self.params["cutout_silhouette_simplify"] = self.cutout_simplify_var.get()

        try:
            self.generate_gcode()
            
            if self.cutout_enabled_var.get():
                self.generate_cutout()
                cutout_path = self.output_path.replace(".gc", "_cutout.nc")
                messagebox.showinfo("Success", f"Files saved:\nEngraving: {self.output_path}\nCut-out: {cutout_path}")
            else:
                messagebox.showinfo("Success", f"G-code saved as:\n{self.output_path}")
                
        except Exception as e:
            error_msg = f"Error generating G-code: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.status_var.set(f"Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to generate G-code:\n{str(e)}")

    def generate_cutout(self):
        """Generate silhouette cut-out G-code"""
        if not self.cropped_img and not self.crop_to_subject_var.get():
            messagebox.showwarning("Warning", "Cut-out requires 'Crop to subject' to be enabled in the Engraving Settings tab.")
            return
        
        if not self.cropped_img:
            messagebox.showwarning("Warning", "No cropped image available. Please load an image with 'Crop to subject' enabled.")
            return
        
        safe_z = self.safe_z_var.get()
        surface_z = self.surface_z_var.get()
        cut_depth = self.cutout_depth_var.get()
        pass_depth = self.cutout_pass_depth_var.get()
        feed_rate = self.cutout_feed_var.get()
        plunge_rate = self.cutout_plunge_var.get()
        tool_number = self.cutout_tool_var.get()
        margin_mm = self.cutout_margin_var.get()
        simplify_tolerance = self.cutout_simplify_var.get()
        
        img_width, img_height = self.cropped_img.size
        output_width_mm = self.width_var.get()
        output_height_mm = self.height_var.get()
        
        scale_x = output_width_mm / img_width if img_width > 0 else 1
        margin_px = int(margin_mm / scale_x) if scale_x > 0 else 0
        
        print("Tracing silhouette...")
        contour_px = self.trace_silhouette(self.subject_mask, margin_px)
        
        if len(contour_px) < 3:
            raise ValueError("Could not trace subject outline. Try adjusting the background threshold.")
        
        print(f"Traced {len(contour_px)} points")
        
        tolerance_px = simplify_tolerance / scale_x if scale_x > 0 else 1
        contour_px = self.simplify_contour(contour_px, tolerance_px)
        print(f"Simplified to {len(contour_px)} points")
        
        contour_mm = self.contour_to_mm(contour_px, img_width, img_height, output_width_mm, output_height_mm, 0)
        
        cutout_gcode = self.generate_cutout_gcode(contour_mm, safe_z, surface_z, cut_depth, pass_depth, feed_rate, plunge_rate, tool_number)
        
        if cutout_gcode is None:
            raise ValueError("Failed to generate cut-out G-code")
        
        cutout_path = self.output_path.replace(".gc", "_cutout.nc")
        with open(cutout_path, "w") as f:
            f.write("\n".join(cutout_gcode))
        
        self.status_var.set(f"Cut-out saved: {os.path.basename(cutout_path)}")
        print(f"Cut-out G-code saved to: {cutout_path}")

    def generate_gcode(self):
        input_image = self.params["input_image"]
        output_gcode = self.params["output_gcode"]
        width_mm = self.params["width_mm"]
        height_mm = self.params["height_mm"]
        line_spacing_mm = self.params["line_spacing_mm"]
        pixel_spacing_mm = self.params["pixel_spacing_mm"]
        safe_z = self.params["safe_z"]
        surface_z = self.params["surface_z"]
        max_depth = abs(self.params["max_depth"])
        feed_rate = self.params["feed_rate"]
        plunge_rate = self.params["plunge_rate"]
        spindle_speed = self.params["spindle_speed"]
        invert_image = self.params["invert_image"]
        crop_to_subject = self.params["crop_to_subject"]
        background_threshold = self.params["background_threshold"]

        if not input_image or not os.path.exists(input_image):
            raise FileNotFoundError(f"Please select an image file first")

        if line_spacing_mm <= 0 or pixel_spacing_mm <= 0:
            raise ValueError("Line spacing and pixel spacing must be greater than zero.")

        if crop_to_subject and self.cropped_img:
            img = self.cropped_img.copy()
            print(f"Using cropped image: {img.size}")
        else:
            img = Image.open(input_image).convert("L")
            if crop_to_subject:
                print("Cropping to subject for G-code generation...")
                bounds = self.find_subject_bounds(img, background_threshold)
                if bounds:
                    min_x, min_y, max_x, max_y = bounds
                    img = img.crop((min_x, min_y, max_x + 1, max_y + 1))
                    print(f"Cropped to: {img.size}")
        
        if img.mode != 'L':
            img = img.convert('L')
        
        cols = max(1, int(width_mm / pixel_spacing_mm))
        rows = max(1, int(height_mm / line_spacing_mm))

        print(f"Generating G-code: {cols} x {rows} points")
        
        img = img.resize((cols, rows))
        pixels = img.load()

        gcode = []
        gcode.append("(Photo engraving generated by Python)")
        gcode.append(f"(Input image: {os.path.basename(input_image)})")
        if crop_to_subject:
            gcode.append("(Mode: Cropped to subject only)")
        gcode.append(f"(Output size: {width_mm} x {height_mm} mm)")
        gcode.append(f"(Raster grid: {cols} columns x {rows} rows)")
        gcode.append(f"(Max depth: {max_depth} mm)")
        gcode.append("G21  (mm)")
        gcode.append("G90  (absolute positioning)")
        gcode.append("G17")
        gcode.append("G94")
        gcode.append(f"S{spindle_speed} M3")
        gcode.append(f"G0 Z{safe_z:.3f}")
        gcode.append("G0 X0 Y0")

        engraved_points = 0
        skipped_points = 0

        for row in range(rows):
            y = row * line_spacing_mm

            if row % 2 == 0:
                x_range = range(cols)
            else:
                x_range = range(cols - 1, -1, -1)

            first_point = True

            for col in x_range:
                x = col * pixel_spacing_mm
                brightness = pixels[col, rows - 1 - row]
                
                if crop_to_subject:
                    if brightness >= background_threshold:
                        skipped_points += 1
                        first_point = True
                        continue

                if invert_image:
                    brightness = 255 - brightness

                darkness = 1.0 - (brightness / 255.0)
                z = surface_z - (darkness * max_depth)

                if first_point:
                    gcode.append(f"G0 Z{safe_z:.3f}")
                    gcode.append(f"G0 X{x:.3f} Y{y:.3f}")
                    gcode.append(f"G1 Z{z:.3f} F{plunge_rate}")
                    first_point = False
                    engraved_points += 1
                else:
                    gcode.append(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feed_rate}")
                    engraved_points += 1

        gcode.append(f"G0 Z{safe_z:.3f}")
        gcode.append("M5")
        gcode.append("G0 X0 Y0")
        gcode.append("M30")

        output_folder = os.path.dirname(output_gcode)
        if output_folder:
            os.makedirs(output_folder, exist_ok=True)

        with open(output_gcode, "w") as f:
            f.write("\n".join(gcode))
        
        total_points = cols * rows
        if crop_to_subject:
            percent_engraved = (engraved_points / total_points) * 100
            self.status_var.set(f"G-code saved! Engraved {engraved_points}/{total_points} points ({percent_engraved:.1f}% of image)")
            print(f"Engraved: {engraved_points}, Skipped: {skipped_points} (background)")
        else:
            self.status_var.set(f"G-code saved to: {output_gcode}")
        
        print(f"G-code saved to: {output_gcode}")


def main():
    print("=" * 50)
    print("Photo Engraving G-code Generator - Pet Portrait Edition")
    print("=" * 50)
    print("Checking dependencies...")
    
    try:
        root = tk.Tk()
        app = EngraveApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Fatal error: {e}")
        print(traceback.format_exc())
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()

