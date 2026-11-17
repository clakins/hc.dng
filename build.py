"""Builds the portfolio site from your Obsidian notes + photo folders.
Run:  python build.py        (one-time setup: pip install pillow; ffmpeg is optional, see below)
"""
import json, re, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageOps

SITE_DIR = Path(__file__).parent  # the folder this script is in

# ---- YOUR TWO FOLDERS ----
NOTES_DIR  = Path(r"C:\Users\photo\Documents\Henry's Sync Vault\Portfolio")  # one .md note per project
PHOTOS_DIR = SITE_DIR  # one folder per project (named like its note), next to this script
# ------------------------------
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".m4v"}  # .mov often won't play outside Safari - export as .mp4


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def resize(src, dst, size):
    """Save a JPG with its long edge at `size` px (skips if it already exists)."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = ImageOps.exif_transpose(Image.open(src))
    im.thumbnail((size, size))
    im.convert("RGB").save(dst, quality=85)


def grab_frame(video, dst):
    """Saves a still from a video as the poster/thumbnail. Needs ffmpeg installed; skipped without it."""
    if dst.exists() or not shutil.which("ffmpeg"):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale='min(2000,iw)':-2", str(dst)])


def embed_url(url):
    """Turns a YouTube or Vimeo link into its embeddable address."""
    m = re.search(r"(?:youtu\.be/|youtube\.com/watch\?v=)([\w-]+)", url)
    if m:
        return "https://www.youtube.com/embed/" + m.group(1)
    m = re.search(r"vimeo\.com/(\d+)", url)
    return "https://player.vimeo.com/video/" + m.group(1) if m else ""


def read_note(path):
    """Returns (frontmatter dict, description text). Handles `type: a, b` and Obsidian's list format."""
    text = path.read_text(encoding="utf-8")
    meta, body, key = {}, text, None
    m = re.match(r"---\s*\n(.*?)\n---\s*\n?(.*)", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if line.strip().startswith("- ") and key:
                meta[key] = (meta[key] + "," if meta[key] else "") + line.strip()[2:]
            elif ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                meta[key] = val.strip().strip("[]")
    body = re.sub(r"!\[\[.*?\]\]|!\[.*?\]\(.*?\)", "", body)  # drop embedded images
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return meta, body


projects = []
for note in sorted(NOTES_DIR.glob("*.md")):
    meta, body = read_note(note)
    if meta.get("publish", "true").lower() == "false":
        continue
    slug = slugify(note.stem)
    src = PHOTOS_DIR / meta.get("folder", note.stem)
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in PHOTO_EXTS | VIDEO_EXTS) if src.is_dir() else []
    if not src.is_dir():
        print(f"  ! folder not found for '{note.stem}': {src}")
    elif not files:
        print(f"  ! folder is empty (no jpg/png/webp/mp4/webm): {src}")

    photos = []
    for f in files:
        jpg = f.stem + ".jpg"
        out = SITE_DIR / "photos" / slug
        is_video = f.suffix.lower() in VIDEO_EXTS
        if is_video:
            grab_frame(f, out / "web" / jpg)           # poster frame (needs ffmpeg)
        source = out / "web" / jpg if is_video else f
        if source.exists():
            resize(source, out / "web" / jpg, 2000)    # shown on the project page
            resize(source, out / "thumb" / jpg, 600)   # shown on the homepage
            resize(source, NOTES_DIR / "_thumbs" / slug / jpg, 400)  # small copy for Obsidian
        full = out / "full" / f.name                   # original, opened on click
        if not full.exists():
            full.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, full)
            if full.stat().st_size > 90_000_000:
                print(f"  ! {f.name} is over 90MB - GitHub rejects files over 100MB")
        photos.append({"img": jpg if source.exists() else "", "full": f.name, "video": is_video})

    types = [t.strip().lower() for t in meta.get("type", "").split(",") if t.strip()]
    thumb = meta.get("thumbnail", "")  # optional: filename of the homepage thumbnail
    if "video" in types and not thumb:  # video projects: a photo named thumbnail.jpg (etc.) is picked up automatically
        thumb = next((p["full"] for p in photos if Path(p["full"]).stem.lower() == "thumbnail"), "")
    cover = next((p for p in photos if p["full"] == thumb and p["img"]), None) or next((p for p in photos if p["img"]), None)
    if "video" in types and cover and not cover["video"] and cover["full"] == thumb:
        photos.remove(cover)  # video projects: the thumbnail photo is only used on the homepage, not the project page
    else:
        photos.sort(key=lambda p: p["full"] != thumb)  # otherwise the thumbnail photo goes first; the rest keep order

    try:  # location: "36.27, -121.81" (latitude, longitude)
        lat, lng = [float(x) for x in meta.get("location", "").split(",")]
    except ValueError:
        lat = lng = None

    projects.append({
        "slug": slug,
        "title": note.stem,  # the note's filename is always the project title
        "date": meta.get("date", ""),
        "types": types,
        "cover": cover["img"] if cover else "",
        "lat": lat,
        "lng": lng,
        "description": body,
        "embeds": [u for u in (embed_url(x.strip()) for x in meta.get("embed", "").split(",")) if u],
        "photos": photos,
    })
    print(f"  {note.stem}: {len(photos)} files")

projects.sort(key=lambda p: p["date"], reverse=True)  # newest first
(SITE_DIR / "projects.js").write_text("const PROJECTS = " + json.dumps(projects, indent=1) + ";\n", encoding="utf-8")
print(f"Done - {len(projects)} projects.")
