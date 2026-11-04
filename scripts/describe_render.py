"""Describe PNG images using an explicitly configured OpenAI-compatible vision model."""

import argparse
import base64
import io
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffxiv_furniture.config import model_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("question")
    parser.add_argument("extra_images", nargs="*", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    try:
        url, model = model_settings(args.endpoint, args.model)
    except ValueError as error:
        parser.error(str(error))
    from PIL import Image

    content = [{"type": "text", "text": args.question}]
    for path in [args.image, *args.extra_images]:
        with Image.open(path) as source:
            image = source.convert("RGB")
        image.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        content.append(
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}}
        )
    body = dict(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Describe visible 3D-rendered objects, positions, colours, gaps and overlaps literally. Do not guess unseen details.",
            },
            {"role": "user", "content": content},
        ],
        max_tokens=900,
        temperature=0.2,
        chat_template_kwargs={"enable_thinking": False},
    )
    request = urllib.request.Request(
        url + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        result = json.load(response)
    print(result["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
