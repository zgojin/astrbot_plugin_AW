import json
import os
import time
from typing import List, Set  # Dict未使用，故去除，不影响整体效果

from PIL import Image, ImageDraw, ImageOps

# 最大保留天数
MAX_GALLERY_AGE = 7  # 保留7天内的图鉴


def get_all_wife_images(img_dir: str) -> List[str]:
    """获取所有二次元老婆图片文件名"""
    if os.path.exists(img_dir):
        image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        return [f for f in os.listdir(img_dir) if f.lower().endswith(image_extensions)]
    return []


def get_unlocked_wives(group_id: str, config_dir: str) -> Set[str]:
    """获取指定群组中所有已解锁的老婆图片名"""
    unlocked = set()
    config_file = os.path.join(config_dir, f"{group_id}.json")

    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                for user_data in config.values():
                    if isinstance(user_data, dict) and "unlocked" in user_data:
                        unlocked.update(
                            [item["wife_name"] for item in user_data["unlocked"]]
                        )
            except json.JSONDecodeError:
                print(f"解析配置文件 {config_file} 时出错")

    return unlocked


def create_full_color_gallery(
    img_dir: str, output_path: str, thumbnail_size: tuple = (80, 80)
) -> None:
    """创建全彩色的老婆图鉴（通用版）"""
    all_wives = get_all_wife_images(img_dir)
    if not all_wives:
        raise ValueError(f"本地图片目录 {img_dir} 中未找到任何图片文件")

    # 创建拼贴图
    images_per_row = 10
    total = len(all_wives)
    rows = (total + images_per_row - 1) // images_per_row
    cols = min(total, images_per_row)

    collage_width = cols * thumbnail_size[0]
    collage_height = rows * thumbnail_size[1]
    collage = Image.new("RGB", (collage_width, collage_height), (245, 245, 245))
    draw = ImageDraw.Draw(collage)

    # 处理所有图片为彩色
    for i, wife in enumerate(all_wives):
        row = i // images_per_row
        col = i % images_per_row
        x = col * thumbnail_size[0]
        y = row * thumbnail_size[1]

        img_path = os.path.join(img_dir, wife)
        try:
            with Image.open(img_path) as img:
                # 处理透明背景
                if img.mode in ("RGBA", "LA"):
                    background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode == "P":
                    img = img.convert("RGB")

                # 缩放图片
                img.thumbnail(thumbnail_size)

                # 创建固定尺寸的缩略图
                thumb = Image.new("RGB", thumbnail_size, (255, 255, 255))
                offset = (
                    (thumbnail_size[0] - img.width) // 2,
                    (thumbnail_size[1] - img.height) // 2,
                )
                thumb.paste(img, offset)

                # 保持彩色
                collage.paste(thumb, (x, y))
        except:
            # 出错时绘制默认彩色方块
            draw.rectangle(
                [(x, y), (x + thumbnail_size[0], y + thumbnail_size[1])],
                fill=(220, 220, 220),
            )

        # 绘制边框
        draw.rectangle(
            [(x, y), (x + thumbnail_size[0] - 1, y + thumbnail_size[1] - 1)],
            outline=(200, 200, 200),
            width=1,
        )

    # 保存彩色大图
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    collage.save(output_path)


def update_gallery_with_black_and_white(
    group_id: str,
    img_dir: str,
    config_dir: str,
    color_gallery_path: str,
    output_path: str,
    thumbnail_size: tuple = (80, 80),
) -> None:
    """在通用彩色大图上渲染未解锁的黑白图片"""
    all_wives = sorted(get_all_wife_images(img_dir))  # 确保顺序固定
    if not all_wives:
        raise ValueError(f"本地图片目录 {img_dir} 中未找到任何图片文件")

    unlocked_wives = get_unlocked_wives(group_id, config_dir)

    # 打开通用彩色大图
    with Image.open(color_gallery_path) as gallery:
        draw = ImageDraw.Draw(gallery)

        # 在彩色图上渲染未解锁的黑白图片
        for i, wife in enumerate(all_wives):
            if wife not in unlocked_wives:
                # 计算在大图中的行列位置
                row = i // 10  # 每行10个图片
                col = i % 10

                # 计算在画布上的像素坐标
                x = col * thumbnail_size[0]
                y = row * thumbnail_size[1]

                # 提取对应位置的彩色图块
                block = gallery.crop(
                    (x, y, x + thumbnail_size[0], y + thumbnail_size[1])
                )

                # 将图块转换为灰度图
                block = ImageOps.grayscale(block)

                # 将灰度图块替换回大图
                gallery.paste(block, (x, y))

        # 添加标题（包含群ID）
        title = f"群{group_id}老婆图鉴 - 已解锁: {len(unlocked_wives)}/{len(all_wives)}"
        title_font_size = 16
        title_height = title_font_size + 10

        # 创建一个更高的新画布，包含标题区域
        new_collage = Image.new(
            "RGB", (gallery.width, gallery.height + title_height), (245, 245, 245)
        )
        new_draw = ImageDraw.Draw(new_collage)

        # 粘贴原拼贴图到新画布
        new_collage.paste(gallery, (0, title_height))

        # 绘制标题
        new_draw.text((10, 5), title, fill=(0, 0, 0))

        # 保存最终图鉴
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        new_collage.save(output_path)


# 清理旧图鉴文件
def cleanup_old_galleries(
    gallery_dir: str, max_age_days: int = MAX_GALLERY_AGE
) -> None:
    """清理超过指定天数的图鉴文件"""
    if not os.path.exists(gallery_dir):
        return

    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60

    for filename in os.listdir(gallery_dir):
        file_path = os.path.join(gallery_dir, filename)
        # 只处理图片文件
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            try:
                # 获取文件修改时间
                mtime = os.path.getmtime(file_path)
                # 如果文件修改时间超过最大保留时间，则删除
                if current_time - mtime > max_age_seconds:
                    os.remove(file_path)
                    print(f"删除过期图鉴文件: {filename}")
            except Exception as e:
                print(f"清理文件时出错: {filename}, 错误: {e}")


def create_or_update_wife_gallery(
    group_id: str,
    img_dir: str,
    config_dir: str,
    color_gallery_dir: str,
    output_path: str,
    thumbnail_size: tuple = (80, 80),
) -> str:
    """
    检查并生成老婆图鉴：
    1. 使用通用彩色大图（所有群共用）
    2. 在通用彩色大图上渲染未解锁的黑白图片
    3. 清理旧的图鉴文件
    """
    # 先清理旧的图鉴文件
    gallery_dir = os.path.dirname(output_path)
    cleanup_old_galleries(gallery_dir)

    # 通用彩色大图路径
    common_color_gallery_path = os.path.join(
        color_gallery_dir, "common_color_gallery.png"
    )

    # 检查通用彩色大图是否存在，不存在则生成
    if not os.path.exists(common_color_gallery_path):
        create_full_color_gallery(
            img_dir=img_dir,
            output_path=common_color_gallery_path,
            thumbnail_size=thumbnail_size,
        )

    # 在通用彩色大图上渲染未解锁的黑白图片
    update_gallery_with_black_and_white(
        group_id=group_id,
        img_dir=img_dir,
        config_dir=config_dir,
        color_gallery_path=common_color_gallery_path,
        output_path=output_path,
        thumbnail_size=thumbnail_size,
    )

    return output_path


def create_personal_wife_gallery(
    unlocked_wives: List[str],
    img_dir: str,
    output_path: str,
    thumbnail_size: tuple = (80, 80),
) -> str:
    """创建个人老婆图鉴"""
    if not unlocked_wives:
        raise ValueError("未找到已解锁的老婆图片")

    # 创建拼贴图
    images_per_row = 10
    total = len(unlocked_wives)
    rows = (total + images_per_row - 1) // images_per_row
    cols = min(total, images_per_row)

    collage_width = cols * thumbnail_size[0]
    collage_height = rows * thumbnail_size[1]
    collage = Image.new("RGB", (collage_width, collage_height), (245, 245, 245))
    draw = ImageDraw.Draw(collage)

    for i, wife in enumerate(unlocked_wives):
        row = i // images_per_row
        col = i % images_per_row
        x = col * thumbnail_size[0]
        y = row * thumbnail_size[1]

        img_path = os.path.join(img_dir, wife)
        try:
            with Image.open(img_path) as img:
                # 处理透明背景
                if img.mode in ("RGBA", "LA"):
                    background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode == "P":
                    img = img.convert("RGB")

                # 缩放图片
                img.thumbnail(thumbnail_size)

                # 创建固定尺寸的缩略图
                thumb = Image.new("RGB", thumbnail_size, (255, 255, 255))
                offset = (
                    (thumbnail_size[0] - img.width) // 2,
                    (thumbnail_size[1] - img.height) // 2,
                )
                thumb.paste(img, offset)

                # 保持彩色
                collage.paste(thumb, (x, y))
        except:
            # 出错时绘制默认彩色方块
            draw.rectangle(
                [(x, y), (x + thumbnail_size[0], y + thumbnail_size[1])],
                fill=(220, 220, 220),
            )

        # 绘制边框
        draw.rectangle(
            [(x, y), (x + thumbnail_size[0] - 1, y + thumbnail_size[1] - 1)],
            outline=(200, 200, 200),
            width=1,
        )

    # 保存个人图鉴
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    collage.save(output_path)

    return output_path
