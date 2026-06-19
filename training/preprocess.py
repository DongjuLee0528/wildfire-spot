import os
import json
import pandas as pd
import random
import shutil
import logging
from PIL import Image
from utils.config import (DATASET_ROOT_PATH, DATASET_OUTPUT_PATH, DATASET_TRAIN_RATIO,
                         DATASET_VAL_RATIO, DATASET_RANDOM_SEED, AIHUB_DATASET_SUBPATH)

BASE = DATASET_ROOT_PATH
OUTPUT_DIR = DATASET_OUTPUT_PATH

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

class DatasetProcessor:

    def __init__(self):
        self.all_image_paths = []
        self.stats = {
            'total_images': 0,
            'fire_images': 0,
            'smoke_images': 0,
            'train_count': 0,
            'val_count': 0,
            'test_count': 0,
            'symlink_failures': 0,
            'label_copy_failures': 0,
            'invalid_bbox_skipped': 0
        }

    def process_fasdd(self):
        print("Processing FASDD dataset...")
        fasdd_path = f"{BASE}/FASDD"

        for split in ['train', 'val', 'test']:
            split_file = f"{fasdd_path}/annotations/YOLO/{split}.txt"
            if not os.path.exists(split_file):
                continue

            try:
                with open(split_file, 'r') as f:
                    for line in f:
                        img_path = line.strip()
                        if img_path.startswith('images/'):
                            img_path = img_path[7:]

                        src_img = f"{fasdd_path}/images/{img_path}"
                        label_name = os.path.splitext(img_path)[0] + '.txt'
                        src_label = f"{fasdd_path}/annotations/YOLO/labels/{label_name}"

                        if os.path.exists(src_img) and os.path.exists(src_label):
                            self.all_image_paths.append((src_img, src_label))

                            try:
                                with open(src_label, 'r') as lf:
                                    content = lf.read().strip()
                                    if content:
                                        lines = content.split('\n')
                                        for label_line in lines:
                                            if label_line.strip():
                                                label_parts = label_line.split()
                                                if not label_parts:
                                                    continue
                                                class_id = int(label_parts[0])
                                                if class_id == 0:
                                                    self.stats['fire_images'] += 1
                                                elif class_id == 1:
                                                    self.stats['smoke_images'] += 1
                            except (IOError, ValueError) as e:
                                print(f"Error reading label file {src_label}: {e}")
            except IOError as e:
                print(f"Error reading split file {split_file}: {e}")

    def process_fasdd_uav(self):
        print("Processing FASDD_UAV dataset...")
        fasdd_uav_path = f"{BASE}/FASDD_UAV"

        for split in ['train', 'val', 'test']:
            split_file = f"{fasdd_uav_path}/annotations/YOLO_UAV/{split}.txt"
            if not os.path.exists(split_file):
                continue

            try:
                with open(split_file, 'r') as f:
                    for line in f:
                        img_path = line.strip()
                        if img_path.startswith('./images/'):
                            img_path = img_path[9:]

                        src_img = f"{fasdd_uav_path}/images/{img_path}"
                        label_name = os.path.splitext(img_path)[0] + '.txt'
                        src_label = f"{fasdd_uav_path}/annotations/YOLO_UAV/labels/{label_name}"

                        if os.path.exists(src_img) and os.path.exists(src_label):
                            self.all_image_paths.append((src_img, src_label))

                            try:
                                with open(src_label, 'r') as lf:
                                    content = lf.read().strip()
                                    if content:
                                        lines = content.split('\n')
                                        for label_line in lines:
                                            if label_line.strip():
                                                label_parts = label_line.split()
                                                if not label_parts:
                                                    continue
                                                class_id = int(label_parts[0])
                                                if class_id == 0:
                                                    self.stats['fire_images'] += 1
                                                elif class_id == 1:
                                                    self.stats['smoke_images'] += 1
                            except (IOError, ValueError) as e:
                                print(f"Error reading label file {src_label}: {e}")
            except IOError as e:
                print(f"Error reading split file {split_file}: {e}")

    def process_pyronear(self):
        print("Processing PyroNear dataset...")
        pyronear_path = f"{BASE}/PyroNear/data"

        try:
            train_files = sorted([f for f in os.listdir(pyronear_path) if f.startswith('train-')])
            val_files = sorted([f for f in os.listdir(pyronear_path) if f.startswith('val-')])
        except OSError as e:
            print(f"Error reading PyroNear directory {pyronear_path}: {e}")
            return

        temp_dir = f"{OUTPUT_DIR}/pyronear_temp"
        os.makedirs(f"{temp_dir}/images", exist_ok=True)
        os.makedirs(f"{temp_dir}/labels", exist_ok=True)

        for files, split in [(train_files, 'train'), (val_files, 'val')]:
            for file in files:
                try:
                    df = pd.read_parquet(f"{pyronear_path}/{file}")
                    for idx, row in df.iterrows():
                        img_data = row.get('image')
                        objects = row.get('objects')
                        if img_data is not None and objects is not None:

                            img_name = f"pyronear_{split}_{file}_{idx}.jpg"
                            img_path = f"{temp_dir}/images/{img_name}"
                            label_name = os.path.splitext(img_name)[0] + '.txt'
                            label_path = f"{temp_dir}/labels/{label_name}"

                            if isinstance(img_data, dict) and 'bytes' in img_data:
                                try:
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data['bytes'])

                                    with Image.open(img_path) as img:
                                        img_width, img_height = img.size

                                        has_objects = False
                                        with open(label_path, 'w') as f:
                                            if objects and 'bbox' in objects:
                                                for bbox in objects['bbox']:
                                                    if len(bbox) < 4:
                                                        continue
                                                    x, y, width, height = bbox
                                                    cx = (x + width/2) / img_width
                                                    cy = (y + height/2) / img_height
                                                    w = width / img_width
                                                    h = height / img_height

                                                    if w <= 0 or h <= 0:
                                                        logger.warning(
                                                            f"Skipped invalid bbox | image={img_path} | label={label_path} | "
                                                            f"bbox_line='1 {cx} {cy} {w} {h}' | reason=width/height <= 0"
                                                        )
                                                        self.stats['invalid_bbox_skipped'] += 1
                                                        continue

                                                    f.write(f"1 {cx} {cy} {w} {h}\n")
                                                    has_objects = True

                                        if has_objects:
                                            self.all_image_paths.append((img_path, label_path))
                                            self.stats['smoke_images'] += 1
                                except (IOError, ValueError) as e:
                                    print(f"Error processing image {img_path}: {e}")

                except (IOError, ValueError, KeyError) as e:
                    print(f"Error processing PyroNear file {file}: {e}")

    def process_ai_hub(self):
        print("Processing AI Hub dataset...")
        ai_hub_path = f"{BASE}/{AIHUB_DATASET_SUBPATH}"

        aihub_dir = f"{OUTPUT_DIR}/aihub"
        os.makedirs(f"{aihub_dir}/images/train", exist_ok=True)
        os.makedirs(f"{aihub_dir}/labels/train", exist_ok=True)

        for split in ['Training', 'Validation']:
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
                    if file.endswith('.json'):
                        json_path = os.path.join(root, file)

                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)

                            if 'images' not in data or 'annotations' not in data:
                                continue

                            for img_info in data['images']:
                                img_name = img_info['file_name']
                                img_width = img_info['width']
                                img_height = img_info['height']

                                img_path = img_index.get(img_name)

                                if not img_path or not os.path.exists(img_path):
                                    continue

                                annotations = [ann for ann in data['annotations'] if ann['image_id'] == img_info['id']]

                                label_name = os.path.splitext(img_name)[0] + '.txt'
                                label_path = f"{aihub_dir}/labels/train/{label_name}"

                                has_fire = False
                                has_smoke = False
                                has_objects = False

                                with open(label_path, 'w') as label_file:
                                    for ann in annotations:
                                        category_id = ann['category_id']
                                        bbox = ann['bbox']

                                        if len(bbox) < 4:
                                            continue

                                        if category_id == 3:
                                            class_id = 0
                                            has_fire = True
                                        elif category_id in [1, 2, 6]:
                                            class_id = 1
                                            has_smoke = True
                                        else:
                                            continue

                                        x, y, width, height = bbox
                                        cx = (x + width/2) / img_width
                                        cy = (y + height/2) / img_height
                                        w = width / img_width
                                        h = height / img_height

                                        if w <= 0 or h <= 0:
                                            logger.warning(
                                                f"Skipped invalid bbox | image={img_name} | label={label_path} | "
                                                f"bbox_line='{class_id} {cx} {cy} {w} {h}' | reason=width/height <= 0"
                                            )
                                            self.stats['invalid_bbox_skipped'] += 1
                                            continue

                                        label_file.write(f"{class_id} {cx} {cy} {w} {h}\n")
                                        has_objects = True

                                if has_objects:
                                    symlink_img_path = f"{aihub_dir}/images/train/{img_name}"
                                    if not os.path.exists(symlink_img_path):
                                        try:
                                            rel_path = os.path.relpath(img_path, os.path.dirname(symlink_img_path))
                                            os.symlink(rel_path, symlink_img_path)
                                        except OSError as e:
                                            print(f"Error creating symlink {symlink_img_path}: {e}")
                                            continue

                                    self.all_image_paths.append((symlink_img_path, label_path))
                                    if has_fire:
                                        self.stats['fire_images'] += 1
                                    if has_smoke:
                                        self.stats['smoke_images'] += 1

                        except (IOError, ValueError, KeyError) as e:
                            print(f"Error processing AI Hub file {json_path}: {e}")

    def split_and_create_files(self):
        print("Creating train/val/test split files...")

        print("Cleaning up previous unified dataset outputs...")
        if os.path.exists(f"{OUTPUT_DIR}/images"):
            shutil.rmtree(f"{OUTPUT_DIR}/images")
        if os.path.exists(f"{OUTPUT_DIR}/labels"):
            shutil.rmtree(f"{OUTPUT_DIR}/labels")
        for file in ['train.txt', 'val.txt', 'test.txt', 'data.yaml']:
            file_path = f"{OUTPUT_DIR}/{file}"
            if os.path.exists(file_path):
                os.remove(file_path)

        if DATASET_TRAIN_RATIO + DATASET_VAL_RATIO > 1.0:
            raise ValueError(f"Invalid dataset ratios: train={DATASET_TRAIN_RATIO}, val={DATASET_VAL_RATIO}, sum > 1.0")

        rng = random.Random(DATASET_RANDOM_SEED)
        rng.shuffle(self.all_image_paths)
        total = len(self.all_image_paths)

        train_end = int(total * DATASET_TRAIN_RATIO)
        val_end = int(total * (DATASET_TRAIN_RATIO + DATASET_VAL_RATIO))

        train_data = self.all_image_paths[:train_end]
        val_data = self.all_image_paths[train_end:val_end]
        test_data = self.all_image_paths[val_end:]

        self.stats['total_images'] = total
        self.stats['train_count'] = len(train_data)
        self.stats['val_count'] = len(val_data)
        self.stats['test_count'] = len(test_data)

        os.makedirs(f"{OUTPUT_DIR}/images/train", exist_ok=True)
        os.makedirs(f"{OUTPUT_DIR}/images/val", exist_ok=True)
        os.makedirs(f"{OUTPUT_DIR}/images/test", exist_ok=True)
        os.makedirs(f"{OUTPUT_DIR}/labels/train", exist_ok=True)
        os.makedirs(f"{OUTPUT_DIR}/labels/val", exist_ok=True)
        os.makedirs(f"{OUTPUT_DIR}/labels/test", exist_ok=True)

        self._create_unified_dataset('train', train_data)
        self._create_unified_dataset('val', val_data)
        self._create_unified_dataset('test', test_data)

        self._verify_unified_dataset()

    def _create_unified_dataset(self, split, data):
        txt_file = f"{OUTPUT_DIR}/{split}.txt"
        with open(txt_file, 'w') as f:
            for idx, (src_img_path, src_label_path) in enumerate(data):
                img_basename = os.path.basename(src_img_path)
                img_name, img_ext = os.path.splitext(img_basename)

                unique_img_name = f"{split}_{idx:06d}_{img_basename}"
                unique_label_name = f"{split}_{idx:06d}_{img_name}.txt"

                unified_img_path = f"{OUTPUT_DIR}/images/{split}/{unique_img_name}"
                unified_label_path = f"{OUTPUT_DIR}/labels/{split}/{unique_label_name}"

                if not os.path.exists(unified_img_path):
                    try:
                        rel_path = os.path.relpath(src_img_path, os.path.dirname(unified_img_path))
                        os.symlink(rel_path, unified_img_path)
                    except OSError as e:
                        print(f"Error creating symlink {unified_img_path}: {e}")
                        self.stats['symlink_failures'] += 1
                        continue

                try:
                    with open(src_label_path, 'r') as src_f:
                        valid_lines = []
                        for line in src_f:
                            line = line.strip()
                            if line and self._validate_yolo_line(line, unified_img_path, unified_label_path):
                                valid_lines.append(line + '\n')

                    if not valid_lines:
                        continue

                    with open(unified_label_path, 'w') as dst_f:
                        dst_f.writelines(valid_lines)
                except (IOError, OSError) as e:
                    print(f"Error copying label {src_label_path}: {e}")
                    self.stats['label_copy_failures'] += 1
                    continue

                f.write(f"{unified_img_path}\n")

    def _validate_yolo_line(self, line, img_path, label_path):
        try:
            parts = line.split()
            if len(parts) < 5:
                logger.warning(
                    f"Skipped invalid bbox | image={img_path} | label={label_path} | "
                    f"bbox_line='{line}' | reason=invalid format"
                )
                self.stats['invalid_bbox_skipped'] += 1
                return False

            width = float(parts[3])
            height = float(parts[4])

            if width <= 0:
                logger.warning(
                    f"Skipped invalid bbox | image={img_path} | label={label_path} | "
                    f"bbox_line='{line}' | reason=width <= 0"
                )
                self.stats['invalid_bbox_skipped'] += 1
                return False

            if height <= 0:
                logger.warning(
                    f"Skipped invalid bbox | image={img_path} | label={label_path} | "
                    f"bbox_line='{line}' | reason=height <= 0"
                )
                self.stats['invalid_bbox_skipped'] += 1
                return False

            return True
        except (ValueError, IndexError) as e:
            logger.warning(
                f"Skipped invalid bbox | image={img_path} | label={label_path} | "
                f"bbox_line='{line}' | reason=parse error ({e})"
            )
            self.stats['invalid_bbox_skipped'] += 1
            return False

    def _verify_unified_dataset(self):
        print("\nVerifying unified dataset integrity...")

        errors = []

        for split in ['train', 'val', 'test']:
            txt_file = f"{OUTPUT_DIR}/{split}.txt"

            if not os.path.exists(txt_file):
                errors.append(f"Missing {split}.txt file")
                continue

            with open(txt_file, 'r') as f:
                image_paths = [line.strip() for line in f if line.strip()]

            for img_path in image_paths:
                if not os.path.exists(img_path):
                    errors.append(f"Image does not exist: {img_path}")
                    continue

                img_name, img_ext = os.path.splitext(os.path.basename(img_path))
                label_path = f"{OUTPUT_DIR}/labels/{split}/{img_name}.txt"

                if not os.path.exists(label_path):
                    errors.append(f"Missing label for image: {img_path} (expected: {label_path})")

        for split in ['train', 'val', 'test']:
            labels_dir = f"{OUTPUT_DIR}/labels/{split}"
            images_dir = f"{OUTPUT_DIR}/images/{split}"

            if os.path.exists(labels_dir):
                label_files = set(os.listdir(labels_dir))
                if os.path.exists(images_dir):
                    image_files = set(os.listdir(images_dir))
                    expected_labels = {os.path.splitext(img)[0] + '.txt' for img in image_files}

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

    def create_data_yaml(self):
        data_yaml = f"path: {OUTPUT_DIR}\ntrain: train.txt\nval: val.txt\ntest: test.txt\n\nnc: 2\nnames: ['fire', 'smoke']\n"
        with open(f"{OUTPUT_DIR}/data.yaml", 'w') as f:
            f.write(data_yaml)

    def print_statistics(self):
        print("\n=== Dataset Processing Complete ===")
        print(f"Total images: {self.stats['total_images']}")
        print(f"Fire images: {self.stats['fire_images']}")
        print(f"Smoke images: {self.stats['smoke_images']}")
        print(f"\nDataset split (80/10/10):")
        print(f"Train: {self.stats['train_count']}")
        print(f"Validation: {self.stats['val_count']}")
        print(f"Test: {self.stats['test_count']}")
        print(f"\nFailures:")
        print(f"Symlink creation failures: {self.stats['symlink_failures']}")
        print(f"Label copy failures: {self.stats['label_copy_failures']}")
        print(f"Invalid bboxes skipped: {self.stats['invalid_bbox_skipped']}")

def main():
    processor = DatasetProcessor()

    processor.process_fasdd()
    processor.process_fasdd_uav()
    processor.process_pyronear()
    processor.process_ai_hub()

    processor.split_and_create_files()
    processor.create_data_yaml()
    processor.print_statistics()

    print(f"\nGenerated files:")
    print(f"- {OUTPUT_DIR}/data.yaml")
    print(f"- {OUTPUT_DIR}/train.txt")
    print(f"- {OUTPUT_DIR}/val.txt")
    print(f"- {OUTPUT_DIR}/test.txt")

if __name__ == "__main__":
    main()