import json
import os
import requests
import argparse
import math
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_data = {}
        self.footer_data = {}
        self.downloaded_images = {}
        self.columns = {}
        self.current_column = None

    def set_header_data(self, data): self.header_data = data or {}
    def set_footer_data(self, data): self.footer_data = data or {}
    def set_downloaded_images(self, images): self.downloaded_images = images or {}

    def header(self):
        if not self.header_data: return
        self.process_elements(self.header_data.get("elements", []))

    def footer(self):
        if not self.footer_data: return
        for element in self.footer_data.get("elements", []):
            if element.get("type") == "text":
                self.set_y(element.get("y", -15))
                self.set_font(element.get("font_family"), element.get("font_style", ""), element.get("font_size"))
                self.set_text_color(element.get("r"), element.get("g"), element.get("b"))
                content = element.get("content", "").replace("{page_num}", str(self.page_no()))
                self.cell(w=0, h=10, text=content, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=element.get("align", "C"))

    def add_column(self, name, x, y, w):
        self.columns[name] = {'x': x, 'y': y, 'w': w, 'start_y': y, 'current_y': y}

    def use_column(self, name):
        self.current_column = name
        if name in self.columns:
            col = self.columns[name]
            self.set_xy(col['x'], col['current_y'])

    def add_spacing(self, h):
        if self.current_column and self.current_column in self.columns:
            self.columns[self.current_column]['current_y'] += h
            self.set_y(self.columns[self.current_column]['current_y'])

    def get_current_column_width(self):
        if self.current_column and self.current_column in self.columns:
            return self.columns[self.current_column]['w']
        return self.w - self.l_margin - self.r_margin

    def clipping_rounded_rect(self, x, y, w, h, r):
        self.unifont_subset = False; k = self.k; hp = self.h
        self._out(f'{x*k:.2f} {(hp-y)*k:.2f} m'); self._out(f'{(x+w-r)*k:.2f} {(hp-y)*k:.2f} l')
        self._out(f'{(x+w)*k:.2f} {(hp-y)*k:.2f} {(x+w)*k:.2f} {(hp-(y+r))*k:.2f} {(x+w-r)*k:.2f} {(hp-(y+r))*k:.2f} c')
        self._out(f'{(x+w)*k:.2f} {(hp-(y+h-r))*k:.2f} l'); self._out(f'{(x+w)*k:.2f} {(hp-(y+h))*k:.2f} {(x+w-r)*k:.2f} {(hp-(y+h))*k:.2f} {(x+w-r)*k:.2f} {(hp-(y+h-r))*k:.2f} c')
        self._out(f'{(x+r)*k:.2f} {(hp-(y+h))*k:.2f} l'); self._out(f'{x*k:.2f} {(hp-(y+h))*k:.2f} {x*k:.2f} {(hp-(y+h-r))*k:.2f} {(x+r)*k:.2f} {(hp-(y+h-r))*k:.2f} c')
        self._out(f'{x*k:.2f} {(hp-(y+r))*k:.2f} l'); self._out(f'{x*k:.2f} {(hp-y)*k:.2f} {(x+r)*k:.2f} {(hp-y)*k:.2f} {(x+r)*k:.2f} {(hp-(y+r))*k:.2f} c')
        self._out('h W n')

    def clipping_circle(self, x, y, r):
        self.unifont_subset = False
        self.ellipse(x - r, y - r, 2 * r, 2 * r)
        self._out('h W n')

    def pie_chart(self, x, y, r, title, data):
        self.set_xy(x, y - r - 15)
        self.set_font("Roboto", 'B', size=10)
        self.set_text_color(40, 40, 40)
        self.cell(w=2*r, text=title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        total = sum(data.values())
        colors = [(80, 120, 255), (255, 130, 80), (100, 200, 100), (220, 220, 100)]
        angle_start = 0
        for i, (label, value) in enumerate(data.items()):
            angle_end = angle_start + (value / total) * 360
            color = colors[i % len(colors)]
            self.set_fill_color(color[0], color[1], color[2])
            points = [(x, y)]
            for angle in range(int(angle_start), int(angle_end) + 1):
                rad = math.radians(angle)
                points.append( (x + r * math.cos(rad), y + r * math.sin(rad)) )
            points.append((x, y))
            self.polygon(points, style="F")
            angle_start = angle_end
        self.set_xy(x + r + 15, y - r/2)
        for i, (label, value) in enumerate(data.items()):
            color = colors[i % len(colors)]
            self.set_fill_color(color[0], color[1], color[2])
            self.rect(self.get_x(), self.get_y()+1, 3, 3, style="F")
            self.set_xy(self.get_x() + 5, self.get_y())
            self.set_font("Roboto", size=9)
            self.set_text_color(80, 80, 80)
            self.cell(text=f"{label} ({value}%)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)

    def process_elements(self, elements):
        for element in elements:
            el_type = element.get("type")

            if el_type in ["define_column", "use_column", "add_spacing"]:
                if el_type == "define_column":
                    self.add_column(element.get("name"), element.get("x"), element.get("y"), element.get("w"))
                elif el_type == "use_column":
                    self.use_column(element.get("name"))
                elif el_type == "add_spacing":
                    self.add_spacing(element.get("h"))
                continue

            if "x" in element and "y" in element:
                self.set_xy(element['x'], element['y'])
            elif self.current_column:
                self.use_column(self.current_column)

            if el_type == "text":
                self.set_font(element.get("font_family"), size=element.get("font_size", 12))
                self.set_text_color(element.get("r",0), element.get("g",0), element.get("b",0))

                align = element.get("align", "L")
                if align.lower() == "center":
                    align = "C"
                elif align.lower() == "right":
                    align = "R"
                else:
                    align = "L"

                content = element.get("content", "")
                content = content.replace("<b>", "**").replace("</b>", "**")

                if self.current_column:
                    col = self.columns[self.current_column]
                    self.multi_cell(w=col['w'], text=content, markdown=True, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    self.columns[self.current_column]['current_y'] = self.get_y()
                else:
                    self.multi_cell(w=0, text=content, markdown=True, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            elif el_type == "toc_item":
                col_width = self.get_current_column_width()
                self.set_font("Roboto", 'B', size=12); self.set_text_color(80, 80, 80)
                self.cell(w=10, text=element.get("number") + ".")
                self.set_font("Roboto", size=12); self.set_text_color(80, 80, 80)
                self.cell(text=" " + element.get("title"))

                title_width = self.get_string_width(element.get("title") + " " + element.get("number") + ".") + 10
                page_width = self.get_string_width(element.get("page"))
                dot_width = col_width - title_width - page_width
                dots = " ." * int(dot_width / self.get_string_width(" ."))

                self.cell(w=dot_width, text=dots, align="R")
                self.cell(text=element.get("page"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                if self.current_column: self.columns[self.current_column]['current_y'] = self.get_y()

            elif el_type == "icon_block":
                col = self.columns[self.current_column]
                icon_path = self.downloaded_images.get(element.get("icon_nickname"))
                if icon_path: self.image(icon_path, x=col['x'], y=col['current_y'], w=8)
                self.set_xy(col['x'] + 12, col['current_y'])
                self.set_font("Roboto", 'B', size=8); self.set_text_color(180, 180, 180)
                self.cell(text=element.get("title"))
                self.set_xy(col['x'] + 12, col['current_y'] + 4)
                self.set_font("RobotoLight", size=12); self.set_text_color(40, 40, 40)
                self.cell(text=element.get("value"))
                if self.current_column: self.columns[self.current_column]['current_y'] += 15 # Manual height for this block

            elif el_type == "circular_image":
                path = self.downloaded_images.get(element.get("nickname"))
                if path:
                    col = self.columns[self.current_column]
                    radius = element.get("r")
                    center_x = col['x'] + col['w'] / 2
                    self.clipping_circle(center_x, col['current_y'] + radius, radius)
                    self.image(path, x=center_x - radius, y=col['current_y'], w=2*radius)
                    self.clipping_circle(0, 0, 0)
                    if self.current_column: self.columns[self.current_column]['current_y'] += (radius * 2)

            elif el_type == "pie_chart":
                col = self.columns[self.current_column]
                radius = element.get("r")
                center_x = col['x'] + col['w'] / 2
                self.pie_chart(center_x - radius - 10, col['current_y'] + radius + 10, radius, element.get("title"), element.get("data"))
                if self.current_column: self.columns[self.current_column]['current_y'] += (radius * 2) + 20

            elif el_type == "progress_bar":
                y = element.get("y") if "y" in element else self.get_y()
                x = element.get("x") if "x" in element else self.l_margin
                w, h = element.get("w"), element.get("h")
                value, max_value = element.get("value"), element.get("max_value")
                fill_w = (value / max_value) * w
                self.set_xy(x, y - 5)
                self.set_font("Roboto", size=8); self.set_text_color(150, 150, 150)
                self.cell(text=element.get("label"))
                self.set_fill_color(230, 230, 230); self.rect(x, y, w, h, style="F")
                self.set_fill_color(80, 120, 255); self.rect(x, y, fill_w, h, style="F")
                if self.current_column: self.columns[self.current_column]['current_y'] = y + h

            elif el_type == "rectangle":
                self.set_fill_color(element.get("r", 0), element.get("g", 0), element.get("b", 0))
                with self.local_context(fill_opacity=element.get("opacity", 1.0)):
                    self.rect(x=element.get("x", 0), y=element.get("y", 0), w=element.get("w", 0), h=element.get("h", 0), style='F')

            elif el_type == "line":
                self.set_draw_color(element.get("r", 0), element.get("g", 0), element.get("b", 0))
                self.set_line_width(element.get("width", 0.2))
                self.line(element.get("x1"), element.get("y1"), element.get("x2"), element.get("y2"))

            else:
                path = self.downloaded_images.get(element.get("nickname"))
                if not path or not os.path.exists(path): continue
                if el_type == "image":
                    self.image(path, x=element.get("x", 0), y=element.get("y", 0), w=element.get("w", 0), h=element.get("h", 0))
                elif el_type == "rounded_image":
                    self.clipping_rounded_rect(x=element.get("x"), y=element.get("y"), w=element.get("w"), h=element.get("h"), r=element.get("r"))
                    self.image(path, x=element.get("x", 0), y=element.get("y", 0), w=element.get("w", 0), h=element.get("h", 0))
                    self.clipping_rounded_rect(0, 0, 0, 0, 0)

def create_pdf_from_instructions(instruction_file, output_filename):
    with open(instruction_file, 'r') as f: instructions = json.load(f)
    temp_dir, output_dir, fonts_dir = "temp_images", "output", "fonts"
    for folder in [temp_dir, output_dir, fonts_dir]:
        if not os.path.exists(folder): os.makedirs(folder)
    print("Downloading image assets...")
    downloaded_images = {}
    for nickname, url in instructions.get("image_sources", {}).items():
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status()
            local_path = os.path.join(temp_dir, f"{nickname}.png")
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_images[nickname] = local_path
            print(f"  - Downloaded '{nickname}'")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {url}: {e}")
            downloaded_images[nickname] = None
    pdf = PDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)
    pdf.set_header_data(instructions.get("header"))
    pdf.set_footer_data(instructions.get("footer"))
    pdf.set_downloaded_images(downloaded_images)
    print("Loading custom fonts...")
    for font in instructions.get("fonts", []):
        family = font.get("family")
        if "styles" in font:
            for style, filename in font["styles"].items():
                font_path = os.path.join(fonts_dir, filename)
                if os.path.exists(font_path):
                    style_map = {"regular": "", "bold": "B", "italic": "I", "bold_italic": "BI"}
                    pdf.add_font(family, style=style_map.get(style, ""), fname=font_path)
                    print(f"  - Loaded style '{style}' for family '{family}'")
        else:
            filename = font.get("file")
            font_path = os.path.join(fonts_dir, filename)
            if os.path.exists(font_path):
                pdf.add_font(family, fname=font_path)
                print(f"  - Loaded font family '{family}' from {filename}")
    print("Building PDF pages...")
    for i, page_data in enumerate(instructions.get("pages", [])):
        pdf.add_page()
        pdf.columns = {} # Reset columns for each new page
        pdf.current_column = None
        print(f"  - Creating Page {i+1}...")
        pdf.process_elements(page_data.get("elements", []))
    output_path = os.path.join(output_dir, output_filename)
    pdf.output(output_path)
    print(f"PDF successfully saved to '{output_path}'")
    print("Cleaning up temporary files...")
    for local_path in downloaded_images.values():
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
    if os.path.exists(temp_dir) and not os.listdir(temp_dir):
        os.rmdir(temp_dir)
    print("Cleanup complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a PDF from a JSON instruction file.")
    parser.add_argument("-i", "--input", default="instructions.json", help="Input JSON instruction file name.")
    parser.add_argument("-o", "--output", default="output.pdf", help="Output PDF file name.")
    args = parser.parse_args()
    if os.path.exists(args.input):
        create_pdf_from_instructions(args.input, args.output)
    else:
        print(f"Error: Input file '{args.input}' not found.")