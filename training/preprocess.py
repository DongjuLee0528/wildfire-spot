import os
import json
import pandas as pd
import random
from PIL import Image
from utils.config import (DATASET_BASE_PATH, DATASET_OUTPUT_PATH, DATASET_TRAIN_RATIO,
                         DATASET_VAL_RATIO, AIHUB_DATASET_SUBPATH)

BASE = DATASET_BASE_PATH
OUTPUT_DIR = DATASET_OUTPUT_PATH

class DatasetProcessor:

    def __init__(self):
        self.all_image_paths = []
        self.stats = {
            'total_images': 0,
            'fire_images': 0,
            'smoke_images': 0,
            'train_count': 0,
            'val_count': 0,
            'test_count': 0
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
                        src_label = f"{fasdd_path}/annotations/YOLO/labels/{img_path.replace('.jpg', '.txt')}"

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
                        src_label = f"{fasdd_uav_path}/annotations/YOLO_UAV/labels/{img_path.replace('.jpg', '.txt')}"

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
            train_files = [f for f in os.listdir(pyronear_path) if f.startswith('train-')]
            val_files = [f for f in os.listdir(pyronear_path) if f.startswith('val-')]
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
                            label_path = f"{temp_dir}/labels/{img_name.replace('.jpg', '.txt')}"

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
        ai_hub_path = f"{DATASET_BASE_PATH}/{AIHUB_DATASET_SUBPATH}"

        aihub_dir = f"{OUTPUT_DIR}/aihub"
        os.makedirs(f"{aihub_dir}/images/train", exist_ok=True)
        os.makedirs(f"{aihub_dir}/labels/train", exist_ok=True)

        for split in ['Training', 'Validation']:
            img_dir = f"{ai_hub_path}/{split}/source-data"
            label_dir = f"{ai_hub_path}/{split}/labeling-data"

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                continue

            print(f"Building image index for {split}...")
            img_index = {f: os.path.join(r, f) for r, _, files in os.walk(img_dir) for f in files}
            print(f"Found {len(img_index)} images in {split}")

            for root, dirs, files in os.walk(label_dir):
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

                                label_name = img_name.replace('.jpg', '.txt')
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
                                        label_file.write(f"{class_id} {cx} {cy} {w} {h}\n")
                                        has_objects = True

                                if has_objects:
                                    symlink_img_path = f"{aihub_dir}/images/train/{img_name}"
                                    if not os.path.exists(symlink_img_path):
                                        try:
                                            os.symlink(img_path, symlink_img_path)
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

        if DATASET_TRAIN_RATIO + DATASET_VAL_RATIO > 1.0:
            raise ValueError(f"Invalid dataset ratios: train={DATASET_TRAIN_RATIO}, val={DATASET_VAL_RATIO}, sum > 1.0")

        random.shuffle(self.all_image_paths)
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

        with open(f"{OUTPUT_DIR}/train.txt", 'w') as f:
            for img_path, label_path in train_data:
                f.write(f"{img_path}\n")

        with open(f"{OUTPUT_DIR}/val.txt", 'w') as f:
            for img_path, label_path in val_data:
                f.write(f"{img_path}\n")

        with open(f"{OUTPUT_DIR}/test.txt", 'w') as f:
            for img_path, label_path in test_data:
                f.write(f"{img_path}\n")

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