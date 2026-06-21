"""트레이/실행파일용 .ico 생성. (한 번만 실행)"""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "clipai.ico")


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle([s * 0.06, s * 0.06, s * 0.94, s * 0.94],
                        radius=int(s * 0.22), fill=(28, 28, 32, 255),
                        outline=(108, 140, 255, 255), width=max(1, int(s * 0.03)))
    # 클립 머리
    d.rounded_rectangle([s * 0.38, s * 0.12, s * 0.62, s * 0.24],
                        radius=int(s * 0.04), fill=(108, 140, 255, 255))
    # AI 텍스트 느낌의 막대 두 개
    d.rounded_rectangle([s * 0.30, s * 0.40, s * 0.40, s * 0.74], radius=int(s*0.02), fill=(236, 236, 240, 255))
    d.rounded_rectangle([s * 0.58, s * 0.40, s * 0.68, s * 0.74], radius=int(s*0.02), fill=(236, 236, 240, 255))
    d.rounded_rectangle([s * 0.30, s * 0.52, s * 0.68, s * 0.60], radius=int(s*0.02), fill=(236, 236, 240, 255))
    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(s) for s in sizes]
    imgs[0].save(os.path.abspath(OUT), format="ICO",
                 sizes=[(s, s) for s in sizes], append_images=imgs[1:])
    print("wrote", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
