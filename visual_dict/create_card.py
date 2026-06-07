#!/usr/bin/env python3
"""Generate visual-dictionary HTML cards from images.

Modes:
 - Single image: --image /path.jpg --italian "la panna" --english "cream"
 - CSV batch: --csv list.csv  (CSV columns: image,italian,english)
 - Directory parse mode: --dir images/  (attempts to parse filename into italian - english)

The script copies images into `output/assets/` and writes `output/<slug>.html` files.
Supports optional image resizing (Pillow) via `--max-width`.
"""
import argparse
from pathlib import Path
import shutil
import html
import csv
import sys

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

TEMPLATE = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")


def slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s).strip("_").lower()


def copy_and_optional_resize(src: Path, dest: Path, max_width: int | None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if max_width and PIL_AVAILABLE:
        try:
            with Image.open(src) as im:
                w, h = im.size
                if w > max_width:
                    new_h = int((max_width / w) * h)
                    im = im.resize((max_width, new_h), Image.LANCZOS)
                im.save(dest)
                return
        except Exception:
            # fallback to copy if Pillow fails for any image
            pass
    shutil.copy2(src, dest)


def make_card(image_path: Path, italian: str, english: str, output_dir: Path, max_width: int | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    image_path = image_path.expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    dest_name = f"{slugify(image_path.stem)}{image_path.suffix.lower()}"
    dest_path = assets_dir / dest_name
    copy_and_optional_resize(image_path, dest_path, max_width)

    # Prepare HTML
    data = {
        "image_file": f"assets/{dest_name}",
        "italian": html.escape(italian),
        "english": html.escape(english),
        "title": html.escape(italian + ' — ' + english),
    }

    html_text = TEMPLATE.format(**data)

    out_filename = f"{slugify(italian)}.html"
    out_path = output_dir / out_filename
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def process_csv(csv_path: Path, output_dir: Path, max_width: int | None):
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required = {"image", "italian", "english"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV must have header columns: image,italian,english")
        results = []
        for row in reader:
            img = Path(row["image"]).expanduser()
            it = row["italian"].strip()
            en = row["english"].strip()
            out = make_card(img, it, en, output_dir, max_width)
            results.append(out)
        return results


def parse_filename_label(fn: str) -> tuple[str, str] | None:
    # Try common separators: ' - ' , ' __ ' , ' -- '
    base = Path(fn).stem
    for sep in (" - ", "__", " -- "):
        if sep in base:
            parts = base.split(sep, 1)
            return parts[0].replace("_", " ").strip(), parts[1].replace("_", " ").strip()
    return None


def process_dir(dir_path: Path, output_dir: Path, max_width: int | None):
    imgs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif"):
        imgs.extend(dir_path.glob(ext))
    results = []
    for img in imgs:
        parsed = parse_filename_label(img.name)
        if not parsed:
            print(f"Skipping (no label in filename): {img.name}")
            continue
        italian, english = parsed
        out = make_card(img, italian, english, output_dir, max_width)
        results.append(out)
    return results


def main():
    p = argparse.ArgumentParser(description="Create visual-dictionary HTML cards from images (single, CSV, or directory).")
    p.add_argument("--image", help="Path to single image file")
    p.add_argument("--italian", help="Italian label for single image")
    p.add_argument("--english", help="English translation for single image")
    p.add_argument("--csv", help="CSV file with header image,italian,english for batch mode")
    p.add_argument("--dir", help="Directory of images; filenames parsed as 'italian - english' in name")
    p.add_argument("--output", default="visual_cards", help="Output directory (default: visual_cards)")
    p.add_argument("--max-width", type=int, help="Optional max width for copied images (requires Pillow)")
    args = p.parse_args()

    out = Path(args.output)
    try:
        if args.csv:
            csvp = Path(args.csv)
            results = process_csv(csvp, out, args.max_width)
            for r in results:
                print(f"Wrote: {r}")
            print(f"Done. {len(results)} cards written to {out}")
            return

        if args.dir:
            d = Path(args.dir)
            results = process_dir(d, out, args.max_width)
            for r in results:
                print(f"Wrote: {r}")
            print(f"Done. {len(results)} cards written to {out}")
            return

        if args.image:
            if not (args.italian and args.english):
                raise SystemExit("For single-image mode provide --italian and --english")
            image = Path(args.image)
            card = make_card(image, args.italian, args.english, out, args.max_width)
            print(f"Wrote: {card}")
            print("Open the HTML file in your browser to preview.")
            return

        p.print_help()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
