import subprocess
import sys
import os
from utils.config import (WANDB_PROJECT, WANDB_ENTITY, TRAIN_MODEL_PATH, TRAIN_DATA_YAML,
                         TRAIN_OUTPUT_DIR, TRAIN_EPOCHS, TRAIN_BATCH_SIZE, TRAIN_IMAGE_SIZE,
                         TRAIN_SAVE_PERIOD, TRAIN_PATIENCE, TRAIN_DEVICE, TRAIN_RUN_NAME,
                         TRAIN_WORKERS, TRAIN_AUGMENT, TRAIN_MOSAIC, TRAIN_HSV_H, TRAIN_HSV_S,
                         TRAIN_HSV_V, TRAIN_FLIPUD, TRAIN_FLIPLR)

def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import ultralytics
except ImportError:
    install_package("ultralytics")
    import ultralytics

try:
    import wandb
except ImportError:
    install_package("wandb")
    import wandb

wandb_api_key = os.environ.get('WANDB_API_KEY')
if wandb_api_key:
    wandb.login(key=wandb_api_key)

from ultralytics import YOLO

def main():
    wandb.init(project=WANDB_PROJECT, entity=WANDB_ENTITY)

    print("Starting wildfire detection training with YOLOv10s...")

    if not os.path.exists(TRAIN_MODEL_PATH):
        raise FileNotFoundError(f"Model file not found: {TRAIN_MODEL_PATH}")

    model = YOLO(TRAIN_MODEL_PATH)

    results = model.train(
        data=TRAIN_DATA_YAML,
        epochs=TRAIN_EPOCHS,
        batch=TRAIN_BATCH_SIZE,
        imgsz=TRAIN_IMAGE_SIZE,
        save_period=TRAIN_SAVE_PERIOD,
        patience=TRAIN_PATIENCE,
        device=TRAIN_DEVICE,
        project=TRAIN_OUTPUT_DIR,
        name=TRAIN_RUN_NAME,
        workers=TRAIN_WORKERS,
        augment=TRAIN_AUGMENT,
        mosaic=TRAIN_MOSAIC,
        hsv_h=TRAIN_HSV_H,
        hsv_s=TRAIN_HSV_S,
        hsv_v=TRAIN_HSV_V,
        flipud=TRAIN_FLIPUD,
        fliplr=TRAIN_FLIPLR
    )

    print("Training completed successfully!")
    print(f"Results saved to: {results.save_dir}")

if __name__ == "__main__":
    main()