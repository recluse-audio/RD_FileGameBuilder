#!/usr/bin/env python3
"""
Resize PNG images from PNG/ORIGINAL_SIZE/ to a sized output directory,
mirroring the subdirectory structure.

Example:
  PNG/ORIGINAL_SIZE/AVERY/DESK/BOOKS/file.png
    -> PNG/320x240/AVERY/DESK/BOOKS/file_320x240.png

By default, maintains aspect ratio and crops to fill (no letterboxing).
Use --stretch for scaling without aspect ratio preservation.
"""

import argparse
from pathlib import Path
from PIL import Image

def resize_crop(img, target_size=(320, 240)):
    """
    Resize image to fill target size while maintaining aspect ratio,
    cropping any overflow from the center.
    """
    img_ratio = img.width / img.height
    target_ratio = target_size[0] / target_size[1]

    if img_ratio > target_ratio:
        new_height = target_size[1]
        new_width = int(new_height * img_ratio)
    else:
        new_width = target_size[0]
        new_height = int(new_width / img_ratio)

    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    x = (new_width  - target_size[0]) // 2
    y = (new_height - target_size[1]) // 2
    return resized.crop((x, y, x + target_size[0], y + target_size[1]))

def resize_stretch(img, target_size=(320, 240)):
    """Resize image to exact target size, stretching/distorting as needed."""
    return img.resize(target_size, Image.Resampling.LANCZOS)

def resize_images(source_root, target_root, target_size=(320, 240), stretch=False, force=False):
    """
    Recursively resize all PNG images from source_root to target_root,
    mirroring the subdirectory structure.
    """
    source_root = Path(source_root)
    target_root = Path(target_root)

    if not source_root.exists():
        print(f"Error: Source directory {source_root} does not exist")
        return

    print(f"Source: {source_root}")
    print(f"Target: {target_root}")
    print(f"Target size: {target_size[0]}x{target_size[1]}")
    print(f"Mode: {'Stretch (no aspect ratio)' if stretch else 'Maintain aspect ratio'}\n")

    png_files = list(source_root.rglob("*.png"))

    if not png_files:
        print("No PNG files found under source directory")
        return

    print(f"Found {len(png_files)} PNG files\n")

    resized = skipped = failed = 0
    size_suffix = f"_{target_size[0]}x{target_size[1]}"

    for png_file in png_files:
        rel = png_file.relative_to(source_root)
        output_filename = f"{png_file.stem}{size_suffix}{png_file.suffix}"
        output_file = target_root / rel.parent / output_filename
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and not force:
            print(f"Skipping {rel} (already exists)")
            skipped += 1
            continue

        try:
            with Image.open(png_file) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                if stretch:
                    resized_img = resize_stretch(img, target_size)
                else:
                    resized_img = resize_crop(img, target_size)

                resized_img.save(output_file, 'PNG')
                print(f"Resized {rel} -> {output_file.relative_to(target_root.parent)}")
                resized += 1

        except Exception as e:
            print(f"Failed to resize {rel}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Resized:  {resized}")
    print(f"  Skipped:  {skipped}")
    print(f"  Failed:   {failed}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    default_source = project_root / "ASSETS" / "IMAGES" / "PNG" / "ORIGINAL_SIZE"

    parser = argparse.ArgumentParser(
        description="Resize PNG images to specified dimensions, mirroring directory structure.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: crop-to-fill at both 320x240 and 640x480, skip existing files
  python resize_png.py

  # Force overwrite all existing output files
  python resize_png.py --force

  # Single custom size
  python resize_png.py --width 480 --height 320

  # Single custom size, force overwrite
  python resize_png.py --width 480 --height 320 --force

  # Stretch to exact dimensions (distorts if aspect ratio differs)
  python resize_png.py --width 320 --height 240 --stretch

  # Custom source folder
  python resize_png.py --source ASSETS/IMAGES/PNG/ORIGINAL_SIZE/AVERY

  # Custom source and explicit target folder
  python resize_png.py --source ASSETS/IMAGES/PNG/ORIGINAL_SIZE/AVERY --target KSC_DATA/LOCATIONS/AVERY

  # Full example: single scene, specific size, force overwrite, custom paths
  python resize_png.py -w 320 -H 240 --force -s ASSETS/IMAGES/PNG/ORIGINAL_SIZE/AVERY -t KSC_DATA/LOCATIONS/AVERY
        """
    )

    parser.add_argument('-w', '--width', type=int, default=None,
        help='Target width in pixels (default: runs both 320x240 and 640x480)')
    parser.add_argument('-H', '--height', type=int, default=None,
        help='Target height in pixels (default: runs both 320x240 and 640x480)')
    parser.add_argument('-s', '--source', type=str, default=str(default_source),
        help=f'Source root directory (default: {default_source})')
    parser.add_argument('-t', '--target', type=str, default=None,
        help='Target root directory (default: auto-generated based on dimensions)')
    parser.add_argument('--stretch', action='store_true',
        help='Stretch image to exact dimensions (no aspect ratio)')
    parser.add_argument('--force', action='store_true',
        help='Overwrite existing output files')

    args = parser.parse_args()

    source_dir = Path(args.source)

    # If a custom size is given, run only that size; otherwise run both defaults
    if args.width is not None or args.height is not None:
        w = args.width or 320
        h = args.height or 240
        if not (1 <= w <= 10000):
            parser.error(f"Width must be between 1 and 10000 (got {w})")
        if not (1 <= h <= 10000):
            parser.error(f"Height must be between 1 and 10000 (got {h})")
        target_dir = Path(args.target) if args.target else \
            project_root / "ASSETS" / "IMAGES" / "PNG" / f"{w}x{h}"
        resize_images(source_dir, target_dir, target_size=(w, h), stretch=args.stretch, force=args.force)
    else:
        for (w, h) in [(320, 240), (640, 480)]:
            target_dir = Path(args.target) if args.target else \
                project_root / "ASSETS" / "IMAGES" / "PNG" / f"{w}x{h}"
            print(f"\n{'='*50}")
            print(f"Resizing to {w}x{h}")
            print(f"{'='*50}")
            resize_images(source_dir, target_dir, target_size=(w, h), stretch=args.stretch, force=args.force)
