import os
import json
import pandas as pd
import random
import shutil
import logging
from PIL import Image
from utils.config import (
    DFIRE_CLEAN_YOLO_PATH,
    DATASET_ROOT_PATH,
    DATASET_OUTPUT_PATH,
    DATASET_TRAIN_RATIO,
    DATASET_VAL_RATIO,
    DATASET_RANDOM_SEED,
    AIHUB_DATASET_SUBPATH,
    NASA_AMS_CLEAN_YOLO_PATH,
)

BASE = DATASET_ROOT_PATH
OUTPUT_DIR = DATASET_OUTPUT_PATH
BUILD_DIR = f"{OUTPUT_DIR}_build"
TEMP_ROOT = f"{OUTPUT_DIR}_temp"
OUTPUT_BACKUP_DIR = f"{OUTPUT_DIR}_backup_before_publish"

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


class DatasetProcessor:

    def __init__(self):
        self.all_image_paths = []
        self.stats = {
            "total_images": 0,
            "fire_images": 0,
            "smoke_images": 0,
            "train_count": 0,
            "val_count": 0,
            "test_count": 0,
            "symlink_failures": 0,
            "label_copy_failures": 0,
            "image_conversion_failures": 0,
            "invalid_bbox_skipped": 0,
            "empty_labels_created": 0,
            "nasa_ams_source_images": 0,
            "nasa_ams_converted_rgb_images": 0,
            "nasa_ams_skipped_images": 0,
            "nasa_ams_missing_labels": 0,
            "nasa_ams_invalid_images": 0,
            "nasa_ams_empty_labels": 0,
        }

    def prepare_build_workspace(self):
        print("Preparing isolated build workspace...")

        for path in [BUILD_DIR, TEMP_ROOT]:
            if os.path.exists(path):
                shutil.rmtree(path)

        os.makedirs(BUILD_DIR, exist_ok=True)
        os.makedirs(TEMP_ROOT, exist_ok=True)

    def publish_build(self):
        print("Publishing verified dataset build...")

        if not os.path.exists(BUILD_DIR):
            raise RuntimeError(
                f"BUILD_DIR does not exist, refusing to publish: {BUILD_DIR}"
            )

        side_backup = f"{OUTPUT_DIR}_publish_side_backup"

        if os.path.exists(side_backup):
            shutil.rmtree(side_backup)

        output_existed = os.path.exists(OUTPUT_DIR)
        if output_existed:
            try:
                os.rename(OUTPUT_DIR, side_backup)
            except OSError as e:
                raise RuntimeError(
                    f"Failed to move existing output dataset to side backup: {e}\n"
                    f"  OUTPUT_DIR:  {OUTPUT_DIR}\n"
                    f"  side_backup: {side_backup}\n"
                    "Existing dataset is untouched."
                ) from e

        try:
            os.rename(BUILD_DIR, OUTPUT_DIR)
        except OSError as e:
            if output_existed and os.path.exists(side_backup) and not os.path.exists(OUTPUT_DIR):
                try:
                    os.rename(side_backup, OUTPUT_DIR)
                    raise RuntimeError(
                        f"Failed to publish build: {e}\n"
                        "Previous output dataset has been restored from side backup."
                    ) from e
                except OSError as restore_error:
                    raise RuntimeError(
                        f"Failed to publish build: {e}\n"
                        f"CRITICAL: Failed to restore previous output dataset from side backup: {restore_error}\n"
                        f"  BUILD_DIR:   {BUILD_DIR}\n"
                        f"  side_backup: {side_backup}\n"
                        f"  OUTPUT_DIR:  {OUTPUT_DIR}\n"
                        "Manual recovery required."
                    ) from restore_error
            raise RuntimeError(
                f"Failed to publish build: {e}\n"
                f"  BUILD_DIR:  {BUILD_DIR}\n"
                f"  OUTPUT_DIR: {OUTPUT_DIR}"
            ) from e

        if os.path.exists(side_backup):
            shutil.rmtree(side_backup)

        if os.path.exists(OUTPUT_BACKUP_DIR):
            shutil.rmtree(OUTPUT_BACKUP_DIR)

        if os.path.exists(TEMP_ROOT):
            shutil.rmtree(TEMP_ROOT)

    def validate_input_datasets(self):
        print("Validating input datasets before touching output directory...")

        counts = {
            "FASDD": self._count_fasdd_inputs(),
            "FASDD_UAV": self._count_fasdd_uav_inputs(),
            "PyroNear": self._count_pyronear_inputs(),
            "AIHub": self._count_ai_hub_inputs(),
            "D-Fire clean_yolo": self._count_clean_yolo_inputs(
                DFIRE_CLEAN_YOLO_PATH,
                ["train", "test"],
                ALLOWED_IMAGE_EXTS,
            ),
            "NASA AMS clean_yolo_patches": self._count_clean_yolo_inputs(
                NASA_AMS_CLEAN_YOLO_PATH,
                ["train", "val", "test"],
                {".jpg", ".jpeg", ".png", ".tif", ".tiff"},
            ),
        }

        total = sum(counts.values())
        for dataset_name, count in counts.items():
            print(f"- {dataset_name}: {count} input images")

        if total == 0:
            checked = ", ".join(f"{name}={count}" for name, count in counts.items())
            raise RuntimeError(
                "No input images found. Refusing to delete existing output dataset. "
                f"Checked datasets: {checked}"
            )

        print(f"Input dataset validation passed: {total} input images found")

    def _count_fasdd_inputs(self):
        fasdd_path = f"{BASE}/FASDD"
        return self._count_split_file_inputs(
            fasdd_path,
            f"{fasdd_path}/annotations/YOLO",
            "labels",
            "images/",
        )

    def _count_fasdd_uav_inputs(self):
        fasdd_uav_path = f"{BASE}/FASDD_UAV"
        return self._count_split_file_inputs(
            fasdd_uav_path,
            f"{fasdd_uav_path}/annotations/YOLO_UAV",
            "labels",
            "./images/",
        )

    def _count_split_file_inputs(self, dataset_path, annotations_path, labels_dir, prefix):
        count = 0

        for split in ["train", "val", "test"]:
            split_file = f"{annotations_path}/{split}.txt"
            if not os.path.exists(split_file):
                continue

            try:
                with open(split_file, "r") as f:
                    for line in f:
                        img_path = line.strip()
                        if img_path.startswith(prefix):
                            img_path = img_path[len(prefix):]

                        src_img = f"{dataset_path}/images/{img_path}"
                        label_name = os.path.splitext(img_path)[0] + ".txt"
                        src_label = f"{annotations_path}/{labels_dir}/{label_name}"

                        if (
                            os.path.exists(src_img)
                            and os.path.exists(src_label)
                            and os.path.splitext(src_img)[1].lower() in ALLOWED_IMAGE_EXTS
                        ):
                            count += 1
            except IOError as e:
                print(f"Error reading split file {split_file}: {e}")

        return count

    def _count_pyronear_inputs(self):
        pyronear_path = f"{BASE}/PyroNear/data"

        try:
            files = sorted(
                f for f in os.listdir(pyronear_path)
                if f.startswith("train-") or f.startswith("val-")
            )
        except OSError as e:
            print(f"Error reading PyroNear directory {pyronear_path}: {e}")
            return 0

        count = 0
        for file in files:
            parquet_path = f"{pyronear_path}/{file}"
            try:
                df = pd.read_parquet(parquet_path, columns=["image", "objects"])
                for _, row in df.iterrows():
                    img_data = row.get("image")
                    objects = row.get("objects")
                    if isinstance(img_data, dict) and "bytes" in img_data and objects is not None:
                        count += 1
            except (IOError, ValueError, KeyError) as e:
                print(f"Error validating PyroNear file {file}: {e}")

        return count

    def _count_ai_hub_inputs(self):
        ai_hub_path = f"{BASE}/{AIHUB_DATASET_SUBPATH}"
        count = 0

        for split in ["Training", "Validation"]:
            img_dir = f"{ai_hub_path}/{split}/source-data"
            label_dir = f"{ai_hub_path}/{split}/labeling-data"

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                continue

            img_index = {}
            for root, dirs, files in os.walk(img_dir):
                dirs.sort()
                files.sort()
                for file in files:
                    if os.path.splitext(file)[1].lower() in ALLOWED_IMAGE_EXTS:
                        img_index[file] = os.path.join(root, file)

            for root, dirs, files in os.walk(label_dir):
                dirs.sort()
                files.sort()
                for file in files:
                    if not file.endswith(".json"):
                        continue

                    json_path = os.path.join(root, file)
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        for img_info in data.get("images", []):
                            img_path = img_index.get(img_info.get("file_name"))
                            if img_path and os.path.exists(img_path):
                                count += 1
                    except (IOError, ValueError, KeyError) as e:
                        print(f"Error validating AI Hub file {json_path}: {e}")

        return count

    def _count_clean_yolo_inputs(self, dataset_path, splits, image_exts):
        if not os.path.exists(dataset_path):
            return 0

        count = 0
        for split in splits:
            img_dir = os.path.join(dataset_path, split, "images")
            label_dir = os.path.join(dataset_path, split, "labels")

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                continue

            try:
                for file in sorted(os.listdir(img_dir)):
                    img_ext = os.path.splitext(file)[1].lower()
                    if img_ext not in image_exts:
                        continue

                    label_path = os.path.join(label_dir, os.path.splitext(file)[0] + ".txt")
                    if os.path.exists(label_path):
                        count += 1
            except OSError as e:
                print(f"Error reading clean YOLO split {img_dir}: {e}")

        return count

    def _count_label_classes(self, label_path):
        has_fire = False
        has_smoke = False

        try:
            with open(label_path, "r") as lf:
                for line in lf:
                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split()
                    if not parts:
                        continue

                    class_id = int(parts[0])
                    if class_id == 0:
                        has_fire = True
                    elif class_id == 1:
                        has_smoke = True

        except (IOError, ValueError) as e:
            print(f"Error reading label file {label_path}: {e}")

        if has_fire:
            self.stats["fire_images"] += 1
        if has_smoke:
            self.stats["smoke_images"] += 1

    def process_fasdd(self):
        print("Processing FASDD dataset...")
        fasdd_path = f"{BASE}/FASDD"

        for split in ["train", "val", "test"]:
            split_file = f"{fasdd_path}/annotations/YOLO/{split}.txt"
            if not os.path.exists(split_file):
                continue

            try:
                with open(split_file, "r") as f:
                    for line in f:
                        img_path = line.strip()
                        if img_path.startswith("images/"):
                            img_path = img_path[7:]

                        src_img = f"{fasdd_path}/images/{img_path}"
                        label_name = os.path.splitext(img_path)[0] + ".txt"
                        src_label = f"{fasdd_path}/annotations/YOLO/labels/{label_name}"

                        if os.path.exists(src_img) and os.path.exists(src_label):
                            if os.path.splitext(src_img)[1].lower() not in ALLOWED_IMAGE_EXTS:
                                continue
                            self.all_image_paths.append((src_img, src_label))
                            self._count_label_classes(src_label)
            except IOError as e:
                print(f"Error reading split file {split_file}: {e}")

    def process_fasdd_uav(self):
        print("Processing FASDD_UAV dataset...")
        fasdd_uav_path = f"{BASE}/FASDD_UAV"

        for split in ["train", "val", "test"]:
            split_file = f"{fasdd_uav_path}/annotations/YOLO_UAV/{split}.txt"
            if not os.path.exists(split_file):
                continue

            try:
                with open(split_file, "r") as f:
                    for line in f:
                        img_path = line.strip()
                        if img_path.startswith("./images/"):
                            img_path = img_path[9:]

                        src_img = f"{fasdd_uav_path}/images/{img_path}"
                        label_name = os.path.splitext(img_path)[0] + ".txt"
                        src_label = f"{fasdd_uav_path}/annotations/YOLO_UAV/labels/{label_name}"

                        if os.path.exists(src_img) and os.path.exists(src_label):
                            if os.path.splitext(src_img)[1].lower() not in ALLOWED_IMAGE_EXTS:
                                continue
                            self.all_image_paths.append((src_img, src_label))
                            self._count_label_classes(src_label)
            except IOError as e:
                print(f"Error reading split file {split_file}: {e}")

    def process_pyronear(self):
        print("Processing PyroNear dataset...")
        pyronear_path = f"{BASE}/PyroNear/data"

        try:
            train_files = sorted([f for f in os.listdir(pyronear_path) if f.startswith("train-")])
            val_files = sorted([f for f in os.listdir(pyronear_path) if f.startswith("val-")])
        except OSError as e:
            print(f"Error reading PyroNear directory {pyronear_path}: {e}")
            return

        temp_dir = f"{TEMP_ROOT}/pyronear_temp"
        os.makedirs(f"{temp_dir}/images", exist_ok=True)
        os.makedirs(f"{temp_dir}/labels", exist_ok=True)

        for files, split in [(train_files, "train"), (val_files, "val")]:
            for file in files:
                try:
                    df = pd.read_parquet(f"{pyronear_path}/{file}")
                    for idx, row in df.iterrows():
                        img_data = row.get("image")
                        objects = row.get("objects")
                        if img_data is None or objects is None:
                            continue

                        img_name = f"pyronear_{split}_{file}_{idx}.jpg"
                        img_path = f"{temp_dir}/images/{img_name}"
                        label_name = os.path.splitext(img_name)[0] + ".txt"
                        label_path = f"{temp_dir}/labels/{label_name}"

                        if isinstance(img_data, dict) and "bytes" in img_data:
                            try:
                                with open(img_path, "wb") as f:
                                    f.write(img_data["bytes"])

                                with Image.open(img_path) as img:
                                    img_width, img_height = img.size

                                    has_objects = False
                                    with open(label_path, "w") as f:
                                        if objects and "bbox" in objects:
                                            for bbox in objects["bbox"]:
                                                if len(bbox) < 4:
                                                    continue

                                                x, y, width, height = bbox
                                                cx = (x + width / 2) / img_width
                                                cy = (y + height / 2) / img_height
                                                w = width / img_width
                                                h = height / img_height

                                                if w <= 0 or h <= 0:
                                                    self.stats["invalid_bbox_skipped"] += 1
                                                    continue

                                                f.write(f"1 {cx} {cy} {w} {h}\n")
                                                has_objects = True

                                    self.all_image_paths.append((img_path, label_path))
                                    if has_objects:
                                        self.stats["smoke_images"] += 1

                            except (IOError, ValueError) as e:
                                print(f"Error processing image {img_path}: {e}")

                except (IOError, ValueError, KeyError) as e:
                    print(f"Error processing PyroNear file {file}: {e}")

    def process_ai_hub(self):
        print("Processing AI Hub dataset...")
        ai_hub_path = f"{BASE}/{AIHUB_DATASET_SUBPATH}"

        aihub_dir = f"{TEMP_ROOT}/aihub"
        os.makedirs(f"{aihub_dir}/images/train", exist_ok=True)
        os.makedirs(f"{aihub_dir}/labels/train", exist_ok=True)

        for split in ["Training", "Validation"]:
            img_dir = f"{ai_hub_path}/{split}/source-data"
            label_dir = f"{ai_hub_path}/{split}/labeling-data"

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                continue

            print(f"Building image index for {split}...")
            img_index = {}
            for r, dirs, files in os.walk(img_dir):
                dirs.sort()
                files.sort()
                for f in files:
                    img_index[f] = os.path.join(r, f)

            print(f"Found {len(img_index)} images in {split}")

            for root, dirs, files in os.walk(label_dir):
                dirs.sort()
                files.sort()

                for file in files:
                    if not file.endswith(".json"):
                        continue

                    json_path = os.path.join(root, file)

                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        if "images" not in data or "annotations" not in data:
                            continue

                        for img_info in data["images"]:
                            img_name = img_info["file_name"]
                            img_width = img_info["width"]
                            img_height = img_info["height"]
                            img_path = img_index.get(img_name)

                            if not img_path or not os.path.exists(img_path):
                                continue

                            annotations = [
                                ann for ann in data["annotations"]
                                if ann["image_id"] == img_info["id"]
                            ]

                            label_name = os.path.splitext(img_name)[0] + ".txt"
                            label_path = f"{aihub_dir}/labels/train/{label_name}"

                            has_fire = False
                            has_smoke = False

                            with open(label_path, "w") as label_file:
                                for ann in annotations:
                                    category_id = ann["category_id"]
                                    bbox = ann["bbox"]

                                    if len(bbox) < 4:
                                        continue

                                    if category_id == 3:
                                        class_id = 0
                                    elif category_id in [1, 2, 6]:
                                        class_id = 1
                                    else:
                                        continue

                                    x, y, width, height = bbox
                                    cx = (x + width / 2) / img_width
                                    cy = (y + height / 2) / img_height
                                    w = width / img_width
                                    h = height / img_height

                                    if w <= 0 or h <= 0:
                                        self.stats["invalid_bbox_skipped"] += 1
                                        continue

                                    label_file.write(f"{class_id} {cx} {cy} {w} {h}\n")

                                    if class_id == 0:
                                        has_fire = True
                                    elif class_id == 1:
                                        has_smoke = True

                            symlink_img_path = f"{aihub_dir}/images/train/{img_name}"
                            if not os.path.exists(symlink_img_path):
                                try:
                                    rel_path = os.path.relpath(img_path, os.path.dirname(symlink_img_path))
                                    os.symlink(rel_path, symlink_img_path)
                                except OSError as e:
                                    print(f"Error creating symlink {symlink_img_path}: {e}")
                                    continue

                            if os.path.splitext(symlink_img_path)[1].lower() not in ALLOWED_IMAGE_EXTS:
                                continue
                            self.all_image_paths.append((symlink_img_path, label_path))

                            if has_fire:
                                self.stats["fire_images"] += 1
                            if has_smoke:
                                self.stats["smoke_images"] += 1

                    except (IOError, ValueError, KeyError) as e:
                        print(f"Error processing AI Hub file {json_path}: {e}")

    def process_dfire(self):
        print("Processing D-Fire dataset...")

        dfire_path = DFIRE_CLEAN_YOLO_PATH
        if not os.path.exists(dfire_path):
            print(f"D-Fire path not found, skipping: {dfire_path}")
            return

        image_exts = ALLOWED_IMAGE_EXTS

        dfire_temp_dir = f"{TEMP_ROOT}/dfire_temp"
        if os.path.exists(dfire_temp_dir):
            shutil.rmtree(dfire_temp_dir)

        for split in ["train", "test"]:
            img_dir = os.path.join(dfire_path, split, "images")
            label_dir = os.path.join(dfire_path, split, "labels")

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                print(f"D-Fire split missing, skipping: {split}")
                continue

            converted_label_dir = f"{dfire_temp_dir}/labels/{split}"
            os.makedirs(converted_label_dir, exist_ok=True)

            for file in sorted(os.listdir(img_dir)):
                img_ext = os.path.splitext(file)[1].lower()
                if img_ext not in image_exts:
                    continue

                src_img = os.path.join(img_dir, file)
                src_label = os.path.join(label_dir, os.path.splitext(file)[0] + ".txt")

                if not os.path.exists(src_label):
                    continue

                converted_label = os.path.join(converted_label_dir, os.path.splitext(file)[0] + ".txt")

                has_fire = False
                has_smoke = False
                valid_lines = []

                try:
                    with open(src_label, "r") as lf:
                        for raw_line in lf:
                            raw_line = raw_line.strip()
                            if not raw_line:
                                continue

                            parts = raw_line.split()
                            if len(parts) < 5:
                                self.stats["invalid_bbox_skipped"] += 1
                                continue

                            try:
                                dfire_class_id = int(parts[0])
                                x, y, w, h = map(float, parts[1:5])
                            except ValueError:
                                self.stats["invalid_bbox_skipped"] += 1
                                continue

                            if w <= 0 or h <= 0:
                                self.stats["invalid_bbox_skipped"] += 1
                                continue

                            if dfire_class_id == 0:
                                class_id = 1
                                has_smoke = True
                            elif dfire_class_id == 1:
                                class_id = 0
                                has_fire = True
                            else:
                                self.stats["invalid_bbox_skipped"] += 1
                                continue

                            valid_lines.append(f"{class_id} {x} {y} {w} {h}\n")

                    with open(converted_label, "w") as out:
                        out.writelines(valid_lines)

                    self.all_image_paths.append((src_img, converted_label))

                    if has_fire:
                        self.stats["fire_images"] += 1
                    if has_smoke:
                        self.stats["smoke_images"] += 1

                except IOError as e:
                    print(f"Error processing D-Fire label file {src_label}: {e}")

    def process_nasa_ams(self):
        print("Processing NASA AMS dataset...")

        nasa_path = NASA_AMS_CLEAN_YOLO_PATH
        if not os.path.exists(nasa_path):
            print(f"NASA AMS path not found, skipping: {nasa_path}")
            return

        nasa_rgb_path = f"{TEMP_ROOT}/nasa_ams_rgb"
        if os.path.abspath(nasa_rgb_path) == os.path.abspath(nasa_path):
            raise ValueError(
                "NASA AMS RGB temp path must be different from NASA_AMS_CLEAN_YOLO_PATH"
            )

        image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

        if os.path.exists(nasa_rgb_path):
            shutil.rmtree(nasa_rgb_path)

        for split in ["train", "val", "test"]:
            img_dir = os.path.join(nasa_path, split, "images")
            label_dir = os.path.join(nasa_path, split, "labels")

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                print(f"NASA AMS split missing, skipping: {split}")
                continue

            rgb_img_dir = os.path.join(nasa_rgb_path, split, "images")
            rgb_label_dir = os.path.join(nasa_rgb_path, split, "labels")
            os.makedirs(rgb_img_dir, exist_ok=True)
            os.makedirs(rgb_label_dir, exist_ok=True)

            for file in sorted(os.listdir(img_dir)):
                img_ext = os.path.splitext(file)[1].lower()
                if img_ext not in image_exts:
                    continue

                self.stats["nasa_ams_source_images"] += 1

                src_img = os.path.join(img_dir, file)
                src_label = os.path.join(label_dir, os.path.splitext(file)[0] + ".txt")

                if not os.path.exists(src_label):
                    self.stats["nasa_ams_missing_labels"] += 1
                    self.stats["nasa_ams_skipped_images"] += 1
                    continue

                dst_img = os.path.join(rgb_img_dir, os.path.splitext(file)[0] + ".jpg")
                dst_label = os.path.join(rgb_label_dir, os.path.splitext(file)[0] + ".txt")

                try:
                    with Image.open(src_img) as img:
                        rgb_img = img.convert("RGB")
                        if rgb_img.mode != "RGB" or len(rgb_img.getbands()) != 3:
                            raise ValueError(f"Converted image is not RGB: {src_img}")
                        rgb_img.save(dst_img, "JPEG", quality=95)

                    with Image.open(dst_img) as verify_img:
                        if verify_img.mode != "RGB" or len(verify_img.getbands()) != 3:
                            raise ValueError(f"Saved image is not RGB: {dst_img}")

                    shutil.copy2(src_label, dst_label)
                except (IOError, OSError, ValueError) as e:
                    print(f"Error converting NASA AMS image {src_img}: {e}")
                    self.stats["nasa_ams_invalid_images"] += 1
                    self.stats["nasa_ams_skipped_images"] += 1
                    for partial_path in [dst_img, dst_label]:
                        if os.path.exists(partial_path):
                            os.remove(partial_path)
                    continue

                self.all_image_paths.append((dst_img, dst_label))
                self.stats["nasa_ams_converted_rgb_images"] += 1

                if os.path.getsize(dst_label) == 0:
                    self.stats["nasa_ams_empty_labels"] += 1

                has_fire = False
                try:
                    with open(dst_label, "r") as lf:
                        for line in lf:
                            line = line.strip()
                            if not line:
                                continue

                            parts = line.split()
                            if len(parts) < 5:
                                continue

                            class_id = int(parts[0])
                            if class_id == 0:
                                has_fire = True

                    if has_fire:
                        self.stats["fire_images"] += 1

                except (IOError, ValueError) as e:
                    print(f"Error reading NASA AMS label file {dst_label}: {e}")

    def split_and_create_files(self):
        print("Creating train/val/test split files...")

        if not self.all_image_paths:
            raise RuntimeError(
                "No input images found. Refusing to delete existing output dataset."
            )

        if DATASET_TRAIN_RATIO + DATASET_VAL_RATIO > 1.0:
            raise ValueError(
                f"Invalid dataset ratios: train={DATASET_TRAIN_RATIO}, "
                f"val={DATASET_VAL_RATIO}, sum > 1.0"
            )

        rng = random.Random(DATASET_RANDOM_SEED)
        rng.shuffle(self.all_image_paths)
        total = len(self.all_image_paths)

        train_end = int(total * DATASET_TRAIN_RATIO)
        val_end = int(total * (DATASET_TRAIN_RATIO + DATASET_VAL_RATIO))

        train_data = self.all_image_paths[:train_end]
        val_data = self.all_image_paths[train_end:val_end]
        test_data = self.all_image_paths[val_end:]

        if not train_data:
            raise RuntimeError("train split is empty. Refusing to publish invalid dataset.")

        if not val_data:
            raise RuntimeError("val split is empty. Refusing to publish invalid dataset.")

        self.stats["total_images"] = total
        self.stats["train_count"] = len(train_data)
        self.stats["val_count"] = len(val_data)
        self.stats["test_count"] = len(test_data)

        os.makedirs(f"{BUILD_DIR}/images/train", exist_ok=True)
        os.makedirs(f"{BUILD_DIR}/images/val", exist_ok=True)
        os.makedirs(f"{BUILD_DIR}/images/test", exist_ok=True)
        os.makedirs(f"{BUILD_DIR}/labels/train", exist_ok=True)
        os.makedirs(f"{BUILD_DIR}/labels/val", exist_ok=True)
        os.makedirs(f"{BUILD_DIR}/labels/test", exist_ok=True)

        self._create_unified_dataset("train", train_data)
        self._create_unified_dataset("val", val_data)
        self._create_unified_dataset("test", test_data)

    def _create_unified_dataset(self, split, data):
        txt_file = f"{BUILD_DIR}/{split}.txt"

        with open(txt_file, "w") as f:
            for idx, (src_img_path, src_label_path) in enumerate(data):
                img_basename = os.path.basename(src_img_path)
                img_name, img_ext = os.path.splitext(img_basename)

                unique_img_name = f"{split}_{idx:06d}_{img_name}.jpg"
                unique_label_name = f"{split}_{idx:06d}_{img_name}.txt"

                unified_img_path = f"{BUILD_DIR}/images/{split}/{unique_img_name}"
                unified_label_path = f"{BUILD_DIR}/labels/{split}/{unique_label_name}"
                final_img_path = f"{OUTPUT_DIR}/images/{split}/{unique_img_name}"

                try:
                    with Image.open(src_img_path) as src_img:
                        rgb_img = src_img.convert("RGB")
                        if rgb_img.mode != "RGB" or len(rgb_img.getbands()) != 3:
                            raise ValueError(f"Converted image is not RGB: {src_img_path}")
                        rgb_img.save(unified_img_path, "JPEG", quality=95)
                except (IOError, OSError, ValueError) as e:
                    print(f"Error converting image {src_img_path}: {e}")
                    self.stats["image_conversion_failures"] += 1
                    if os.path.exists(unified_img_path):
                        os.remove(unified_img_path)
                    continue

                try:
                    with open(src_label_path, "r") as src_f:
                        valid_lines = []
                        for line in src_f:
                            line = line.strip()
                            if line and self._validate_yolo_line(line, unified_img_path, unified_label_path):
                                valid_lines.append(line + "\n")

                    with open(unified_label_path, "w") as dst_f:
                        dst_f.writelines(valid_lines)

                    if not valid_lines:
                        self.stats["empty_labels_created"] += 1

                except (IOError, OSError) as e:
                    print(f"Error copying label {src_label_path}: {e}")
                    self.stats["label_copy_failures"] += 1
                    if os.path.exists(unified_img_path):
                        os.remove(unified_img_path)
                    continue

                f.write(f"{final_img_path}\n")

    def _validate_yolo_line(self, line, img_path, label_path):
        try:
            parts = line.split()
            if len(parts) < 5:
                self.stats["invalid_bbox_skipped"] += 1
                logger.warning("Skipping invalid YOLO label line in %s: %s", label_path, line)
                return False

            class_id = int(parts[0])
            x = float(parts[1])
            y = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])

            if class_id not in [0, 1]:
                self.stats["invalid_bbox_skipped"] += 1
                logger.warning("Skipping label with invalid class in %s: %s", label_path, line)
                return False

            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 <= width <= 1 and 0 <= height <= 1):
                self.stats["invalid_bbox_skipped"] += 1
                logger.warning("Skipping label with out-of-range bbox in %s: %s", label_path, line)
                return False

            if width <= 0 or height <= 0:
                self.stats["invalid_bbox_skipped"] += 1
                logger.warning("Skipping label with non-positive bbox in %s: %s", label_path, line)
                return False

            return True
        except (ValueError, IndexError):
            self.stats["invalid_bbox_skipped"] += 1
            logger.warning("Skipping unparsable YOLO label line in %s: %s", label_path, line)
            return False

    def _verify_unified_dataset(self):
        print("\nVerifying unified dataset integrity...")

        errors = []
        allowed_top_level = {
            "images",
            "labels",
            "train.txt",
            "val.txt",
            "test.txt",
            "data.yaml",
        }
        forbidden_top_level = {
            "aihub",
            "pyronear_temp",
            "dfire_temp",
            "nasa_ams_rgb",
        }

        if os.path.exists(BUILD_DIR):
            top_level_entries = set(os.listdir(BUILD_DIR))
            unexpected_entries = top_level_entries - allowed_top_level
            for entry in sorted(unexpected_entries):
                if entry in forbidden_top_level or entry.endswith("_build") or entry.endswith("_temp"):
                    errors.append(f"Forbidden temp/build entry in final dataset build: {entry}")
                else:
                    errors.append(f"Unexpected entry in final dataset build: {entry}")
        else:
            errors.append(f"Missing build directory: {BUILD_DIR}")

        data_yaml_path = f"{BUILD_DIR}/data.yaml"
        if not os.path.exists(data_yaml_path):
            errors.append("Missing data.yaml file")

        for split in ["train", "val", "test"]:
            txt_file = f"{BUILD_DIR}/{split}.txt"

            if not os.path.exists(txt_file):
                errors.append(f"Missing {split}.txt file")
                continue

            with open(txt_file, "r") as f:
                image_paths = [line.strip() for line in f if line.strip()]

            for img_path in image_paths:
                actual_img_path = self._build_path_for_final_path(img_path)

                if not os.path.exists(actual_img_path):
                    errors.append(f"Image does not exist: {img_path}")
                    continue

                if os.path.splitext(actual_img_path)[1].lower() not in ALLOWED_IMAGE_EXTS:
                    errors.append(f"Unsupported image format in unified dataset: {img_path}")
                    continue

                try:
                    with Image.open(actual_img_path) as img:
                        if img.mode != "RGB" or len(img.getbands()) != 3:
                            errors.append(f"Non-RGB image in unified dataset: {img_path}")
                            continue
                except (IOError, OSError, ValueError) as e:
                    errors.append(f"Invalid image in unified dataset: {img_path} ({e})")
                    continue

                img_name, _ = os.path.splitext(os.path.basename(actual_img_path))
                label_path = f"{BUILD_DIR}/labels/{split}/{img_name}.txt"

                if not os.path.exists(label_path):
                    errors.append(f"Missing label for image: {img_path} (expected: {label_path})")

        for split in ["train", "val", "test"]:
            labels_dir = f"{BUILD_DIR}/labels/{split}"
            images_dir = f"{BUILD_DIR}/images/{split}"

            if os.path.exists(labels_dir) and os.path.exists(images_dir):
                label_files = set(os.listdir(labels_dir))
                image_files = set(os.listdir(images_dir))

                for image_file in image_files:
                    image_ext = os.path.splitext(image_file)[1].lower()
                    if image_ext in {".tif", ".tiff"}:
                        errors.append(f"TIFF image found in unified dataset: {images_dir}/{image_file}")

                expected_labels = {os.path.splitext(img)[0] + ".txt" for img in image_files}

                orphaned_labels = label_files - expected_labels
                if orphaned_labels:
                    for orphan in orphaned_labels:
                        errors.append(f"Orphaned label without image: {labels_dir}/{orphan}")

        if errors:
            error_msg = "Dataset verification failed:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            raise RuntimeError(error_msg)

        print("✓ Dataset verification passed")

    def _build_path_for_final_path(self, final_path):
        final_abs = os.path.abspath(final_path)
        output_abs = os.path.abspath(OUTPUT_DIR)

        if final_abs == output_abs or final_abs.startswith(output_abs + os.sep):
            rel_path = os.path.relpath(final_abs, output_abs)
            return os.path.join(BUILD_DIR, rel_path)

        return final_path

    def create_data_yaml(self):
        data_yaml = (
            f"path: {OUTPUT_DIR}\n"
            f"train: train.txt\n"
            f"val: val.txt\n"
            f"test: test.txt\n\n"
            f"nc: 2\n"
            f"names: ['fire', 'smoke']\n"
        )

        with open(f"{BUILD_DIR}/data.yaml", "w") as f:
            f.write(data_yaml)

    def print_statistics(self):
        train_ratio = int(DATASET_TRAIN_RATIO * 100)
        val_ratio = int(DATASET_VAL_RATIO * 100)
        test_ratio = 100 - train_ratio - val_ratio

        print("\n=== Dataset Processing Complete ===")
        print(f"Total images: {self.stats['total_images']}")
        print(f"Fire images: {self.stats['fire_images']}")
        print(f"Smoke images: {self.stats['smoke_images']}")
        print(f"\nDataset split ({train_ratio}/{val_ratio}/{test_ratio}):")
        print(f"Train: {self.stats['train_count']}")
        print(f"Validation: {self.stats['val_count']}")
        print(f"Test: {self.stats['test_count']}")
        print("\nFailures:")
        print(f"Symlink creation failures: {self.stats['symlink_failures']}")
        print(f"Label copy failures: {self.stats['label_copy_failures']}")
        print(f"Image conversion failures: {self.stats['image_conversion_failures']}")
        print(f"Invalid bboxes skipped: {self.stats['invalid_bbox_skipped']}")
        print(f"Empty label files created (negative samples): {self.stats['empty_labels_created']}")
        print("\nNASA AMS:")
        print(f"Source images: {self.stats['nasa_ams_source_images']}")
        print(f"Converted RGB images: {self.stats['nasa_ams_converted_rgb_images']}")
        print(f"Skipped images: {self.stats['nasa_ams_skipped_images']}")
        print(f"Missing labels: {self.stats['nasa_ams_missing_labels']}")
        print(f"Invalid images: {self.stats['nasa_ams_invalid_images']}")
        print(f"Empty labels preserved: {self.stats['nasa_ams_empty_labels']}")


def main():
    processor = DatasetProcessor()

    processor.validate_input_datasets()
    processor.prepare_build_workspace()

    processor.process_fasdd()
    processor.process_fasdd_uav()
    processor.process_pyronear()
    processor.process_ai_hub()
    processor.process_dfire()
    processor.process_nasa_ams()

    processor.split_and_create_files()
    processor.create_data_yaml()
    processor._verify_unified_dataset()
    processor.publish_build()
    processor.print_statistics()

    print("\nGenerated files:")
    print(f"- {OUTPUT_DIR}/data.yaml")
    print(f"- {OUTPUT_DIR}/train.txt")
    print(f"- {OUTPUT_DIR}/val.txt")
    print(f"- {OUTPUT_DIR}/test.txt")


if __name__ == "__main__":
    main()
