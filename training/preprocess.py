"""
Wildfire Dataset Preprocessing Script

This script processes multiple wildfire detection datasets (FASDD, FASDD_UAV, PyroNear, AI Hub)
and creates unified YOLO format training/validation/test splits for wildfire detection model training.
The script handles fire and smoke object detection annotations and converts them to YOLO format.
"""

import os
import json
import pandas as pd
import random
from typing import Dict, List, Tuple

# Base directory containing all wildfire datasets
BASE = "/Users/dongjulee/Documents/AIdatasets/wildfire-dataset"
# Output directory for processed dataset files
OUTPUT_DIR = BASE

class DatasetProcessor:
    """
    Main class for processing wildfire detection datasets from multiple sources.

    Handles dataset loading, annotation conversion, and train/validation/test splitting
    for FASDD, FASDD_UAV, PyroNear, and AI Hub wildfire datasets.
    """

    def __init__(self):
        """
        Initialize the dataset processor with empty image paths list and statistics counters.
        """
        # List to store tuples of (image_path, label_path) for all processed images
        self.all_image_paths = []
        # Statistics tracking for different image types and dataset splits
        self.stats = {
            'total_images': 0,        # Total number of images processed
            'fire_images': 0,         # Number of images containing fire objects
            'smoke_images': 0,        # Number of images containing smoke objects
            'train_count': 0,         # Number of images in training set
            'val_count': 0,           # Number of images in validation set
            'test_count': 0           # Number of images in test set
        }

    def process_fasdd(self):
        """
        Process the FASDD (Fire and Smoke Detection Dataset) dataset.

        Reads YOLO format annotations and images from the FASDD dataset directory.
        Class 0 = fire, Class 1 = smoke. Updates statistics for fire and smoke images.
        """
        print("Processing FASDD dataset...")
        fasdd_path = f"{BASE}/FASDD"

        # Process each data split (train, validation, test)
        for split in ['train', 'val', 'test']:
            split_file = f"{fasdd_path}/annotations/YOLO/{split}.txt"
            if not os.path.exists(split_file):
                continue

            # Read list of image paths from split file
            with open(split_file, 'r') as f:
                for line in f:
                    img_path = line.strip()
                    # Remove 'images/' prefix if present
                    if img_path.startswith('images/'):
                        img_path = img_path[7:]

                    # Construct full paths to image and label files
                    src_img = f"{fasdd_path}/images/{img_path}"
                    src_label = f"{fasdd_path}/annotations/YOLO/labels/{img_path.replace('.jpg', '.txt')}"

                    # Only process if both image and label files exist
                    if os.path.exists(src_img) and os.path.exists(src_label):
                        self.all_image_paths.append((src_img, src_label))

                        # Parse label file to count fire and smoke objects
                        with open(src_label, 'r') as lf:
                            content = lf.read().strip()
                            if content:
                                lines = content.split('\n')
                                for line in lines:
                                    if line.strip():
                                        # First value in YOLO format is class_id
                                        class_id = int(line.split()[0])
                                        if class_id == 0:  # Fire class
                                            self.stats['fire_images'] += 1
                                        elif class_id == 1:  # Smoke class
                                            self.stats['smoke_images'] += 1

    def process_fasdd_uav(self):
        """
        Process the FASDD_UAV (Fire and Smoke Detection Dataset - UAV) dataset.

        Similar to FASDD but contains UAV/drone captured images.
        Class 0 = fire, Class 1 = smoke. Updates statistics for fire and smoke images.
        """
        print("Processing FASDD_UAV dataset...")
        fasdd_uav_path = f"{BASE}/FASDD_UAV"

        # Process each data split (train, validation, test)
        for split in ['train', 'val', 'test']:
            split_file = f"{fasdd_uav_path}/annotations/YOLO_UAV/{split}.txt"
            if not os.path.exists(split_file):
                continue

            # Read list of image paths from split file
            with open(split_file, 'r') as f:
                for line in f:
                    img_path = line.strip()
                    # Remove './images/' prefix if present
                    if img_path.startswith('./images/'):
                        img_path = img_path[9:]

                    # Construct full paths to image and label files
                    src_img = f"{fasdd_uav_path}/images/{img_path}"
                    src_label = f"{fasdd_uav_path}/annotations/YOLO_UAV/labels/{img_path.replace('.jpg', '.txt')}"

                    # Only process if both image and label files exist
                    if os.path.exists(src_img) and os.path.exists(src_label):
                        self.all_image_paths.append((src_img, src_label))

                        # Parse label file to count fire and smoke objects
                        with open(src_label, 'r') as lf:
                            content = lf.read().strip()
                            if content:
                                lines = content.split('\n')
                                for line in lines:
                                    if line.strip():
                                        # First value in YOLO format is class_id
                                        class_id = int(line.split()[0])
                                        if class_id == 0:  # Fire class
                                            self.stats['fire_images'] += 1
                                        elif class_id == 1:  # Smoke class
                                            self.stats['smoke_images'] += 1

    def process_pyronear(self):
        """
        Process the PyroNear dataset.

        PyroNear dataset is stored in Parquet format with embedded image bytes and bounding box annotations.
        Extracts images and converts bounding boxes to YOLO format. All objects are treated as smoke (class 1).
        """
        print("Processing PyroNear dataset...")
        pyronear_path = f"{BASE}/PyroNear/data"

        # Find training and validation Parquet files
        train_files = [f for f in os.listdir(pyronear_path) if f.startswith('train-')]
        val_files = [f for f in os.listdir(pyronear_path) if f.startswith('val-')]

        # Create temporary directory for extracted PyroNear images and labels
        temp_dir = f"{OUTPUT_DIR}/pyronear_temp"
        os.makedirs(f"{temp_dir}/images", exist_ok=True)
        os.makedirs(f"{temp_dir}/labels", exist_ok=True)

        # Process both training and validation files
        for files, split in [(train_files, 'train'), (val_files, 'val')]:
            for file in files:
                try:
                    # Read Parquet file containing image data and annotations
                    df = pd.read_parquet(f"{pyronear_path}/{file}")
                    for idx, row in df.iterrows():
                        if 'image' in row and 'objects' in row:
                            img_data = row['image']
                            objects = row['objects']

                            # Generate unique filename for this image
                            img_name = f"pyronear_{split}_{file}_{idx}.jpg"
                            img_path = f"{temp_dir}/images/{img_name}"
                            label_path = f"{temp_dir}/labels/{img_name.replace('.jpg', '.txt')}"

                            # Extract image bytes and save as JPEG file
                            if isinstance(img_data, dict) and 'bytes' in img_data:
                                with open(img_path, 'wb') as f:
                                    f.write(img_data['bytes'])

                                # Get image dimensions for YOLO format conversion
                                from PIL import Image
                                img = Image.open(img_path)
                                img_width, img_height = img.size

                                # Convert bounding boxes to YOLO format
                                has_objects = False
                                with open(label_path, 'w') as f:
                                    if objects and 'bbox' in objects:
                                        for bbox in objects['bbox']:
                                            x, y, width, height = bbox
                                            # Convert to YOLO format (normalized center coordinates)
                                            cx = (x + width/2) / img_width
                                            cy = (y + height/2) / img_height
                                            w = width / img_width
                                            h = height / img_height
                                            # Class 1 = smoke for PyroNear dataset
                                            f.write(f"1 {cx} {cy} {w} {h}\n")
                                            has_objects = True

                                # Only keep images that have object annotations
                                if has_objects:
                                    self.all_image_paths.append((img_path, label_path))
                                    self.stats['smoke_images'] += 1

                except Exception as e:
                    print(f"Error processing PyroNear file {file}: {e}")

    def process_ai_hub(self):
        """
        Process the AI Hub wildfire dataset.

        Processes the Korean AI Hub wildfire dataset with COCO format annotations.
        Maps category IDs: 3=fire (class 0), 1,2,6=smoke variants (class 1).
        Creates symlinks to original images and converts annotations to YOLO format.
        """
        print("Processing AI Hub dataset...")
        # Long path name for Korean AI Hub wildfire dataset
        ai_hub_path = f"{BASE}/265.지역안전재난(산불) 방재의 고도화를 위한 대규모 인공지능 데이터베이스 구축/01-1.정식개방데이터"

        # Create output directories for AI Hub processed data
        aihub_dir = f"{OUTPUT_DIR}/aihub"
        os.makedirs(f"{aihub_dir}/images/train", exist_ok=True)
        os.makedirs(f"{aihub_dir}/labels/train", exist_ok=True)

        # Process both Training and Validation splits from AI Hub
        for split in ['Training', 'Validation']:
            img_dir = f"{ai_hub_path}/{split}/01.원천데이터"  # Original data directory
            label_dir = f"{ai_hub_path}/{split}/02.라벨링데이터"  # Labeling data directory

            if not os.path.exists(img_dir) or not os.path.exists(label_dir):
                continue

            # Build index of all image files for fast lookup
            print(f"Building image index for {split}...")
            img_index = {f: os.path.join(r, f) for r, _, files in os.walk(img_dir) for f in files}
            print(f"Found {len(img_index)} images in {split}")

            # Walk through all JSON annotation files
            for root, dirs, files in os.walk(label_dir):
                for file in files:
                    if file.endswith('.json'):
                        json_path = os.path.join(root, file)

                        try:
                            # Load COCO format annotation file
                            with open(json_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)

                            # Skip files without proper COCO format structure
                            if 'images' not in data or 'annotations' not in data:
                                continue

                            # Process each image in the annotation file
                            for img_info in data['images']:
                                img_name = img_info['file_name']
                                img_width = img_info['width']
                                img_height = img_info['height']

                                # Find the corresponding image file
                                img_path = img_index.get(img_name)

                                if not img_path or not os.path.exists(img_path):
                                    continue

                                # Get all annotations for this image
                                annotations = [ann for ann in data['annotations'] if ann['image_id'] == img_info['id']]

                                label_name = img_name.replace('.jpg', '.txt')
                                label_path = f"{aihub_dir}/labels/train/{label_name}"

                                # Track what types of objects are found
                                has_fire = False
                                has_smoke = False
                                has_objects = False

                                # Convert annotations to YOLO format
                                with open(label_path, 'w') as label_file:
                                    for ann in annotations:
                                        category_id = ann['category_id']
                                        bbox = ann['bbox']

                                        # Map AI Hub categories to our classes
                                        if category_id == 3:  # Fire
                                            class_id = 0
                                            has_fire = True
                                        elif category_id in [1, 2, 6]:  # Various smoke types
                                            class_id = 1
                                            has_smoke = True
                                        else:
                                            continue  # Skip unknown categories

                                        # Convert COCO bbox (x,y,w,h) to YOLO format (normalized center)
                                        x, y, width, height = bbox
                                        cx = (x + width/2) / img_width
                                        cy = (y + height/2) / img_height
                                        w = width / img_width
                                        h = height / img_height
                                        label_file.write(f"{class_id} {cx} {cy} {w} {h}\n")
                                        has_objects = True

                                # Only process images with valid object annotations
                                if has_objects:
                                    # Create symlink to original image (avoid copying large files)
                                    symlink_img_path = f"{aihub_dir}/images/train/{img_name}"
                                    if not os.path.exists(symlink_img_path):
                                        os.symlink(img_path, symlink_img_path)

                                    self.all_image_paths.append((symlink_img_path, label_path))
                                    # Update statistics based on object types found
                                    if has_fire:
                                        self.stats['fire_images'] += 1
                                    if has_smoke:
                                        self.stats['smoke_images'] += 1

                        except Exception as e:
                            print(f"Error processing AI Hub file {json_path}: {e}")

    def split_and_create_files(self):
        """
        Split the combined dataset into train/validation/test sets and create file lists.

        Uses 80/10/10 split ratio for train/validation/test.
        Creates text files containing image paths for each split that YOLO can use for training.
        """
        print("Creating train/val/test split files...")

        # Randomly shuffle all image paths to ensure random distribution
        random.shuffle(self.all_image_paths)
        total = len(self.all_image_paths)

        # Calculate split boundaries (80% train, 10% val, 10% test)
        train_end = int(total * 0.8)
        val_end = int(total * 0.9)

        # Split the dataset
        train_data = self.all_image_paths[:train_end]
        val_data = self.all_image_paths[train_end:val_end]
        test_data = self.all_image_paths[val_end:]

        # Update statistics with split counts
        self.stats['total_images'] = total
        self.stats['train_count'] = len(train_data)
        self.stats['val_count'] = len(val_data)
        self.stats['test_count'] = len(test_data)

        # Write training set file (image paths only)
        with open(f"{OUTPUT_DIR}/train.txt", 'w') as f:
            for img_path, label_path in train_data:
                f.write(f"{img_path}\n")

        # Write validation set file
        with open(f"{OUTPUT_DIR}/val.txt", 'w') as f:
            for img_path, label_path in val_data:
                f.write(f"{img_path}\n")

        # Write test set file
        with open(f"{OUTPUT_DIR}/test.txt", 'w') as f:
            for img_path, label_path in test_data:
                f.write(f"{img_path}\n")

    def create_data_yaml(self):
        """
        Create YOLO dataset configuration file (data.yaml).

        This file tells YOLO where to find the dataset files and defines the class names.
        Required for YOLO training to locate train/val/test splits and understand class mapping.
        """
        # YOLO dataset configuration format
        data_yaml = f"""path: {OUTPUT_DIR}
train: train.txt
val: val.txt
test: test.txt

nc: 2
names: ['fire', 'smoke']
"""
        with open(f"{OUTPUT_DIR}/data.yaml", 'w') as f:
            f.write(data_yaml)

    def print_statistics(self):
        """
        Print dataset processing statistics and summary.

        Displays total image counts, class distribution, and train/val/test split sizes.
        """
        print("\n=== Dataset Processing Complete ===")
        print(f"Total images: {self.stats['total_images']}")
        print(f"Fire images: {self.stats['fire_images']}")
        print(f"Smoke images: {self.stats['smoke_images']}")
        print(f"\nDataset split (80/10/10):")
        print(f"Train: {self.stats['train_count']}")
        print(f"Validation: {self.stats['val_count']}")
        print(f"Test: {self.stats['test_count']}")

def main():
    """
    Main function to execute the complete dataset preprocessing pipeline.

    Processes all wildfire datasets, creates train/val/test splits,
    generates YOLO configuration files, and prints summary statistics.
    """
    # Initialize the dataset processor
    processor = DatasetProcessor()

    # Process each dataset source
    processor.process_fasdd()        # FASDD satellite/aerial images
    processor.process_fasdd_uav()    # FASDD UAV/drone images
    processor.process_pyronear()     # PyroNear parquet format dataset
    processor.process_ai_hub()       # Korean AI Hub wildfire dataset

    # Create unified dataset splits and configuration
    processor.split_and_create_files()  # Generate train/val/test splits
    processor.create_data_yaml()         # Create YOLO config file
    processor.print_statistics()         # Display processing summary

    # Show generated output files
    print(f"\nGenerated files:")
    print(f"- {OUTPUT_DIR}/data.yaml")    # YOLO dataset configuration
    print(f"- {OUTPUT_DIR}/train.txt")    # Training image list
    print(f"- {OUTPUT_DIR}/val.txt")      # Validation image list
    print(f"- {OUTPUT_DIR}/test.txt")     # Test image list

# Execute the preprocessing pipeline when script is run directly
if __name__ == "__main__":
    main()