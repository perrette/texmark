import os
import hashlib
import requests
from urllib.parse import urlparse
import panflute as pf

def is_remote_url(url):
    return url.startswith("http://") or url.startswith("https://")

def safe_filename_from_url(url):
    # Create a unique but readable filename
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path)
    if not basename:
        basename = "image"
    ext = os.path.splitext(basename)[-1] or ".png"
    hash_digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return os.path.join(hash_digest, basename)

def download_image(url, output_path):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        pf.debug(f"Failed to download {url}: {e}")
        return False

def action(elem, doc):
    BUILD_DIR = doc.get_metadata('build_dir', 'build')
    IMAGE_DIR = os.path.join(BUILD_DIR, os.path.basename(doc.get_metadata('images', 'images')))

    if isinstance(elem, pf.Image) and is_remote_url(elem.url):
        filename = safe_filename_from_url(elem.url)
        local_path = os.path.join(IMAGE_DIR, filename)

        # Ensure image directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # Download only if not already present
        if not os.path.exists(local_path):
            success = download_image(elem.url, local_path)
            if not success:
                return elem  # Leave original URL if failed

        # Replace remote URL with local path
        elem.url = os.path.relpath(local_path, BUILD_DIR)
        return elem

def main(doc=None):
    return pf.run_filter(action, doc=doc)

if __name__ == "__main__":
    main()
